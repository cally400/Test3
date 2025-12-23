import cloudscraper
import random
import string
import os
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional, List
from functools import wraps

COOKIE_FILE = "ichancy_session.json"

# إعداد اللوجينج مرة واحدة فقط
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


class IChancyAPI:
    def __init__(self):
        self.logger = logging.getLogger("IChancyAPI")
        self._load_config()

        # Lazy initialization
        self.scraper = None

        # Session state
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None

    # =========================
    # تحميل الإعدادات
    # =========================
    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME", "twd_bot@agent.nsp")
        self.PASSWORD = os.getenv("AGENT_PASSWORD", "Twd@@123")
        self.PARENT_ID = os.getenv("PARENT_ID", "2470819")

        self.ORIGIN = os.getenv("ICHANCY_ORIGIN", "https://agents.ichancy.com")

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

        self.REFERER = self.ORIGIN + "/dashboard"
        self.REQUEST_TIMEOUT = 25

    # =========================
    # إدارة Scraper
    # =========================
    def _init_scraper(self):
        if self.scraper:
            return

        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )

        # تحميل الكوكيز من الجلسة المحفوظة
        if self.session_cookies:
            self.scraper.cookies.update(self.session_cookies)

    def _is_session_valid(self):
        if not self.session_expiry or not self.last_login_time:
            return False

        now = datetime.now()

        if now >= self.session_expiry:
            return False

        # حماية إضافية
        if now - self.last_login_time >= timedelta(hours=2):
            return False

        return True

    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER,
        }

    def _check_captcha(self, response):
        try:
            text = response.text.lower()
        except:
            return False

        if "captcha" in text or "cloudflare" in text:
            self.logger.warning("⚠️ Cloudflare/Captcha detected")
            return True

        return False

    def _invalidate_session(self):
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None

    # =========================
    # حفظ الجلسة في ملف
    # =========================
    def _save_session_to_file(self):
        try:
            if not self.session_cookies:
                return

            data = {
                "cookies": self.session_cookies,
                "expiry": self.session_expiry.isoformat(),
                "last_login": self.last_login_time.isoformat(),
            }

            with open(COOKIE_FILE, "w") as f:
                json.dump(data, f)

            self.logger.info("💾 Session saved to file")

        except Exception as e:
            self.logger.error(f"❌ Failed to save session: {e}")

    # =========================
    # Decorator — with_retry
    # =========================
    @staticmethod
    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                self.ensure_login()

                resp = func(self, *args, **kwargs)

                # إذا API رجع 401/403 → إعادة تسجيل الدخول مرة واحدة
                if isinstance(resp, tuple) and resp[0] in (401, 403):
                    self.logger.warning("⚠️ Session invalid — retrying login")
                    self._invalidate_session()
                    self.ensure_login()
                    resp = func(self, *args, **kwargs)

                return resp

            except Exception as e:
                self.logger.error(f"❌ Error in {func.__name__}: {e}")
                return 500, {"error": str(e)}

        return wrapper

    # =========================
    # تسجيل الدخول
    # =========================
    def login(self):
        self._init_scraper()

        payload = {"username": self.USERNAME, "password": self.PASSWORD}

        try:
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS["signin"],
                json=payload,
                headers=self._get_headers(),
                timeout=self.REQUEST_TIMEOUT,
            )

            if resp.status_code != 200:
                return False, {"error": f"HTTP {resp.status_code}"}

            if self._check_captcha(resp):
                return False, {"error": "captcha_detected"}

            data = resp.json()

            if data.get("result"):
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=30)
                self.last_login_time = datetime.now()
                self.is_logged_in = True

                self._save_session_to_file()

                self.logger.info("✅ Login successful")
                return True, data

            msg = data.get("notification", [{"content": "login_failed"}])[0]["content"]
            return False, {"error": msg}

        except Exception as e:
            return False, {"error": str(e)}

    # =========================
    # ensure_login
    # =========================
    def ensure_login(self):
        self._init_scraper()

        if self.is_logged_in and self._is_session_valid():
            return True

        success, data = self.login()
        if not success:
            raise Exception(data.get("error", "login_failed"))

        return True

    # =========================
    # get_player_id
    # =========================
    @with_retry
    def get_player_id(self, login):
        self._init_scraper()

        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except:
            return None

        records = data.get("result", {}).get("records", [])

        for r in records:
            if r.get("login") == login or r.get("username") == login:
                return r.get("playerId")

        return None

    # =========================
    # check_player_exists
    # =========================
    @with_retry
    def check_player_exists(self, login):
        self._init_scraper()

        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except:
            return False

        records = data.get("result", {}).get("records", [])

        return any(
            (r.get("login") == login) or (r.get("username") == login)
            for r in records
        )

    # =========================
    # create_player_with_credentials
    # =========================
    @with_retry
    def create_player_with_credentials(self, login, password):
        self._init_scraper()

        email = f"{login}@agint.nsp"
        suffix = 1

        while self.check_email_exists(email):
            email = f"{login}_{suffix}@agint.nsp"
            suffix += 1

        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": self.PARENT_ID,
                "login": login,
            }
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["create"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except:
            data = {}

        # الحصول على player_id
        player_id = None
        for _ in range(5):
            player_id = self.get_player_id(login)
            if player_id:
                break
            time.sleep(1)

        return resp.status_code, data, player_id, email

    # =========================
    # check_email_exists
    # =========================
    @with_retry
    def check_email_exists(self, email):
        self._init_scraper()

        payload = {"page": 1, "pageSize": 100, "filter": {"email": email}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except:
            return False

        records = data.get("result", {}).get("records", [])
        return any(r.get("email") == email for r in records)

    # =========================
    # deposit
    # =========================
    @with_retry
    def deposit_to_player(self, player_id, amount):
        self._init_scraper()

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
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except:
            data = {}

        return resp.status_code, data

    # =========================
    # withdraw
    # =========================
    @with_retry
    def withdraw_from_player(self, player_id, amount):
        self._init_scraper()

        payload = {
            "amount": amount,
            "comment": "Withdrawal from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5,
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["withdraw"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except:
            data = {}

        return resp.status_code, data

    # =========================
    # get_player_balance
    # =========================
    @with_retry
    def get_player_balance(self, player_id):
        self._init_scraper()

        payload = {"playerId": str(player_id)}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["balance"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except:
            return resp.status_code, {}, 0.0

        results = data.get("result", [])
        balance = 0.0

        if isinstance(results, list) and results:
            try:
                balance = float(results[0].get("balance", 0))
            except:
                balance = 0.0

        return resp.status_code, data, balance

    # =========================
    # get_all_players
    # =========================
    @with_retry
    def get_all_players(self):
        self._init_scraper()

        payload = {"page": 1, "pageSize": 100, "filter": {}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except:
            return []

        return data.get("result", {}).get("records", [])
