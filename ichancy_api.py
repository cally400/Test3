import cloudscraper
import random
import string
import os
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional
import json
from functools import wraps
import threading
import time
import requests

# إعدادات إشعارات تيليغرام
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def notify_admin(message: str):
    """إرسال إشعار إلى المشرف عبر تيليغرام"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except Exception as e:
        print(f"❌ خطأ في إرسال إشعار تيليغرام: {e}")

class IChancyAPI:
    def __init__(self):
        self._setup_logging()
        self._load_config()
        self.scraper = None
        self.is_logged_in = False
        self.session_cookies = {}  
        self.session_expiry = None  
        self.last_login_time = None  

        # تفعيل Watchdog للجلسة
        threading.Thread(target=self._session_watchdog, daemon=True).start()

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
            "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.5249.126 Mobile Safari/537.36"
        )
        self.REFERER = self.ORIGIN + "/dashboard"

    def _init_scraper(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
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
        session_duration = timedelta(minutes=30)
        max_session_age = timedelta(hours=2)
        time_since_login = datetime.now() - self.last_login_time
        return (datetime.now() < self.session_expiry and time_since_login < max_session_age)

    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER
        }

    def _check_captcha(self, response):
        if 'captcha' in response.text.lower() or 'cloudflare' in response.text.lower():
            self.logger.warning("تم اكتشاف كابتشا في الاستجابة")
            return True
        return False

    def _log_captcha_success(self):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logger.info(f"{timestamp} - تم تخطي الكابتشا بنجاح")

    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                self.ensure_login()
                result = func(self, *args, **kwargs)
                if result is None:
                    return None
                if isinstance(result, tuple) and len(result) >= 2:
                    status, data = result[0], result[1]
                    if status == 403 or (isinstance(data, dict) and 'captcha' in str(data).lower()):
                        self.logger.warning("تم اكتشاف كابتشا، جاري إعادة المحاولة...")
                        self.is_logged_in = False
                        self.session_cookies = {}
                        self.ensure_login()
                        result = func(self, *args, **kwargs)
                return result
            except Exception as e:
                self.logger.error(f"خطأ في تنفيذ الدالة {func.__name__}: {str(e)}")
                return None, {"error": str(e)}
        return wrapper

    def login(self):
        if not self.scraper:
            self._init_scraper()
        payload = {"username": self.USERNAME, "password": self.PASSWORD}
        try:
            resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['signin'], json=payload, headers=self._get_headers())
            if not self._check_captcha(resp):
                self._log_captcha_success()
            data = resp.json()
            if data.get("result", False):
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=30)
                self.last_login_time = datetime.now()
                self.is_logged_in = True
                self.logger.info("✅ تم تسجيل الدخول وحفظ الجلسة")
                notify_admin("♻️ تم إعادة تسجيل الدخول بنجاح في IChancy API.")
                return True, data
            else:
                error_msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول")
                self.logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
                notify_admin(f"❌ فشل تسجيل الدخول: {error_msg}")
                return False, data
        except Exception as e:
            self.logger.error(f"❌ حدث خطأ في تسجيل الدخول: {str(e)}")
            notify_admin(f"❌ حدث خطأ في تسجيل الدخول: {str(e)}")
            return False, {"error": str(e)}

    def ensure_login(self):
        if not self.scraper:
            self._init_scraper()
        if self._is_session_valid() and self.is_logged_in:
            return True
        self.logger.info("🔄 الجلسة منتهية أو غير موجودة، جاري تسجيل الدخول...")
        success, data = self.login()
        if not success:
            error_msg = data.get("error", data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول"))
            raise Exception(f"❌ فشل في تسجيل الدخول: {error_msg}")
        return True

    def _session_watchdog(self, interval=60):
        """خيط خلفي لإبقاء الجلسة حية"""
        while True:
            try:
                if not self._is_session_valid() or not self.is_logged_in:
                    self.logger.warning("♻️ Watchdog: إعادة تسجيل الدخول تلقائياً")
                    self.ensure_login()
            except Exception as e:
                self.logger.error(f"❌ خطأ في Watchdog: {str(e)}")
            time.sleep(interval)

    # -------------------- دوال API --------------------

    @with_retry
    def create_player(self, login=None, password=None) -> Tuple[int, dict, str, str, Optional[str]]:
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
    def create_player_with_credentials(self, login: str, password: str) -> Tuple[int, dict, Optional[str], str]:
        email = f"{login}@agint.nsp"
        suffix = 1
        while self.check_email_exists(email):
            email = f"{login}_{suffix}@agint.nsp"
            suffix += 1
        payload = {"player": {"email": email, "password": password, "parentId": self.PARENT_ID, "login": login}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['create'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            player_id = self.get_player_id(login)
            return resp.status_code, data, player_id, email
        except Exception:
            return resp.status_code, {}, None, email

    @with_retry
    def check_email_exists(self, email: str) -> bool:
        payload = {"page": 1, "pageSize": 100, "filter": {"email": email}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            return any(record.get("email") == email for record in records)
        except Exception:
            return False

    @with_retry
    def check_player_exists(self, login: str) -> bool:
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            return any(record.get("username") == login for record in records)
        except Exception:
            return False

    @with_retry
    def deposit_to_player(self, player_id: str, amount: float) -> Tuple[int, dict]:
        payload = {"amount": amount, "comment": "Deposit from API", "playerId": player_id,
                   "currencyCode": "NSP", "currency": "NSP", "moneyStatus": 5}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['deposit'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            return resp.status_code, data
        except Exception:
            return resp.status_code, {}

    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float) -> Tuple[int, dict]:
        payload = {"amount": amount, "comment": "Withdrawal from API", "playerId": player_id,
                   "currencyCode": "NSP", "currency": "NSP", "moneyStatus": 5}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['withdraw'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            return resp.status_code, data
        except Exception:
            return resp.status_code, {}

    @with_retry
    def get_player_balance(self, player_id: str) -> Tuple[int, dict, float]:
        payload = {"playerId": str(player_id)}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['balance'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            results = data.get("result", [])
            balance = results[0].get("balance", 0) if isinstance(results, list) and results else 0
            return resp.status_code, data, balance
        except Exception:
            return resp.status_code, {}, 0

    @with_retry
    def get_all_players(self) -> list:
        payload = {"page": 1, "pageSize": 100, "filter": {}}
        resp = self.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=self._get_headers())
        try:
            data = resp.json()
            return data.get("result", {}).get("records", [])
        except Exception:
            return []

