import cloudscraper
import random
import string
import os
import logging
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional, Union
import json
from functools import wraps

class IChancyAPI:
    def __init__(self):
        self._setup_logging()
        self._load_config()
        self.scraper = None
        self.is_logged_in = False
        self.session_cookies = {}  # تخزين الكوكيز في الذاكرة
        self.session_expiry = None  # وقت انتهاء الجلسة
        self.last_login_time = None  # وقت آخر تسجيل دخول
        
    def _setup_logging(self):
        """تهيئة نظام التسجيل - بدون ملفات"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()  # فقط للشاشة
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        """تحميل الإعدادات"""
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
        """تهيئة السكرابر مع استعادة الجلسة من الذاكرة"""
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        
        # استعادة الكوكيز من الذاكرة إذا كانت الجلسة سارية
        if self.session_cookies and self._is_session_valid():
            self.scraper.cookies.update(self.session_cookies)
            self.is_logged_in = True
            self.logger.info("✅ تم استعادة الجلسة من الذاكرة")
        else:
            self.is_logged_in = False
            self.session_cookies = {}

    def _is_session_valid(self):
        """التحقق من صلاحية الجلسة"""
        if not self.session_expiry or not self.last_login_time:
            return False
            
        # الجلسة صالحة لمدة 30 دقيقة
        session_duration = timedelta(minutes=30)
        max_session_age = timedelta(hours=2)
        
        time_since_login = datetime.now() - self.last_login_time
        
        return (datetime.now() < self.session_expiry and 
                time_since_login < max_session_age)

    def _get_headers(self):
        """الحصول على هيدرات الطلب"""
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER
        }

    def _log_captcha_success(self):
        """تسجيل نجاح تخطي الكابتشا - في الذاكرة فقط"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"{timestamp} - تم تخطي الكابتشا بنجاح"
        self.logger.info(message)

    def _check_captcha(self, response):
        """التحقق من وجود كابتشا"""
        if 'captcha' in response.text.lower() or 'cloudflare' in response.text.lower():
            self.logger.warning("تم اكتشاف كابتشا في الاستجابة")
            return True
        return False

    def with_retry(func):
        """مُعدِّل لإعادة المحاولة"""
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
        """تسجيل دخول الوكيل مع حفظ الجلسة في الذاكرة"""
        if not self.scraper:
            self._init_scraper()
            
        payload = {
            "username": self.USERNAME,
            "password": self.PASSWORD
        }

        try:
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS['signin'],
                json=payload,
                headers=self._get_headers()
            )

            if not self._check_captcha(resp):
                self._log_captcha_success()

            data = resp.json()

            if data.get("result", False):
                # حفظ الجلسة في الذاكرة
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=30)
                self.last_login_time = datetime.now()
                self.is_logged_in = True
                
                self.logger.info("✅ تم تسجيل الدخول وحفظ الجلسة في الذاكرة")
                self.logger.info(f"   الجلسة صالحة حتى: {self.session_expiry.strftime('%H:%M:%S')}")
                return True, data
            else:
                error_msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول")
                self.logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
                return False, data

        except Exception as e:
            self.logger.error(f"❌ حدث خطأ في تسجيل الدخول: {str(e)}")
            return False, {"error": str(e)}

    def ensure_login(self):
        """التأكد من تسجيل الدخول مع إعادة الاتصال إذا لزم"""
        if not self.scraper:
            self._init_scraper()
            
        if self._is_session_valid() and self.is_logged_in:
            self.logger.debug("✅ الجلسة سارية بالفعل")
            return True
            
        self.logger.info("🔄 الجلسة منتهية أو غير موجودة، جاري تسجيل الدخول...")
        success, data = self.login()
        
        if not success:
            error_msg = data.get("error", data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول"))
            raise Exception(f"❌ فشل في تسجيل الدخول: {error_msg}")
            
        return True

    @with_retry
    def create_player(self, login=None, password=None) -> Tuple[int, dict, str, str, Optional[str]]:
        """إنشاء لاعب جديد"""
        login = login or "u" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(7))
        password = password or "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        email = f"{login}@example.com"

        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": self.PARENT_ID,
                "login": login
            }
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['create'],
            json=payload,
            headers=self._get_headers()
        )

        try:
            data = resp.json()
            player_id = self.get_player_id(login)
            return resp.status_code, data, login, password, player_id
        except Exception:
            return resp.status_code, {}, login, password, None

    @with_retry
    def get_player_id(self, login: str) -> Optional[str]:
        """الحصول على معرف اللاعب"""
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"login": login}
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._get_headers()
        )

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
        """إنشاء لاعب ببيانات محددة"""
        email = f"{login}@agint.nsp"
        # التأكد من تفرد الإيميل
        suffix = 1
        while self.check_email_exists(email):
            email = f"{login}_{suffix}@agint.nsp"
            suffix += 1

        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": self.PARENT_ID,
                "login": login
            }
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['create'],
            json=payload,
            headers=self._get_headers()
        )

        try:
            data = resp.json()
            player_id = self.get_player_id(login)
            return resp.status_code, data, player_id, email
        except Exception:
            return resp.status_code, {}, None, email

    @with_retry
    def check_email_exists(self, email: str) -> bool:
        """التحقق من وجود إيميل"""
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"email": email}
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._get_headers()
        )

        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            return any(record.get("email") == email for record in records)
        except Exception:
            return False

    @with_retry
    def check_player_exists(self, login: str) -> bool:
        """التحقق من وجود لاعب"""
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"login": login}
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._get_headers()
        )

        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            return any(record.get("username") == login for record in records)
        except Exception:
            return False

    @with_retry
    def deposit_to_player(self, player_id: str, amount: float) -> Tuple[int, dict]:
    """إيداع رصيد للاعب مع التسجيل"""
    self.logger.info(f"🚀 بدء إيداع: {amount} NSP للاعب {player_id}")
    
    payload = {
        "amount": amount,
        "comment": f"Deposit from Telegram Bot - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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

    try:
        data = resp.json()
        if resp.status_code == 200:
            self.logger.info(f"✅ إيداع ناجح: {amount} NSP للاعب {player_id}")
        else:
            self.logger.error(f"❌ فشل الإيداع: {resp.status_code} - {data}")
        return resp.status_code, data
    except Exception as e:
        self.logger.error(f"❌ خطأ في الإيداع: {e}")
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
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {}
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._get_headers()
        )

        try:
            data = resp.json()
            return data.get("result", {}).get("records", [])
        except Exception:
            return []
