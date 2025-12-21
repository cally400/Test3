import cloudscraper
import random
import string
import os
import logging
import time
from datetime import datetime, timedelta
from typing import Tuple, Optional
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
        self._init_scraper()  # تهيئة السكرابر عند البداية

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME", "twd_bot@agent.nsp")
        self.PASSWORD = os.getenv("AGENT_PASSWORD", "Twd@@123")
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
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        )
        self.REFERER = self.ORIGIN + "/dashboard"
        self.CAPTCHA_API_KEY = os.getenv("API_KEY_2CAPTCHA", "")

    def _init_scraper(self):
        """تهيئة cloudscraper مع دعم 2Captcha"""
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
            captcha={'provider': '2captcha', 'api_key': self.CAPTCHA_API_KEY}
        )
        if self.session_cookies and self._is_session_valid():
            self.scraper.cookies.update(self.session_cookies)
            self.is_logged_in = True
            self.logger.info("✅ تم استعادة الجلسة من الذاكرة")
        else:
            self.is_logged_in = False
            self.session_cookies = {}

    def _is_session_valid(self):
        if not self.session_expiry or not self.last_login_time:
            return False
        return datetime.now() < self.session_expiry

    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER
        }

    def _check_captcha(self, response):
        """التحقق من وجود كابتشا أو challenge"""
        text = response.text.lower()
        if 'captcha' in text or 'cf_chl_rt' in text or 'cloudflare' in text:
            self.logger.warning("تم اكتشاف كابتشا في الاستجابة")
            return True
        return False

    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                self.ensure_login()
                result = func(self, *args, **kwargs)
                if isinstance(result, tuple) and len(result) >= 2:
                    status, data = result[0], result[1]
                    if status == 403 or (isinstance(data, dict) and 'captcha' in str(data).lower()):
                        self.logger.warning("تم اكتشاف كابتشا، إعادة المحاولة بعد 5 ثواني...")
                        time.sleep(5)
                        self.is_logged_in = False
                        self.session_cookies = {}
                        self.ensure_login()
                        return func(self, *args, **kwargs)
                return result
            except Exception as e:
                self.logger.error(f"خطأ في {func.__name__}: {str(e)}")
                return None, {"error": str(e)}
        return wrapper

    def login(self):
        if not self.scraper:
            self._init_scraper()
        payload = {"username": self.USERNAME, "password": self.PASSWORD}
        try:
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS['signin'],
                json=payload,
                headers=self._get_headers()
            )
            if not self._check_captcha(resp):
                self.logger.info("✅ تم تخطي الكابتشا بنجاح")
            data = resp.json()
            if data.get("result", False):
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=30)
                self.last_login_time = datetime.now()
                self.is_logged_in = True
                self.logger.info("✅ تم تسجيل الدخول وحفظ الجلسة")
                return True, data
            else:
                error_msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول")
                self.logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
                return False, data
        except Exception as e:
            self.logger.error(f"❌ حدث خطأ في تسجيل الدخول: {str(e)}")
            return False, {"error": str(e)}

    def ensure_login(self):
        if self._is_session_valid() and self.is_logged_in:
            return True
        self.logger.info("🔄 الجلسة منتهية، جاري تسجيل الدخول...")
        success, data = self.login()
        if not success:
            error_msg = data.get("error", data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول"))
            raise Exception(f"❌ فشل تسجيل الدخول: {error_msg}")
        return True

    @with_retry
    def create_player(self, login=None, password=None):
        login = login or "u" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(7))
        password = password or "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        email = f"{login}@example.com"
        payload = {"player": {"email": email, "password": password, "parentId": self.PARENT_ID, "login": login}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['create'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            player_id = self.get_player_id(login)
            return resp.status_code, data, login, password, player_id
        except Exception:
            return resp.status_code, {}, login, password, None

    @with_retry
    def get_player_id(self, login: str) -> Optional[str]:
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            for record in records:
                if record.get("username") == login:
                    return record.get("playerId")
        except Exception:
            pass
        return None
    @with_retry
    def deposit_to_player(self, player_id: str, amount: float) -> Tuple[int, dict]:
        """إيداع رصيد للاعب"""
        payload = {
            "amount": amount,
            "comment": "Deposit from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['deposit'],
            json=payload,
            headers=self._get_headers()
        )
        if self._check_captcha(resp):
            self.logger.info("🔄 كابتشا أثناء الإيداع، إعادة المحاولة...")
            self.ensure_login()
            return self.deposit_to_player(player_id, amount)
        try:
            data = resp.json()
            return resp.status_code, data
        except Exception:
            return resp.status_code, {}

    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float) -> Tuple[int, dict]:
        """سحب رصيد من اللاعب"""
        payload = {
            "amount": amount,
            "comment": "Withdrawal from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['withdraw'],
            json=payload,
            headers=self._get_headers()
        )
        if self._check_captcha(resp):
            self.logger.info("🔄 كابتشا أثناء السحب، إعادة المحاولة...")
            self.ensure_login()
            return self.withdraw_from_player(player_id, amount)
        try:
            data = resp.json()
            return resp.status_code, data
        except Exception:
            return resp.status_code, {}

    @with_retry
    def get_player_balance(self, player_id: str) -> Tuple[int, dict, float]:
        """الحصول على رصيد اللاعب"""
        payload = {"playerId": str(player_id)}
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['balance'],
            json=payload,
            headers=self._get_headers()
        )
        if self._check_captcha(resp):
            self.logger.info("🔄 كابتشا أثناء الحصول على الرصيد، إعادة المحاولة...")
            self.ensure_login()
            return self.get_player_balance(player_id)
        try:
            data = resp.json()
            results = data.get("result", [])
            balance = results[0].get("balance", 0) if isinstance(results, list) and results else 0
            return resp.status_code, data, balance
        except Exception:
            return resp.status_code, {}, 0

    @with_retry
    def get_all_players(self) -> list:
        """الحصول على جميع اللاعبين"""
        payload = {"page": 1, "pageSize": 100, "filter": {}}
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._get_headers()
        )
        if self._check_captcha(resp):
            self.logger.info("🔄 كابتشا أثناء جلب جميع اللاعبين، إعادة المحاولة...")
            self.ensure_login()
            return self.get_all_players()
        try:
            data = resp.json()
            return data.get("result", {}).get("records", [])
        except Exception:
            return []

