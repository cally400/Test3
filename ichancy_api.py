import cloudscraper
import random
import string
import os
import logging
import time
import threading
import requests
from datetime import datetime, timedelta
from functools import wraps


class IChancyAPI:
    def __init__(self):
        self._setup_logging()
        self._load_config()

        self.scraper = None
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None

        self._init_scraper()
        self.start_session_watchdog()

    # ================= LOGGING =================

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

    # ================= CONFIG =================

    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
        self.PARENT_ID = os.getenv("PARENT_ID")

        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

        self.ORIGIN = "https://agents.ichancy.com"
        self.ENDPOINTS = {
            "signin": "/global/api/User/signIn",
            "create": "/global/api/Player/registerPlayer",
            "statistics": "/global/api/Statistics/getPlayersStatisticsPro",
            "deposit": "/global/api/Player/depositToPlayer",
            "withdraw": "/global/api/Player/withdrawFromPlayer",
            "balance": "/global/api/Player/getPlayerBalanceById",
        }

        self.USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0",
            "Mozilla/5.0 (Linux; Android 10) Chrome/120.0",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        ]

    # ================= TELEGRAM =================

    def notify_admin(self, message: str):
        if not self.TELEGRAM_BOT_TOKEN or not self.TELEGRAM_CHAT_ID:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": self.TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                },
                timeout=5,
            )
        except Exception:
            pass

    # ================= SESSION =================

    def _init_scraper(self):
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )

        if self.session_cookies and self._is_session_valid():
            self.scraper.cookies.update(self.session_cookies)
            self.is_logged_in = True
        else:
            self.is_logged_in = False

    def _is_session_valid(self):
        if not self.session_expiry or not self.last_login_time:
            return False
        return datetime.now() < self.session_expiry

    def reset_session(self, reason="unknown"):
        self.logger.warning(f"♻️ Reset session: {reason}")

        self.scraper = None
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None

        self.notify_admin(
            f"♻️ *Session Reset*\n"
            f"📌 Reason: `{reason}`\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def ensure_login(self):
        if not self.scraper:
            self._init_scraper()

        if self._is_session_valid() and self.is_logged_in:
            return True

        for attempt in range(1, 4):
            success, _ = self.login()
            if success:
                self.notify_admin(
                    f"✅ *Login Success*\n"
                    f"🔁 Attempt: {attempt}\n"
                    f"⏰ Expiry: {self.session_expiry.strftime('%H:%M:%S')}"
                )
                return True

            self.reset_session(f"login attempt {attempt}")
            time.sleep(3)

        self.notify_admin("🚨 *Login failed after 3 attempts*")
        raise Exception("Login failed")

    # ================= LOGIN =================

    def login(self):
        self._init_scraper()

        headers = {
            "Content-Type": "application/json",
            "User-Agent": random.choice(self.USER_AGENTS),
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard",
        }

        payload = {
            "username": self.USERNAME,
            "password": self.PASSWORD,
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["signin"],
            json=payload,
            headers=headers,
        )

        data = resp.json()

        if data.get("result"):
            self.session_cookies = dict(self.scraper.cookies)
            self.session_expiry = datetime.now() + timedelta(minutes=25)
            self.last_login_time = datetime.now()
            self.is_logged_in = True
            return True, data

        return False, data

    # ================= RETRY =================

    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.ensure_login()
            time.sleep(random.uniform(1.5, 3.0))
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                self.reset_session(str(e))
                self.ensure_login()
                return func(self, *args, **kwargs)

        return wrapper

    # ================= API =================

    @with_retry
    def get_player_id(self, login: str):
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"login": login},
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": random.choice(self.USER_AGENTS),
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard",
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=headers,
        )

        records = resp.json().get("result", {}).get("records", [])
        for r in records:
            if r.get("username") == login:
                return r.get("playerId")

        return None

    @with_retry
    def create_player(self, login=None, password=None):
        login = login or "u" + "".join(
            random.choice(string.ascii_lowercase + string.digits) for _ in range(7)
        )
        password = password or "".join(
            random.choice(string.ascii_letters + string.digits) for _ in range(10)
        )
        email = f"{login}@example.com"

        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": self.PARENT_ID,
                "login": login,
            }
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": random.choice(self.USER_AGENTS),
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard",
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["create"],
            json=payload,
            headers=headers,
        )

        player_id = self.get_player_id(login)

        return {
            "status": resp.status_code,
            "login": login,
            "password": password,
            "email": email,
            "player_id": player_id,
            "raw": resp.json(),
        }

    @with_retry
    def deposit_to_player(self, player_id: str, amount: float):
        payload = {
            "amount": amount,
            "comment": "Deposit from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5,
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["deposit"],
            json=payload,
            headers=self._api_headers(),
        )

        return resp.status_code, resp.json()

    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float):
        payload = {
            "amount": amount,
            "comment": "Withdraw from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5,
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["withdraw"],
            json=payload,
            headers=self._api_headers(),
        )

        return resp.status_code, resp.json()

    @with_retry
    def get_player_balance(self, player_id: str):
        payload = {"playerId": str(player_id)}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["balance"],
            json=payload,
            headers=self._api_headers(),
        )

        data = resp.json()
        balance = 0
        try:
            balance = data["result"][0]["balance"]
        except Exception:
            pass

        return resp.status_code, balance, data

    def _api_headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": random.choice(self.USER_AGENTS),
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard",
        }

    # ================= WATCHDOG =================

    def start_session_watchdog(self):
        def watchdog():
            while True:
                try:
                    if not self._is_session_valid():
                        self.reset_session("session expired")
                        self.ensure_login()
                    time.sleep(60)
                except Exception as e:
                    self.notify_admin(f"🚨 Watchdog Error:\n`{e}`")
                    time.sleep(30)

        threading.Thread(target=watchdog, daemon=True).start()

