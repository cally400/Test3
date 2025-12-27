# ichancy_api.py - النسخة المعدلة مع Redis والمنطق الصحيح
import cloudscraper
import os
import logging
import time
import json
import redis
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional, Union
from functools import wraps

# =========================
# Global API Instance مع Redis
# =========================
_global_api_instance = None

def get_api_instance():
    """إرجاع نسخة واحدة مشتركة من API مع Redis"""
    global _global_api_instance
    if _global_api_instance is None:
        _global_api_instance = IChancyAPI()
    return _global_api_instance

class IChancyAPI:
    """إدارة جلسة IChancy مع Redis - باستخدام المنطق القديم الصحيح"""
    
    def __init__(self):
        self._setup_logging()
        self._load_config()
        self.scraper = None
        self.redis = None
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None
        
        # مفاتيح Redis
        self.REDIS_SESSION_KEY = "ichancy:global_session"
        self.REDIS_LOCK_KEY = "ichancy:login_lock"
        
        self._init_redis()
        self._init_scraper()
        self._load_session_from_redis()
    
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)
    
    def _load_config(self):
        """تحميل الإعدادات - بنفس منطق النسخة القديمة"""
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
        self.PARENT_ID = os.getenv("PARENT_ID")
        
        # ⚠️ نفس ORIGIN الذي كان يعمل
        self.ORIGIN = os.getenv("ICHANCY_ORIGIN", "https://agents.ichancy.com")
        
        # ⚠️ نفس ENDPOINTS التي كانت تعمل (باستخدام statistics)
        self.ENDPOINTS = {
            'signin': "/global/api/User/signIn",
            'create': "/global/api/Player/registerPlayer",
            'statistics': "/global/api/Statistics/getPlayersStatisticsPro",  # ✅ هذا المهم
            'deposit': "/global/api/Player/depositToPlayer",
            'withdraw': "/global/api/Player/withdrawFromPlayer",
            'balance': "/global/api/Player/getPlayerBalanceById"
        }
        
        # ⚠️ نفس User-Agent الذي كان يعمل
        self.USER_AGENT = (
            "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.5249.126 Mobile Safari/537.36"
        )
        
        self.REFERER = self.ORIGIN + "/dashboard"  # ⚠️ /dashboard كما في القديم
        self.REQUEST_TIMEOUT = 30
    
    def _init_redis(self):
        """تهيئة Redis"""
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            self.logger.error("❌ REDIS_URL غير موجود")
            raise RuntimeError("REDIS_URL مطلوب")
        
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            self.logger.info("✅ Redis connected successfully")
        except Exception as e:
            self.logger.error(f"❌ فشل الاتصال بـ Redis: {e}")
            raise
    
    def _init_scraper(self):
        """تهيئة cloudscraper - بنفس إعدادات النسخة القديمة"""
        if self.scraper:
            return
        
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                },
                delay=5  # تأخير بسيط
            )
            self.logger.info("✅ CloudScraper initialized")
        except Exception as e:
            self.logger.error(f"❌ فشل تهيئة CloudScraper: {e}")
            raise
    
    def _get_headers(self):
        """نفس هيدرات النسخة القديمة"""
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER
        }
    
    # =========================
    # إدارة الجلسة مع Redis
    # =========================
    def _is_session_valid(self):
        """التحقق من صلاحية الجلسة"""
        if not self.session_expiry or not self.last_login_time:
            return False
        
        # نفس منطق النسخة القديمة
        session_duration = timedelta(minutes=30)
        max_session_age = timedelta(hours=2)
        time_since_login = datetime.now() - self.last_login_time
        
        return (datetime.now() < self.session_expiry and 
                time_since_login < max_session_age)
    
    def _load_session_from_redis(self):
        """تحميل الجلسة من Redis"""
        try:
            data = self.redis.get(self.REDIS_SESSION_KEY)
            if not data:
                self.logger.info("ℹ️ لا توجد جلسة في Redis")
                return
            
            session = json.loads(data)
            self.session_cookies = session.get("cookies", {})
            
            if session.get("expiry"):
                self.session_expiry = datetime.fromisoformat(session["expiry"])
            if session.get("last_login"):
                self.last_login_time = datetime.fromisoformat(session["last_login"])
            
            # تحديث الكوكيز في السكرابر
            if self.scraper and self.session_cookies:
                self.scraper.cookies.update(self.session_cookies)
            
            self.is_logged_in = self._is_session_valid()
            
            if self.is_logged_in:
                self.logger.info("✅ تم تحميل الجلسة من Redis")
            else:
                self.logger.info("ℹ️ الجلسة المخزنة منتهية الصلاحية")
                
        except Exception as e:
            self.logger.error(f"❌ فشل تحميل الجلسة من Redis: {e}")
    
    def _save_session_to_redis(self):
        """حفظ الجلسة في Redis"""
        try:
            data = {
                "cookies": self.session_cookies,
                "expiry": self.session_expiry.isoformat() if self.session_expiry else None,
                "last_login": self.last_login_time.isoformat() if self.last_login_time else None
            }
            
            # صلاحية الجلسة في Redis: 30 دقيقة
            self.redis.set(self.REDIS_SESSION_KEY, json.dumps(data), ex=1800)
            self.logger.info("💾 تم حفظ الجلسة في Redis")
        except Exception as e:
            self.logger.error(f"❌ فشل حفظ الجلسة في Redis: {e}")
    
    def _invalidate_session(self):
        """إبطال الجلسة"""
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None
        
        try:
            self.redis.delete(self.REDIS_SESSION_KEY)
            self.logger.warning("♻️ تم إبطال الجلسة")
        except:
            pass
    
    # =========================
    # تسجيل الدخول (بنفس منطق النسخة القديمة)
    # =========================
    def login(self):
        """تسجيل دخول - بنفس منطق النسخة القديمة"""
        if not self.scraper:
            self._init_scraper()
        
        # 🔒 منع تسجيلات الدخول المتزامنة
        if not self.redis.set(self.REDIS_LOCK_KEY, "1", nx=True, ex=60):
            self.logger.info("⏳ انتظار تسجيل دخول آخر...")
            time.sleep(3)
            self._load_session_from_redis()
            if self.is_logged_in:
                return True, {"status": True, "result": True}
        
        try:
            self.logger.info(f"🚀 محاولة تسجيل الدخول إلى {self.ORIGIN}")
            
            payload = {
                "username": self.USERNAME,
                "password": self.PASSWORD
            }
            
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS['signin'],
                json=payload,
                headers=self._get_headers(),
                timeout=self.REQUEST_TIMEOUT
            )
            
            self.logger.info(f"📡 استجابة تسجيل الدخول: {resp.status_code}")
            
            if resp.status_code != 200:
                self.logger.error(f"❌ فشل تسجيل الدخول: HTTP {resp.status_code}")
                if resp.text:
                    self.logger.error(f"📄 محتوى: {resp.text[:200]}")
                return False, {"error": f"HTTP {resp.status_code}"}
            
            try:
                data = resp.json()
            except:
                self.logger.error(f"❌ استجابة غير صالحة: {resp.text[:200]}")
                return False, {"error": "استجابة غير صالحة"}
            
            # ⚠️ التحقق بنفس طريقة النسخة القديمة
            if data.get("result", False):
                # ✅ تسجيل الدخول ناجح
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=30)
                self.last_login_time = datetime.now()
                self.is_logged_in = True
                
                # حفظ الجلسة في Redis
                self._save_session_to_redis()
                
                self.logger.info("✅ تم تسجيل الدخول بنجاح")
                return True, data
            else:
                error_msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول")
                self.logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
                return False, data
                
        except Exception as e:
            self.logger.error(f"❌ استثناء في تسجيل الدخول: {e}")
            return False, {"error": str(e)}
        finally:
            # 🔓 تحرير القفل
            try:
                self.redis.delete(self.REDIS_LOCK_KEY)
            except:
                pass
    
    def ensure_login(self):
        """التأكد من تسجيل الدخول"""
        if self._is_session_valid() and self.is_logged_in:
            self.logger.debug("✅ الجلسة سارية")
            return True
        
        # محاولة تحميل من Redis
        self._load_session_from_redis()
        
        if self._is_session_valid() and self.is_logged_in:
            self.logger.info("✅ تم استعادة الجلسة من Redis")
            return True
        
        self.logger.info("🔑 الجلسة غير نشطة، جاري تسجيل الدخول...")
        success, data = self.login()
        
        if not success:
            error_msg = data.get("error", data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول"))
            raise Exception(f"❌ فشل في تسجيل الدخول: {error_msg}")
            
        return True
    
    # =========================
    # ديكورات ووظائف API (بنفس منطق النسخة القديمة)
    # =========================
    def with_retry(func):
        """مُعدِّل لإعادة المحاولة"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                self.ensure_login()
                return func(self, *args, **kwargs)
            except Exception as e:
                self.logger.error(f"خطأ في {func.__name__}: {str(e)}")
                
                # محاولة إعادة تسجيل الدخول
                self._invalidate_session()
                try:
                    self.ensure_login()
                    return func(self, *args, **kwargs)
                except Exception as e2:
                    self.logger.error(f"❌ فشل إعادة المحاولة: {e2}")
                    return None, {"error": str(e2)}
        return wrapper
    
    @with_retry
    def check_player_exists(self, login: str) -> bool:
        """✅ التحقق من وجود اللاعب - باستخدام statistics كما في النسخة القديمة"""
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"login": login}
        }
        
        self.logger.info(f"🔍 التحقق من اللاعب: {login}")
        
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT
        )
        
        self.logger.info(f"📡 استجابة التحقق: HTTP {resp.status_code}")
        
        # إذا كان هناك خطأ 403، لا تعتبره أن اللاعب موجود
        if resp.status_code == 403:
            self.logger.warning(f"⚠️ Cloudflare حظر التحقق (403)")
            return False  # ⚠️ مهم: False وليس True
        
        if resp.status_code != 200:
            self.logger.warning(f"⚠️ استجابة غير 200: HTTP {resp.status_code}")
            return False
        
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            exists = any(record.get("username") == login for record in records)
            self.logger.info(f"ℹ️ نتيجة التحقق: اللاعب '{login}' موجود = {exists}")
            return exists
        except Exception as e:
            self.logger.error(f"❌ خطأ في تحليل الاستجابة: {e}")
            return False
    
    @with_retry
    def create_player(self, login: str, password: str) -> Tuple[int, dict, Optional[str]]:
        """إنشاء لاعب جديد - يُرجع 3 قيم كما يتوقع ichancy_create_account.py"""
        email = f"{login}@agent.nsp"
        
        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": self.PARENT_ID,
                "login": login
            }
        }
        
        self.logger.info(f"👤 محاولة إنشاء لاعب: {login}")
        
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['create'],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT
        )
        
        self.logger.info(f"📡 استجابة الإنشاء: HTTP {resp.status_code}")
        
        try:
            data = resp.json()
            player_id = None
            
            if data.get("status"):
                # محاولة الحصول على player_id
                player_id = self.get_player_id(login)
            
            return resp.status_code, data, player_id
        except Exception:
            return resp.status_code, {}, None
    
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
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT
        )
        
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            for record in records:
                if record.get("username") == login:
                    player_id = record.get("playerId")
                    self.logger.info(f"✅ تم العثور على معرف اللاعب: {player_id}")
                    return player_id
        except Exception as e:
            self.logger.error(f"❌ خطأ في الحصول على معرف اللاعب: {e}")
        
        self.logger.warning(f"⚠️ لم يتم العثور على معرف للاعب: {login}")
        return None
    
    # باقي الدوال (deposit, withdraw, etc.) يمكن إضافتها هنا
