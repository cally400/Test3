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
from typing import Tuple, Optional

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
        self.start_watchdog()

    def _setup_logging(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
        self.PARENT_ID = os.getenv("PARENT_ID")
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
        self.ORIGIN = "https://agents.ichancy.com"
        self.ENDPOINTS = {
            'signin': "/global/api/User/signIn",
            'create': "/global/api/Player/registerPlayer",
            'statistics': "/global/api/Statistics/getPlayersStatisticsPro",
            'deposit': "/global/api/Player/depositToPlayer",
            'withdraw': "/global/api/Player/withdrawFromPlayer",
            'balance': "/global/api/Player/getPlayerBalanceById"
        }
        self.USER_AGENT = "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.5249.126 Mobile Safari/537.36"
        self.REFERER = self.ORIGIN + "/dashboard"

    def notify_admin(self, message: str):
        if not self.TELEGRAM_BOT_TOKEN or not self.TELEGRAM_CHAT_ID:
            return
        try:
            requests.post(f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": self.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
        except Exception:
            pass

    def _init_scraper(self):
        self.scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','platform': 'windows','mobile': False})
        if self.session_cookies and self._is_session_valid():
            self.scraper.cookies.update(self.session_cookies)
            self.is_logged_in = True
        else:
            self.is_logged_in = False
            self.session_cookies = {}

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
        self.notify_admin(f"♻️ *Session Reset*\n📌 Reason: `{reason}`\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def ensure_login(self):
        if not self.scraper:
            self._init_scraper()
        if self._is_session_valid() and self.is_logged_in:
            return True
        success, _ = self.login()
        if not success:
            self.reset_session("Login failed")
            raise Exception("Login failed")
        return True

    def login(self):
        self._init_scraper()
        payload = {"username": self.USERNAME, "password": self.PASSWORD}
        try:
            resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['signin'], json=payload, headers=self._get_headers())
            data = resp.json()
            if data.get("result", False):
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=30)
                self.last_login_time = datetime.now()
                self.is_logged_in = True
                self.notify_admin(f"✅ *Logged in*\n⏰ Session expires: {self.session_expiry.strftime('%H:%M:%S')}")
                return True, data
            else:
                return False, data
        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return False, {"error": str(e)}

    def _get_headers(self):
        return {"Content-Type": "application/json", "User-Agent": self.USER_AGENT,
                "Origin": self.ORIGIN, "Referer": self.REFERER}

    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.ensure_login()
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                self.reset_session(str(e))
                self.ensure_login()
                return func(self, *args, **kwargs)
        return wrapper

    # ====== PLAYER FUNCTIONS ======
    @with_retry
    def create_player(self, login=None, password=None):
        login = login or "u" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(7))
        password = password or "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        email = f"{login}@example.com"
        payload = {"player": {"email": email, "password": password, "parentId": self.PARENT_ID, "login": login}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['create'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
        except Exception:
            data = {}
        player_id = self.get_player_id(login)
        return resp.status_code, data, login, password, player_id

    @with_retry
    def create_player_with_credentials(self, login: str, password: str):
        email = f"{login}@agint.nsp"
        suffix = 1
        while self.check_email_exists(email):
            email = f"{login}_{suffix}@agint.nsp"
            suffix += 1
        payload = {"player": {"email": email, "password": password, "parentId": self.PARENT_ID, "login": login}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['create'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
        except Exception:
            data = {}
        player_id = self.get_player_id(login)
        return resp.status_code, data, player_id, email

    @with_retry
    def get_player_id(self, login: str):
        payload = {"page":1, "pageSize":100, "filter":{"login":login}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            for r in records:
                if r.get("username") == login:
                    return r.get("playerId")
        except Exception:
            return None

    @with_retry
    def check_email_exists(self, email: str):
        payload = {"page":1, "pageSize":100, "filter":{"email":email}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            return any(r.get("email") == email for r in records)
        except Exception:
            return False

    @with_retry
    def check_player_exists(self, login: str):
        payload = {"page":1, "pageSize":100, "filter":{"login":login}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            return any(r.get("username") == login for r in records)
        except Exception:
            return False

    @with_retry
    def deposit_to_player(self, player_id: str, amount: float):
        payload = {"amount": amount, "comment":"Deposit from API", "playerId":player_id, "currencyCode":"NSP", "currency":"NSP","moneyStatus":5}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['deposit'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
        except Exception:
            data = {}
        return resp.status_code, data

    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float):
        payload = {"amount": amount, "comment":"Withdrawal from API", "playerId":player_id, "currencyCode":"NSP", "currency":"NSP","moneyStatus":5}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['withdraw'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
        except Exception:
            data = {}
        return resp.status_code, data

    @with_retry
    def get_player_balance(self, player_id: str):
        payload = {"playerId":player_id}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['balance'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            results = data.get("result", [])
            balance = results[0].get("balance", 0) if isinstance(results, list) and results else 0
        except Exception:
            data = {}
            balance = 0
        return resp.status_code, data, balance

    @with_retry
    def get_all_players(self):
        payload = {"page":1,"pageSize":100,"filter":{}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            return data.get("result", {}).get("records", [])
        except Exception:
            return []

    # ====== WATCHDOG ======
    def start_watchdog(self):
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

