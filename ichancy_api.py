import cloudscraper
import os
import random
import string
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Tuple, Dict

class IChancyAPI:
    """API لإدارة اللاعبين على iChancy مع جلسة لكل مستخدم"""

    def __init__(self):
        self._setup_logging()
        self._load_config()
        self.sessions: Dict[str, cloudscraper.CloudScraper] = {}
        self.session_expiry: Dict[str, datetime] = {}

    # -------------------------
    # إعدادات
    # -------------------------
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
        self.PARENT_ID = os.getenv("PARENT_ID")

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

    # -------------------------
    # جلسة لكل مستخدم
    # -------------------------
    def _init_session(self, user_key: str):
        """تهيئة جلسة لكل مستخدم"""
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.sessions[user_key] = scraper
        self.session_expiry[user_key] = datetime.now() - timedelta(minutes=1)
        return scraper

    def _get_session(self, user_key: str) -> cloudscraper.CloudScraper:
        """الحصول على جلسة صالحة"""
        scraper = self.sessions.get(user_key) or self._init_session(user_key)
        expiry = self.session_expiry.get(user_key)

        # إعادة تسجيل الدخول إذا انتهت الجلسة
        if not expiry or datetime.now() > expiry:
            self._login(scraper)
            self.session_expiry[user_key] = datetime.now() + timedelta(minutes=30)

        return scraper

    # -------------------------
    # تسجيل الدخول
    # -------------------------
    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard"
        }

    def _safe_json(self, resp):
        try:
            return resp.json()
        except ValueError:
            return {}

    def _check_captcha(self, resp) -> bool:
        text = resp.text.lower()
        if 'captcha' in text or 'cloudflare' in text:
            self.logger.warning("⚠️ اكتشاف كابتشا!")
            return True
        return False

    def _login(self, scraper: cloudscraper.CloudScraper):
        payload = {"username": self.USERNAME, "password": self.PASSWORD}
        resp = scraper.post(self.ORIGIN + self.ENDPOINTS['signin'], json=payload, headers=self._get_headers())
        data = self._safe_json(resp)
        if not data.get("result", False):
            raise Exception("❌ فشل تسجيل الدخول")
        self.logger.info("✅ تم تسجيل الدخول بنجاح")

    # -------------------------
    # Decorator لإعادة المحاولة
    # -------------------------
    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            user_key = kwargs.get("user_key", "default")
            scraper = self._get_session(user_key)
            try:
                result = func(self, *args, **kwargs, scraper=scraper)
                # التحقق من الكابتشا
                if isinstance(result, tuple):
                    status, data = result[0], result[1]
                    if status == 403 or ('captcha' in str(data).lower()):
                        self.logger.warning("كابتشا، إعادة المحاولة...")
                        scraper = self._init_session(user_key)
                        self._login(scraper)
                        result = func(self, *args, **kwargs, scraper=scraper)
                return result
            except Exception as e:
                self.logger.error(f"خطأ في {func.__name__}: {str(e)}")
                return 500, {"error": str(e)}
        return wrapper

    # -------------------------
    # التحقق من وجود لاعب
    # -------------------------
    @with_retry
    def check_player_exists(self, login: str, user_key="default", scraper=None) -> bool:
        payload = {"page":1,"pageSize":100,"filter":{"login": login}}
        resp = scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        data = self._safe_json(resp)
        records = data.get("result", {}).get("records", [])
        return any(record.get("username") == login for record in records)

    # -------------------------
    # إنشاء لاعب جديد
    # -------------------------
    @with_retry
    def create_player_with_credentials(self, login: str, password: str, user_key="default", scraper=None) -> Tuple[int, dict, Optional[str]]:
        email = f"{login}@agent.nsp"
        suffix = 1
        while self.check_email_exists(email, user_key=user_key):
            email = f"{login}_{suffix}@agent.nsp"
            suffix += 1

        payload = {"player": {"email": email, "password": password, "parentId": self.PARENT_ID, "login": login}}
        resp = scraper.post(self.ORIGIN + self.ENDPOINTS['create'], json=payload, headers=self._get_headers())
        data = self._safe_json(resp)
        player_id = self.get_player_id(login, user_key=user_key)
        return resp.status_code, data, player_id

    # -------------------------
    # التحقق من البريد الإلكتروني
    # -------------------------
    @with_retry
    def check_email_exists(self, email: str, user_key="default", scraper=None) -> bool:
        payload = {"page":1,"pageSize":100,"filter":{"email": email}}
        resp = scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        data = self._safe_json(resp)
        records = data.get("result", {}).get("records", [])
        return any(record.get("email") == email for record in records)

    # -------------------------
    # الحصول على معرف اللاعب
    # -------------------------
    @with_retry
    def get_player_id(self, login: str, user_key="default", scraper=None) -> Optional[str]:
        payload = {"page":1,"pageSize":100,"filter":{"login": login}}
        resp = scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        data = self._safe_json(resp)
        records = data.get("result", {}).get("records", [])
        for r in records:
            if r.get("username") == login:
                return r.get("playerId")
        return None

    # -------------------------
    # إيداع
    # -------------------------
    @with_retry
    def deposit_to_player(self, player_id: str, amount: float, user_key="default", scraper=None) -> Tuple[int, dict]:
        payload = {"playerId": player_id, "amount": amount, "currency": "NSP", "currencyCode": "NSP", "moneyStatus": 5}
        resp = scraper.post(self.ORIGIN + self.ENDPOINTS['deposit'], json=payload, headers=self._get_headers())
        return resp.status_code, self._safe_json(resp)

    # -------------------------
    # سحب
    # -------------------------
    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float, user_key="default", scraper=None) -> Tuple[int, dict]:
        payload = {"playerId": player_id, "amount": amount, "currency": "NSP", "currencyCode": "NSP", "moneyStatus": 5}
        resp = scraper.post(self.ORIGIN + self.ENDPOINTS['withdraw'], json=payload, headers=self._get_headers())
        return resp.status_code, self._safe_json(resp)

    # -------------------------
    # رصيد اللاعب
    # -------------------------
    @with_retry
    def get_player_balance(self, player_id: str, user_key="default", scraper=None) -> Tuple[int, dict, float]:
        payload = {"playerId": str(player_id)}
        resp = scraper.post(self.ORIGIN + self.ENDPOINTS['balance'], json=payload, headers=self._get_headers())
        data = self._safe_json(resp)
        results = data.get("result", [])
        balance = results[0].get("balance", 0) if isinstance(results, list) and results else 0
        return resp.status_code, data, balance

