# ichancy_api.py - الإصدار المحسّن
import cloudscraper
import os
import logging
import time
import json
import redis
from datetime import datetime, timedelta
from functools import wraps

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("IChancyAPI")

# =========================
# Global API Instance
# =========================
_global_api_instance = None

def get_api_instance():
    """
    إرجاع نسخة واحدة مشتركة من IChancyAPI لجميع الطلبات
    """
    global _global_api_instance
    if _global_api_instance is None:
        _global_api_instance = IChancyAPI()
    return _global_api_instance

class IChancyAPI:
    """
    🔐 Global Agent Session - إدارة الجلسة المركزية
    """

    def __init__(self):
        self._load_config()
        self.scraper = None
        self.redis = None
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None
        
        # Redis keys
        self.REDIS_SESSION_KEY = "ichancy:global_session"
        self.REDIS_LOCK_KEY = "ichancy:login_lock"
        
        self._init_redis()
        self._init_scraper()
        self._load_session_from_redis()

    # =========================
    # Config
    # =========================
    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
        self.PARENT_ID = os.getenv("PARENT_ID")
        
        # ⚠️ تأكد من أن هذه القيمة صحيحة
        self.ORIGIN = os.getenv("ICHANCY_ORIGIN", "https://agents.ichancy.com")
        
        self.ENDPOINTS = {
            "signin": "/global/api/User/signIn",
            "create": "/global/api/Player/registerPlayer",
            "check_player": "/global/api/Player/checkPlayerExist",
            "statistics": "/global/api/Statistics/getPlayersStatisticsPro",
            "deposit": "/global/api/Player/depositToPlayer",
            "withdraw": "/global/api/Player/withdrawFromPlayer",
            "balance": "/global/api/Player/getPlayerBalanceById",
        }
        
        self.USER_AGENT = (
            "Mozilla/5.0 (Linux; Android 10) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/119.0 Mobile Safari/537.36"
        )
        
        self.REQUEST_TIMEOUT = 25
        
        # ✅ التحقق من وجود المتغيرات البيئية
        if not all([self.USERNAME, self.PASSWORD, self.PARENT_ID]):
            logger.error("❌ متغيرات البيئة AGENT_USERNAME أو AGENT_PASSWORD أو PARENT_ID غير موجودة")
            raise RuntimeError("متغيرات البيئة المطلوبة غير موجودة")

    # =========================
    # Redis
    # =========================
    def _init_redis(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.error("❌ REDIS_URL غير موجود في متغيرات البيئة")
            raise RuntimeError("REDIS_URL غير موجود")
        
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            logger.info("✅ Redis connected successfully")
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بـ Redis: {e}")
            raise

    # =========================
    # Scraper
    # =========================
    def _init_scraper(self):
        if self.scraper:
            return
        
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            logger.info("✅ CloudScraper initialized")
        except Exception as e:
            logger.error(f"❌ فشل تهيئة CloudScraper: {e}")
            raise

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": f"{self.ORIGIN}/login",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    # =========================
    # Session Management
    # =========================
    def _is_session_valid(self):
        if not self.session_expiry:
            return False
        return datetime.utcnow() < self.session_expiry

    def _load_session_from_redis(self):
        try:
            data = self.redis.get(self.REDIS_SESSION_KEY)
            if not data:
                logger.info("ℹ️ لا توجد جلسة مخزنة في Redis")
                return
            
            session = json.loads(data)
            self.session_cookies = session["cookies"]
            self.session_expiry = datetime.fromisoformat(session["expiry"])
            self.last_login_time = datetime.fromisoformat(session["last_login"])
            self.scraper.cookies.update(self.session_cookies)
            self.is_logged_in = self._is_session_valid()
            
            if self.is_logged_in:
                logger.info("✅ تم تحميل الجلسة من Redis")
            else:
                logger.info("ℹ️ الجلسة المخزنة منتهية الصلاحية")
                
        except Exception as e:
            logger.error(f"❌ فشل تحميل الجلسة من Redis: {e}")

    def _save_session_to_redis(self):
        try:
            data = {
                "cookies": self.session_cookies,
                "expiry": self.session_expiry.isoformat(),
                "last_login": self.last_login_time.isoformat(),
            }
            self.redis.set(self.REDIS_SESSION_KEY, json.dumps(data), ex=3600)
            logger.info("💾 تم حفظ الجلسة في Redis")
        except Exception as e:
            logger.error(f"❌ فشل حفظ الجلسة في Redis: {e}")

    def _invalidate_session(self):
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None
        try:
            self.redis.delete(self.REDIS_SESSION_KEY)
            logger.warning("♻️ تم إبطال الجلسة وحذفها من Redis")
        except:
            pass

    # =========================
    # Login
    # =========================
    def login(self):
        # 🔒 منع تسجيلات الدخول المتزامنة
        if not self.redis.set(self.REDIS_LOCK_KEY, "1", nx=True, ex=60):
            logger.info("⏳ جاري انتظار عملية تسجيل دخول أخرى...")
            time.sleep(3)
            self._load_session_from_redis()
            if self.is_logged_in:
                return True
        
        try:
            logger.info(f"🚀 محاولة تسجيل الدخول إلى {self.ORIGIN}")
            
            payload = {
                "username": self.USERNAME,
                "password": self.PASSWORD,
            }
            
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS["signin"],
                json=payload,
                headers=self._headers(),
                timeout=self.REQUEST_TIMEOUT,
            )
            
            logger.info(f"📡 استجابة تسجيل الدخول: {resp.status_code}")
            
            # ✅ طباعة الاستجابة الكاملة لأغراض التصحيح
            if resp.status_code != 200:
                logger.error(f"❌ فشل تسجيل الدخول: HTTP {resp.status_code}")
                logger.error(f"📄 محتوى الاستجابة: {resp.text[:500]}")
                return False
            
            data = resp.json()
            logger.info(f"📊 بيانات استجابة API: {json.dumps(data, indent=2)[:500]}")
            
            if not data.get("result"):
                logger.error(f"❌ فشل تسجيل الدخول: {data.get('message', 'لا توجد رسالة')}")
                return False
            
            # ✅ حفظ بيانات الجلسة
            self.session_cookies = dict(self.scraper.cookies)
            self.session_expiry = datetime.utcnow() + timedelta(minutes=30)
            self.last_login_time = datetime.utcnow()
            self.is_logged_in = True
            
            # ✅ حفظ الجلسة في Redis
            self._save_session_to_redis()
            
            logger.info("✅ تم تسجيل الدخول بنجاح")
            return True
            
        except Exception as e:
            logger.error(f"❌ استثناء أثناء تسجيل الدخول: {e}")
            return False
        finally:
            # 🔓 تحرير القفل
            try:
                self.redis.delete(self.REDIS_LOCK_KEY)
            except:
                pass

    def ensure_login(self):
        if self.is_logged_in and self._is_session_valid():
            logger.info("✅ الجلسة نشطة بالفعل")
            return True
        
        self._load_session_from_redis()
        
        if self.is_logged_in and self._is_session_valid():
            logger.info("✅ تم استعادة الجلسة من Redis")
            return True
        
        logger.info("🔑 الجلسة غير نشطة، جاري تسجيل الدخول...")
        return self.login()

    # =========================
    # Decorator for API calls (IMPROVED VERSION)
    # =========================
    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # ✅ محاولة تسجيل الدخول أولاً
            if not self.ensure_login():
                return (401, {"error": "فشل تسجيل الدخول"})
            
            # ✅ التنفيذ الأول للطلب
            resp = func(self, *args, **kwargs)
            
            # ✅ إعادة المحاولة ONLY إذا كان الخطأ 401 أو 403
            if isinstance(resp, tuple) and resp[0] in (401, 403):
                # ⚠️ تسجيل تفاصيل الخطأ قبل إعادة المحاولة
                func_name = func.__name__
                logger.warning(f"⚠️ [{func_name}] تم رفض الطلب برمز {resp[0]}، جاري إعادة تسجيل الدخول...")
                if len(resp) > 1 and isinstance(resp[1], dict):
                    logger.warning(f"📄 [{func_name}] محتوى استجابة الخطأ: {resp[1]}")
                
                self._invalidate_session()
                
                if self.login():
                    # إعادة التنفيذ بعد تسجيل الدخول الجديد
                    resp = func(self, *args, **kwargs)
                else:
                    return (401, {"error": "فشل إعادة تسجيل الدخول"})
            
            return resp
        return wrapper

    # =========================
    # API Methods
    # =========================
    @with_retry
    def create_player(self, login, password):
        payload = {
            "player": {
                "login": login,
                "password": password,
                "email": f"{login}@agent.nsp",
                "parentId": self.PARENT_ID,
            }
        }
        
        logger.info(f"👤 محاولة إنشاء لاعب: {login}")
        
        r = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["create"],
            json=payload,
            headers=self._headers(),
            timeout=self.REQUEST_TIMEOUT,
        )
        
        logger.info(f"📡 استجابة إنشاء اللاعب: {r.status_code}")
        
        if r.status_code in (401, 403):
            logger.error(f"❌ رفض الوصول: {r.status_code}")
            logger.error(f"📄 محتوى الاستجابة: {r.text[:500]}")
        
        return r.status_code, r.json()

    @with_retry
    def check_player_exists(self, login):
        payload = {"login": login}
        
        # ✅ أضف هذا السطر لتتبع بداية الطلب
        logger.info(f"🔍 [check_player_exists] التحقق من وجود اللاعب: {login}")
        
        r = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["check_player"],
            json=payload,
            headers=self._headers(),
            timeout=self.REQUEST_TIMEOUT,
        )
        
        # ✅ تسجيل تفصيلي للاستجابة بغض النظر عن النتيجة
        logger.info(f"📡 [check_player_exists] استجابة HTTP: {r.status_code}")
        
        # ✅ تسجيل محتوى الاستجابة فقط في حالة الخطأ
        if r.status_code != 200:
            logger.warning(f"⚠️ [check_player_exists] محتوى الاستجابة (غير 200): {r.text[:300]}")
            
            # ⚠️ المعالجة الخاصة: إذا كان الخطأ 403
            if r.status_code == 403:
                logger.error("❌ [check_player_exists] رفض الوصول (403) للتحقق من اللاعب. قد يكون Endpoint خاطئ أو يحتاج صلاحية خاصة.")
                # نُعيد False هنا حتى لا يوقف البوت العملية
                return False
            else:
                # للأخطاء الأخرى غير 403، نرفع الاستثناء كما كان
                logger.error(f"❌ خطأ في التحقق من اللاعب: HTTP {r.status_code}")
                raise Exception(f"HTTP {r.status_code} عند التحقق من اسم المستخدم")
        
        data = r.json()
        exists = data.get("result", {}).get("exists", False)
        logger.info(f"ℹ️ [check_player_exists] نتيجة التحقق: اللاعب '{login}' موجود = {exists}")
        return exists

    @with_retry
    def deposit(self, player_id, amount):
        payload = {
            "playerId": player_id,
            "amount": amount,
            "currency": "NSP",
            "moneyStatus": 5,
        }
        
        logger.info(f"💰 محاولة إيداع: {amount} NSP للاعب {player_id}")
        
        r = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["deposit"],
            json=payload,
            headers=self._headers(),
            timeout=self.REQUEST_TIMEOUT,
        )
        
        logger.info(f"📡 استجابة الإيداع: {r.status_code}")
        
        return r.status_code, r.json()

    @with_retry
    def withdraw(self, player_id, amount):
        payload = {
            "playerId": player_id,
            "amount": amount,
            "currency": "NSP",
            "moneyStatus": 5,
        }
        
        logger.info(f"💸 محاولة سحب: {amount} NSP من اللاعب {player_id}")
        
        r = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["withdraw"],
            json=payload,
            headers=self._headers(),
            timeout=self.REQUEST_TIMEOUT,
        )
        
        logger.info(f"📡 استجابة السحب: {r.status_code}")
        
        return r.status_code, r.json()
