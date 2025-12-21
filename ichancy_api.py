#ichancy_api.py

import cloudscraper
import random
import string
import os
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Tuple, Optional
from functools import wraps

# =========================
# GLOBAL LOCK & SESSION
# =========================
_global_lock = threading.Lock()
_global_scraper = None
_global_session_data = {
    "cookies": {},
    "expiry": None,
    "last_login": None,
    "logged_in": False
}

class IChancyAPI:
    def __init__(self):
        self._setup_logging()
        self._load_config()
        self._init_scraper()

    # -------------------------
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger("ichancy")

    # -------------------------
    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME", "twd_bot@agent.nsp")
        self.PASSWORD = os.getenv("AGENT_PASSWORD", "Twd@@123")
        self.PARENT_ID = os.getenv("PARENT_ID", "2470819")

        self.ORIGIN = "https://agents.ichancy.com"
        self.ENDPOINTS = {
            "signin": "/global/api/User/signIn",
            "create": "/global/api/Player/registerPlayer",
            "statistics": "/global/api/Statistics/getPlayersStatisticsPro",
            "deposit": "/global/api/Player/depositToPlayer",
            "withdraw": "/global/api/Player/withdrawFromPlayer",
            "balance": "/global/api/Player/getPlayerBalanceById",
        }

        self.USER_AGENT = (
            "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.5249.126 Mobile Safari/537.36"
        )

    # -------------------------
    def _init_scraper(self):
        global _global_scraper
        if _global_scraper is None:
            _global_scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
        self.scraper = _global_scraper

        if _global_session_data["cookies"]:
            self.scraper.cookies.update(_global_session_data["cookies"])

    # -------------------------
    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard"
        }

    # =========================
    # LOGIN MANAGEMENT
    # =========================
    def _session_valid(self):
        if not _global_session_data["expiry"]:
            return False
        return datetime.now() < _global_session_data["expiry"]

    def ensure_login(self):
        with _global_lock:
            if self._session_valid() and _global_session_data["logged_in"]:
                return True

            self.logger.info("🔐 تسجيل دخول جديد...")
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS["signin"],
                json={"username": self.USERNAME, "password": self.PASSWORD},
                headers=self._headers()
            )

            data = resp.json()
            if not data.get("result"):
                raise Exception("فشل تسجيل الدخول")

            _global_session_data["cookies"] = dict(self.scraper.cookies)
            _global_session_data["expiry"] = datetime.now() + timedelta(minutes=30)
            _global_session_data["last_login"] = datetime.now()
            _global_session_data["logged_in"] = True

            self.logger.info("✅ تم تسجيل الدخول بنجاح")
            return True

    # =========================
    # SAFE RETRY DECORATOR
    # =========================
    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            attempts = 3
            for i in range(attempts):
                try:
                    self.ensure_login()
                    with _global_lock:
                        return func(self, *args, **kwargs)
                except Exception as e:
                    if i == attempts - 1:
                        raise
                    time.sleep(2 + random.random())
        return wrapper

    # =========================
    # API METHODS (UNCHANGED LOGIC)
    # =========================
    @with_retry
    def create_player(self, login=None, password=None):
        login = login or "u" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(7))
        password = password or "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        email = f"{login}@example.com"

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["create"],
            json={"player": {
                "email": email,
                "password": password,
                "parentId": self.PARENT_ID,
                "login": login
            }},
            headers=self._headers()
        )

        data = resp.json()
        player_id = self.get_player_id(login)
        return resp.status_code, data, login, password, player_id

    @with_retry
    def get_player_id(self, login: str) -> Optional[str]:
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json={"page": 1, "pageSize": 100, "filter": {"login": login}},
            headers=self._headers()
        )
        data = resp.json()
        for r in data.get("result", {}).get("records", []):
            if r.get("username") == login:
                return r.get("playerId")
        return None

    @with_retry
    def deposit_to_player(self, player_id: str, amount: float):
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["deposit"],
            json={
                "amount": amount,
                "playerId": player_id,
                "currencyCode": "NSP",
                "moneyStatus": 5
            },
            headers=self._headers()
        )
        return resp.status_code, resp.json()

    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float):
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["withdraw"],
            json={
                "amount": amount,
                "playerId": player_id,
                "currencyCode": "NSP",
                "moneyStatus": 5
            },
            headers=self._headers()
        )
        return resp.status_code, resp.json()

    @with_retry
    def get_player_balance(self, player_id: str):
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["balance"],
            json={"playerId": str(player_id)},
            headers=self._headers()
        )
        data = resp.json()
        balance = data.get("result", [{}])[0].get("balance", 0)
        return resp.status_code, data, balance

