import cloudscraper
import random
import string
import os
import logging
from datetime import datetime, timedelta
from functools import wraps


class IChancyAPI:
    def __init__(self):
        self._setup_logging()
        self._load_config()

        # إنشاء سكرابر Cloudflare
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )

        self.is_logged_in = False
        self.session_expiry = None
        self.last_login_time = None

    # -----------------------------
    # إعدادات
    # -----------------------------
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
        self.PARENT_ID = os.getenv("PARENT_ID", "2470819")

        self.ORIGIN = "https://agents.ichancy.com"
        self.ENDPOINTS = {
            'signin': "/global/api/User/signIn",
            'create': "/global/api/Player/registerPlayer",
            'statistics': "/global/api/Statistics/getPlayersStatisticsPro",
            'deposit': "/global/api/Player/depositToPlayer",
            'withdraw': "/global/api/Player/withdrawFromPlayer",
            'balance': "/global/api/Player/getPlayerBalanceById"
        }

        self.USER_AGENT = (
            "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.5249.126 Mobile Safari/537.36"
        )
        self.REFERER = self.ORIGIN + "/dashboard"

    # -----------------------------
    # أدوات مساعدة
    # -----------------------------
    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER
        }

    def _is_session_valid(self):
        if not self.session_expiry or not self.last_login_time:
            return False

        if datetime.now() > self.session_expiry:
            return False

        if datetime.now() - self.last_login_time > timedelta(hours=2):
            return False

        return True

    # -----------------------------
    # تسجيل الدخول
    # -----------------------------
    def login(self):
        payload = {"username": self.USERNAME, "password": self.PASSWORD}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['signin'],
            json=payload,
            headers=self._headers()
        )

        try:
            data = resp.json()
        except:
            return False, {}

        if data.get("result", False):
            self.is_logged_in = True
            self.last_login_time = datetime.now()
            self.session_expiry = datetime.now() + timedelta(minutes=30)

            self.logger.info("✅ تسجيل الدخول ناجح — الجلسة جاهزة")
            return True, data

        return False, data

    def ensure_login(self):
        if self.is_logged_in and self._is_session_valid():
            return True

        self.logger.info("🔄 إعادة تسجيل الدخول...")
        ok, data = self.login()

        if not ok:
            msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول")
            raise RuntimeError(msg)

        return True

    # -----------------------------
    # Decorator لإعادة المحاولة
    # -----------------------------
    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.ensure_login()
            result = func(self, *args, **kwargs)

            if result is None:
                return 0, {}

            status, data = result[0], result[1]

            if status != 200:
                self.is_logged_in = False
                self.ensure_login()
                return func(self, *args, **kwargs)

            return result
        return wrapper

    # -----------------------------
    # API Calls
    # -----------------------------
    @with_retry
    def create_player(self):
        login = "u" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(7))
        pwd = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        email = f"{login}@example.com"

        payload = {
            "player": {
                "email": email,
                "password": pwd,
                "parentId": self.PARENT_ID,
                "login": login
            }
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['create'],
            json=payload,
            headers=self._headers()
        )

        try:
            data = resp.json()
        except:
            return resp.status_code, {}, login, pwd, None

        player_id = self.get_player_id(login)
        return resp.status_code, data, login, pwd, player_id

    @with_retry
    def get_player_id(self, login):
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._headers()
        )

        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            for r in records:
                if r.get("username") == login:
                    return r.get("playerId")
        except:
            pass

        return None

    @with_retry
    def create_player_with_credentials(self, login, pwd):
        email = f"{login}@agent.nsp"

        payload = {
            "player": {
                "email": email,
                "password": pwd,
                "parentId": self.PARENT_ID,
                "login": login
            }
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['create'],
            json=payload,
            headers=self._headers()
        )

        try:
            data = resp.json()
        except:
            return resp.status_code, {}, None, email

        player_id = self.get_player_id(login)
        return resp.status_code, data, player_id, email

    @with_retry
    def check_player_exists(self, login):
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._headers()
        )

        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            return any(r.get("username") == login for r in records)
        except:
            return False

    @with_retry
    def deposit_to_player(self, player_id, amount):
        payload = {
            "amount": amount,
            "comment": None,
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['deposit'],
            json=payload,
            headers=self._headers()
        )

        try:
            return resp.status_code, resp.json()
        except:
            return resp.status_code, {}

    @with_retry
    def withdraw_from_player(self, player_id, amount):
        payload = {
            "amount": amount,
            "comment": None,
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['withdraw'],
            json=payload,
            headers=self._headers()
        )

        try:
            return resp.status_code, resp.json()
        except:
            return resp.status_code, {}

    @with_retry
    def get_player_balance(self, player_id):
        payload = {"playerId": str(player_id)}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['balance'],
            json=payload,
            headers=self._headers()
        )

        try:
            data = resp.json()
            results = data.get("result", [])
            balance = results[0].get("balance", 0) if results else 0
            return resp.status_code, data, balance
        except:
            return resp.status_code, {}, 0
