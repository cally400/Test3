import cloudscraper
import os
import logging
import json
import time
from datetime import datetime, timedelta
import threading

class SharedIChancyAPI:
    # متغيرات عامة للمشاركة بين جميع النسخ
    _shared_session = None
    _shared_cookies = {}
    _is_logged_in = False
    _session_expiry = None
    _last_activity = None
    _lock = threading.Lock()
    _instance = None
    
    def __new__(cls):
        """Singleton pattern - نسخة واحدة فقط"""
        if cls._instance is None:
            cls._instance = super(SharedIChancyAPI, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._setup_logging()
        self._load_config()
        self._initialized = True
        
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - IChancyAPI - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME", "twd_bot@agent.nsp")
        self.PASSWORD = os.getenv("AGENT_PASSWORD", "Twd@@123")
        self.PARENT_ID = os.getenv("PARENT_ID", "2470819")
        
        self.BASE_URL = "https://agents.ichancy.com"
        self.ENDPOINTS = {
            'signin': "/global/api/User/signIn",
            'create': "/global/api/Player/registerPlayer",
            'statistics': "/global/api/Statistics/getPlayersStatisticsPro",
            'balance': "/global/api/Player/getPlayerBalanceById"
        }
        
        self.USER_AGENT = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def _init_scraper(self):
        """تهيئة السكرابر المشترك"""
        with self._lock:
            if self._shared_session is None:
                try:
                    self._shared_session = cloudscraper.create_scraper(
                        browser={
                            'browser': 'chrome',
                            'platform': 'windows',
                            'mobile': False
                        }
                    )
                    self.logger.info("✅ تم تهيئة السكرابر المشترك")
                except Exception as e:
                    self.logger.error(f"❌ فشل في تهيئة السكرابر: {e}")
                    raise
            return self._shared_session

    def _is_session_valid(self):
        """التحقق من صلاحية الجلسة المشتركة"""
        with self._lock:
            if not self._is_logged_in or not self._session_expiry:
                return False
            
            # الجلسة صالحة لمدة 20 دقيقة
            if datetime.now() > self._session_expiry:
                self.logger.info("انتهت صلاحية الجلسة المشتركة")
                return False
            
            # إذا مر أكثر من 15 دقيقة بدون نشاط، نعتبرها منتهية
            if self._last_activity and (datetime.now() - self._last_activity) > timedelta(minutes=15):
                self.logger.info("الجلسة المشتركة غير نشطة")
                return False
            
            return True

    def _update_activity(self):
        """تحديث وقت النشاط الأخير"""
        with self._lock:
            self._last_activity = datetime.now()

    def login(self):
        """تسجيل دخول مرة واحدة للجميع"""
        with self._lock:
            # إذا كانت الجلسة سارية، لا داعي لتسجيل دخول جديد
            if self._is_session_valid():
                self.logger.info("✅ الجلسة المشتركة سارية بالفعل")
                return True, {"result": True, "message": "Already logged in"}
            
            # تهيئة السكرابر إذا لم يكن موجوداً
            if self._shared_session is None:
                self._init_scraper()
            
            payload = {
                "username": self.USERNAME,
                "password": self.PASSWORD
            }
            
            try:
                url = self.BASE_URL + self.ENDPOINTS['signin']
                self.logger.info("🔄 محاولة تسجيل الدخول (جلسة مشتركة)...")
                
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": self.USER_AGENT,
                    "Origin": self.BASE_URL,
                    "Referer": self.BASE_URL + "/dashboard"
                }
                
                resp = self._shared_session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                self.logger.info(f"استجابة تسجيل الدخول: {resp.status_code}")
                
                try:
                    data = resp.json()
                    
                    if data.get("result", False):
                        # حفظ الكوكيز والجلسة
                        self._shared_cookies = dict(self._shared_session.cookies)
                        self._session_expiry = datetime.now() + timedelta(minutes=20)
                        self._last_activity = datetime.now()
                        self._is_logged_in = True
                        
                        self.logger.info("✅ تم تسجيل الدخول بنجاح (جلسة مشتركة)")
                        self.logger.info(f"   الجلسة صالحة حتى: {self._session_expiry.strftime('%H:%M:%S')}")
                        return True, data
                    else:
                        error_msg = "فشل تسجيل الدخول"
                        if "notification" in data and isinstance(data["notification"], list):
                            error_msg = data["notification"][0].get("content", error_msg)
                        self.logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
                        return False, data
                        
                except json.JSONDecodeError:
                    self.logger.error(f"❌ استجابة غير صالحة: {resp.text[:200]}")
                    return False, {"error": "استجابة غير صالحة"}
                    
            except Exception as e:
                self.logger.error(f"❌ خطأ في تسجيل الدخول: {str(e)}")
                return False, {"error": str(e)}

    def ensure_login(self):
        """التأكد من أن الجلسة المشتركة نشطة"""
        with self._lock:
            if self._is_session_valid():
                self._update_activity()
                return True
            
            self.logger.info("🔄 الجلسة المشتركة منتهية، جاري إعادة الاتصال...")
            success, data = self.login()
            
            if not success:
                error_msg = "فشل في الاتصال بالنظام"
                if isinstance(data, dict):
                    if 'error' in data:
                        error_msg = data['error']
                    elif 'notification' in data and data['notification']:
                        error_msg = data['notification'][0].get('content', error_msg)
                
                self.logger.error(f"❌ {error_msg}")
                raise Exception(f"فشل في الاتصال: {error_msg}")
            
            return True

    # الدوال الأساسية
    def check_player_exists(self, login: str) -> bool:
        """التحقق من وجود لاعب"""
        self.ensure_login()
        
        with self._lock:
            payload = {
                "page": 1,
                "pageSize": 100,
                "filter": {"login": login}
            }
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": self.USER_AGENT,
                "Origin": self.BASE_URL,
                "Referer": self.BASE_URL + "/dashboard"
            }
            
            try:
                resp = self._shared_session.post(
                    self.BASE_URL + self.ENDPOINTS['statistics'],
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                data = resp.json()
                records = data.get("result", {}).get("records", [])
                return any(record.get("username") == login for record in records)
                
            except Exception as e:
                self.logger.error(f"خطأ في check_player_exists: {e}")
                return False

    def create_player_with_credentials(self, login: str, password: str):
        """إنشاء لاعب ببيانات محددة"""
        self.ensure_login()
        
        with self._lock:
            # إنشاء إيميل فريد
            email = f"{login}@agent.nsp"
            
            payload = {
                "player": {
                    "email": email,
                    "password": password,
                    "parentId": self.PARENT_ID,
                    "login": login
                }
            }
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": self.USER_AGENT,
                "Origin": self.BASE_URL,
                "Referer": self.BASE_URL + "/dashboard"
            }
            
            try:
                resp = self._shared_session.post(
                    self.BASE_URL + self.ENDPOINTS['create'],
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                status_code = resp.status_code
                
                try:
                    data = resp.json()
                except:
                    data = {}
                
                # الحصول على player_id
                player_id = None
                if status_code == 200 and data.get("result", False):
                    time.sleep(0.5)
                    player_id = self.get_player_id(login)
                
                return status_code, data, player_id, email
                
            except Exception as e:
                self.logger.error(f"خطأ في create_player_with_credentials: {e}")
                return 500, {"error": str(e)}, None, email

    def get_player_id(self, login: str):
        """الحصول على معرف اللاعب"""
        self.ensure_login()
        
        with self._lock:
            payload = {
                "page": 1,
                "pageSize": 100,
                "filter": {"login": login}
            }
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": self.USER_AGENT,
                "Origin": self.BASE_URL,
                "Referer": self.BASE_URL + "/dashboard"
            }
            
            try:
                resp = self._shared_session.post(
                    self.BASE_URL + self.ENDPOINTS['statistics'],
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                data = resp.json()
                records = data.get("result", {}).get("records", [])
                
                for record in records:
                    if record.get("username") == login:
                        return record.get("playerId")
                        
                return None
                
            except Exception as e:
                self.logger.error(f"خطأ في get_player_id: {e}")
                return None

# إنشاء نسخة واحدة مشتركة
shared_api = SharedIChancyAPI()
