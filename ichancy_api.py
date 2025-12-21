import cloudscraper
import random
import string
import os
import logging
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional, Union
import json
from functools import wraps
import time
import requests
import threading

class IChancyAPI:
    def __init__(self):
        self._setup_logging()
        self._load_config()
        self.scraper = None
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None
        self.login_attempts = 0
        self.max_login_attempts = 3
        self._login_lock = threading.Lock()  # قفل لمنع تسجيل دخول مزدوج
        self._request_lock = threading.Lock()  # قفل للطلبات
        
    def _setup_logging(self):
        """تهيئة نظام التسجيل"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('ichancy_api.log', encoding='utf-8')
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        """تحميل الإعدادات"""
        self.USERNAME = os.getenv("AGENT_USERNAME", "twd_bot@agent.nsp")
        self.PASSWORD = os.getenv("AGENT_PASSWORD", "Twd@@123")
        self.PARENT_ID = os.getenv("PARENT_ID", "2470819")

        self.ORIGIN = "https://agents.ichancy.com"
        self.BASE_URL = "https://agents.ichancy.com"
        self.ENDPOINTS = {
            'signin': "/global/api/User/signIn",
            'create': "/global/api/Player/registerPlayer",
            'statistics': "/global/api/Statistics/getPlayersStatisticsPro",
            'deposit': "/global/api/Player/depositToPlayer",
            'withdraw': "/global/api/Player/withdrawFromPlayer",
            'balance': "/global/api/Player/getPlayerBalanceById"
        }

        self.USER_AGENT = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        self.REFERER = self.BASE_URL + "/dashboard"

    def _init_scraper(self):
        """تهيئة السكرابر"""
        try:
            with self._login_lock:
                self.scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'mobile': False
                    },
                    delay=5
                )
                
                self.logger.info("✅ تم تهيئة السكرابر بنجاح")
                
        except Exception as e:
            self.logger.error(f"❌ فشل في تهيئة السكرابر: {e}")
            raise

    def _get_headers(self, extra_headers=None):
        """الحصول على هيدرات الطلب"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Connection": "keep-alive"
        }
        
        if extra_headers:
            headers.update(extra_headers)
            
        return headers

    def _is_session_valid(self):
        """التحقق من صلاحية الجلسة"""
        with self._login_lock:
            if not self.session_expiry or not self.last_login_time:
                return False
                
            # تحقق إذا انتهت الجلسة
            if datetime.now() > self.session_expiry:
                self.logger.info("انتهت صلاحية الجلسة")
                return False
                
            # تحقق إذا مر أكثر من 25 دقيقة على آخر تسجيل دخول
            max_session_age = timedelta(minutes=25)
            time_since_login = datetime.now() - self.last_login_time
            
            if time_since_login > max_session_age:
                self.logger.info("الجلسة قديمة جداً")
                return False
                
            return True

    def login(self):
        """تسجيل دخول الوكيل مع منع الازدواجية"""
        with self._login_lock:
            # إذا كانت الجلسة سارية بالفعل، لا داعي لتسجيل دخول جديد
            if self.is_logged_in and self._is_session_valid():
                self.logger.info("✅ الجلسة سارية بالفعل، تخطي تسجيل الدخول")
                return True, {"result": True, "message": "Already logged in"}
            
            self.login_attempts += 1
            
            if self.login_attempts > self.max_login_attempts:
                self.logger.error("❌ تجاوز الحد الأقصى لمحاولات تسجيل الدخول")
                return False, {"error": "تجاوز الحد الأقصى لمحاولات تسجيل الدخول"}
            
            # إعادة تهيئة السكرابر إذا لزم
            if not self.scraper:
                self._init_scraper()
                
            payload = {
                "username": self.USERNAME,
                "password": self.PASSWORD
            }

            try:
                url = self.BASE_URL + self.ENDPOINTS['signin']
                self.logger.info(f"محاولة تسجيل الدخول: {self.login_attempts}/{self.max_login_attempts}")
                
                headers = self._get_headers()
                
                # إضافة timestamp لمنع الطلبات المكررة
                timestamp = int(time.time() * 1000)
                headers["X-Request-Timestamp"] = str(timestamp)
                
                resp = self.scraper.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                self.logger.info(f"استجابة تسجيل الدخول: {resp.status_code}")
                
                # التحقق من نوع المحتوى
                content_type = resp.headers.get('Content-Type', '')
                
                # إذا كانت الاستجابة HTML وليست JSON
                if 'text/html' in content_type.lower():
                    self.logger.warning("الاستجابة هي HTML وليست JSON!")
                    
                    # التحقق من وجود Duplicate login في HTML
                    if 'duplicate login' in resp.text.lower():
                        self.logger.warning("تم اكتشاف Duplicate login في HTML")
                        # ربما نحن مسجلين بالفعل، نعتبر أن الجلسة سارية
                        if self.scraper.cookies:
                            self.session_cookies = dict(self.scraper.cookies)
                            self.session_expiry = datetime.now() + timedelta(minutes=30)
                            self.last_login_time = datetime.now()
                            self.is_logged_in = True
                            self.login_attempts = 0
                            return True, {"result": True, "message": "Already logged in (from HTML)"}
                    
                    return False, {"error": "استجابة غير متوقعة (HTML بدلاً من JSON)"}
                
                # محاولة تحليل JSON
                try:
                    data = resp.json()
                    self.logger.info(f"JSON Response: {data}")
                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ فشل في تحليل JSON: {e}")
                    return False, {"error": f"استجابة غير صالحة: {resp.text[:100]}"}
                
                # التحقق من النتيجة
                if data.get("result", False):
                    self.session_cookies = dict(self.scraper.cookies)
                    self.session_expiry = datetime.now() + timedelta(minutes=30)
                    self.last_login_time = datetime.now()
                    self.is_logged_in = True
                    self.login_attempts = 0
                    
                    self.logger.info(f"✅ تم تسجيل الدخول بنجاح")
                    return True, data
                else:
                    error_msg = "فشل تسجيل الدخول"
                    
                    # التحقق من Duplicate login في JSON
                    if "notification" in data and isinstance(data["notification"], list):
                        for notif in data["notification"]:
                            content = notif.get("content", "").lower()
                            if "duplicate" in content or "already logged" in content:
                                self.logger.warning("Duplicate login detected in JSON response")
                                # إذا كان هناك duplicate login، نعتبر أننا مسجلين
                                if self.scraper.cookies:
                                    self.session_cookies = dict(self.scraper.cookies)
                                    self.session_expiry = datetime.now() + timedelta(minutes=30)
                                    self.last_login_time = datetime.now()
                                    self.is_logged_in = True
                                    self.login_attempts = 0
                                    return True, {"result": True, "message": "Already logged in (duplicate detected)"}
                            error_msg = notif.get("content", error_msg)
                    
                    self.logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
                    return False, data

            except requests.exceptions.Timeout:
                self.logger.error("❌ انتهت مهلة الاتصال")
                return False, {"error": "انتهت مهلة الاتصال بالخادم"}
                
            except requests.exceptions.ConnectionError:
                self.logger.error("❌ خطأ في الاتصال")
                return False, {"error": "لا يمكن الاتصال بالخادم"}
                
            except Exception as e:
                self.logger.error(f"❌ حدث خطأ في تسجيل الدخول: {str(e)}", exc_info=True)
                return False, {"error": str(e)}

    def ensure_login(self):
        """التأكد من تسجيل الدخول مع معالجة الأخطاء"""
        try:
            # إذا كانت الجلسة سارية وصالحة، لا داعي لفعل شيء
            if self.is_logged_in and self._is_session_valid():
                self.logger.debug("✅ الجلسة سارية وصالحة")
                return True
                
            self.logger.info("🔄 الجلسة منتهية أو غير صالحة، جاري تسجيل الدخول...")
            
            success, data = self.login()
            
            if not success:
                error_msg = "فشل تسجيل الدخول"
                if isinstance(data, dict):
                    if 'error' in data:
                        error_msg = data['error']
                    elif 'message' in data:
                        error_msg = data['message']
                
                self.logger.error(f"❌ فشل في تسجيل الدخول: {error_msg}")
                
                # إذا كان الخطأ هو duplicate login، نعتبر أنه ناجح
                if "duplicate" in error_msg.lower() or "already logged" in error_msg.lower():
                    self.logger.warning("⚠️ Duplicate login detected, considering as success")
                    return True
                    
                raise Exception(f"فشل في تسجيل الدخول: {error_msg}")
                
            return True
            
        except Exception as e:
            self.logger.error(f"❌ فشل في ensure_login: {e}")
            raise

    # تحديث الديكوراتور لاستخدام الأقفال
    def with_retry(func):
        """مُعدِّل لإعادة المحاولة"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    with self._request_lock:
                        self.ensure_login()
                        result = func(self, *args, **kwargs)
                        
                    return result
                    
                except Exception as e:
                    self.logger.warning(f"محاولة {attempt + 1} فشلت: {e}")
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(1)  # انتظر قبل إعادة المحاولة
                    
            return None
        return wrapper

    # باقي الدوال تبقى كما هي مع @with_retry
    @with_retry
    def check_player_exists(self, login: str) -> bool:
        """التحقق من وجود لاعب"""
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"login": login}
        }

        with self._request_lock:
            resp = self.scraper.post(
                self.BASE_URL + self.ENDPOINTS['statistics'],
                json=payload,
                headers=self._get_headers()
            )

            try:
                data = resp.json()
                records = data.get("result", {}).get("records", [])
                return any(record.get("username") == login for record in records)
            except Exception as e:
                self.logger.error(f"خطأ في check_player_exists: {e}")
                return False

    @with_retry
    def create_player_with_credentials(self, login: str, password: str) -> Tuple[int, dict, Optional[str], str]:
        """إنشاء لاعب ببيانات محددة"""
        # توليد إيميل فريد
        base_email = f"{login}@agent.nsp"
        email = base_email
        
        suffix = 1
        while self.check_email_exists(email):
            email = f"{login}{suffix}@agent.nsp"
            suffix += 1
            if suffix > 5:
                email = f"{login}_{int(time.time())}@agent.nsp"
                break

        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": self.PARENT_ID,
                "login": login
            }
        }

        self.logger.info(f"محاولة إنشاء لاعب: {login}")
        
        with self._request_lock:
            resp = self.scraper.post(
                self.BASE_URL + self.ENDPOINTS['create'],
                json=payload,
                headers=self._get_headers()
            )

            try:
                data = resp.json()
                player_id = None
                
                if resp.status_code == 200 and data.get("result", False):
                    # انتظر قليلاً ثم احصل على المعرف
                    time.sleep(0.5)
                    player_id = self.get_player_id(login)
                    
                return resp.status_code, data, player_id, email
            except Exception as e:
                self.logger.error(f"خطأ في create_player_with_credentials: {e}")
                return resp.status_code, {}, None, email
