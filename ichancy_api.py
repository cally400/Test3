
# ichancy_api.py - الإصدار النهائي مع Redis وCloudScraper
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
    """
    إرجاع نسخة واحدة مشتركة من IChancyAPI لجميع الطلبات
    """
    global _global_api_instance
    if _global_api_instance is None:
        _global_api_instance = IChancyAPI()
    return _global_api_instance

class IChancyAPI:
    """
    🔐 Global Agent Session - إدارة الجلسة المركزية مع Redis
    """

    def __init__(self):
        self._setup_logging()
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
    # Logging
    # =========================
    def _setup_logging(self):
        """تهيئة نظام التسجيل"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    # =========================
    # Config
    # =========================
    def _load_config(self):
        """تحميل الإعدادات من متغيرات البيئة"""
        self.USERNAME = os.getenv("AGENT_USERNAME", "twd_bot@agent.nsp")
        self.PASSWORD = os.getenv("AGENT_PASSWORD", "Twd@@123")
        self.PARENT_ID = os.getenv("PARENT_ID", "2470819")

        # ⚠️ تأكد من أن هذه القيمة صحيحة
        self.ORIGIN = os.getenv("ICHANCY_ORIGIN", "https://agents.ichancy.com")
        
        # ⚠️ الإندبوينت الصحيح للتحقق من اللاعب هو statistics
        self.ENDPOINTS = {
            'signin': "/global/api/User/signIn",
            'create': "/global/api/Player/registerPlayer",
            'statistics': "/global/api/Statistics/getPlayersStatisticsPro",  # ✅ للإحصاءات والتحقق
            'deposit': "/global/api/Player/depositToPlayer",
            'withdraw': "/global/api/Player/withdrawFromPlayer",
            'balance': "/global/api/Player/getPlayerBalanceById"
        }

        # ⚠️ User-Agent للإصدار القديم (كان يعمل)
        self.USER_AGENT = (
            "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.5249.126 Mobile Safari/537.36"
        )
        
        self.REFERER = self.ORIGIN + "/dashboard"
        self.REQUEST_TIMEOUT = 30
        
        # ✅ التحقق من وجود المتغيرات البيئية
        if not all([self.USERNAME, self.PASSWORD, self.PARENT_ID]):
            self.logger.error("❌ متغيرات البيئة AGENT_USERNAME أو AGENT_PASSWORD أو PARENT_ID غير موجودة")
            raise RuntimeError("متغيرات البيئة المطلوبة غير موجودة")

    # =========================
    # Redis
    # =========================
    def _init_redis(self):
        """تهيئة اتصال Redis"""
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            self.logger.error("❌ REDIS_URL غير موجود في متغيرات البيئة")
            # استمر بدون Redis (للتوافق)
            self.logger.warning("⚠️ سيتم العمل بدون Redis - تخزين الجلسة في الذاكرة فقط")
            return
        
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            self.logger.info("✅ Redis connected successfully")
        except Exception as e:
            self.logger.error(f"❌ فشل الاتصال بـ Redis: {e}")
            self.logger.warning("⚠️ سيتم العمل بدون Redis - تخزين الجلسة في الذاكرة فقط")

    # =========================
    # Scraper
    # =========================
    def _init_scraper(self):
        """تهيئة السكرابر مع إعدادات خاصة لتجنب Cloudflare"""
        if self.scraper:
            return
        
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                },
                # ⚠️ إضافة delay لتجنب كشف Cloudflare
                delay=5
            )
            self.logger.info("✅ CloudScraper initialized")
        except Exception as e:
            self.logger.error(f"❌ فشل تهيئة CloudScraper: {e}")
            raise

    def _get_headers(self):
        """الحصول على هيدرات الطلب"""
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    # =========================
    # Session Management مع Redis
    # =========================
    def _is_session_valid(self):
        """التحقق من صلاحية الجلسة"""
        if not self.session_expiry or not self.last_login_time:
            return False
            
        # الجلسة صالحة لمدة 25 دقيقة (أقل من 30 لتجنب الانتهاء أثناء العملية)
        session_duration = timedelta(minutes=25)
        max_session_age = timedelta(hours=2)
        
        time_since_login = datetime.now() - self.last_login_time
        
        return (datetime.now() < self.session_expiry and 
                time_since_login < max_session_age)

    def _load_session_from_redis(self):
        """تحميل الجلسة من Redis"""
        if not self.redis:
            return
            
        try:
            data = self.redis.get(self.REDIS_SESSION_KEY)
            if not data:
                self.logger.info("ℹ️ لا توجد جلسة مخزنة في Redis")
                return
            
            session = json.loads(data)
            self.session_cookies = session.get("cookies", {})
            self.session_expiry = datetime.fromisoformat(session["expiry"])
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
        if not self.redis or not self.session_cookies:
            return
            
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
        """إبطال الجلسة وحذفها من Redis"""
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None
        
        if self.redis:
            try:
                self.redis.delete(self.REDIS_SESSION_KEY)
                self.logger.warning("♻️ تم إبطال الجلسة وحذفها من Redis")
            except:
                pass

    # =========================
    # Login
    # =========================
    def _clean_cookies(self):
        """تنظيف الكوكيز من القيم المكررة"""
        if not self.scraper:
            return
            
        try:
            # إنشاء قاموس جديد للكوكيز بدون تكرار
            unique_cookies = {}
            for cookie in self.scraper.cookies:
                # تجاهل الكوكيز المكررة
                if cookie.name not in unique_cookies:
                    unique_cookies[cookie.name] = cookie.value
            
            # تحديث الكوكيز في السكرابر
            self.scraper.cookies.clear()
            for name, value in unique_cookies.items():
                self.scraper.cookies.set(name, value)
                
        except Exception as e:
            self.logger.warning(f"⚠️ خطأ في تنظيف الكوكيز: {e}")

    def login(self):
        """تسجيل دخول الوكيل مع إدارة الكوكيز"""
        if not self.scraper:
            self._init_scraper()
            
        # 🔒 منع تسجيلات الدخول المتزامنة
        if self.redis:
            if not self.redis.set(self.REDIS_LOCK_KEY, "1", nx=True, ex=60):
                self.logger.info("⏳ جاري انتظار عملية تسجيل دخول أخرى...")
                time.sleep(3)
                self._load_session_from_redis()
                if self.is_logged_in:
                    return True, {"status": True, "result": {"type": 0, "message": "dashboard"}}
        
        try:
            self.logger.info(f"🚀 محاولة تسجيل الدخول إلى {self.ORIGIN}")
            
            # ⚠️ تنظيف الكوكيز القديمة قبل المحاولة
            self.scraper.cookies.clear()
            
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
            
            # ✅ معالجة الاستجابة
            if resp.status_code != 200:
                self.logger.error(f"❌ فشل تسجيل الدخول: HTTP {resp.status_code}")
                self.logger.error(f"📄 محتوى الاستجابة: {resp.text[:500]}")
                return False, {"error": f"HTTP {resp.status_code}"}
            
            try:
                data = resp.json()
            except:
                self.logger.error(f"❌ استجابة غير صالحة (ليست JSON): {resp.text[:500]}")
                return False, {"error": "استجابة غير صالحة"}
            
            self.logger.info(f"📊 بيانات استجابة API: {json.dumps(data, indent=2)[:500]}")
            
            # ⚠️ التحقق الصحيح من نتيجة تسجيل الدخول
            if data.get("status") and isinstance(data.get("result"), dict) and data["result"].get("type") == 0:
                # ✅ تسجيل الدخول ناجح
                
                # ⚠️ تنظيف الكوكيز من التكرارات
                self._clean_cookies()
                
                # حفظ بيانات الجلسة
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=25)
                self.last_login_time = datetime.now()
                self.is_logged_in = True
                
                # حفظ الجلسة في Redis
                self._save_session_to_redis()
                
                self.logger.info("✅ تم تسجيل الدخول بنجاح")
                self.logger.info(f"   الجلسة صالحة حتى: {self.session_expiry.strftime('%H:%M:%S')}")
                return True, data
            else:
                error_msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول - result ليس 0")
                self.logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
                self.logger.error(f"📊 result القيمة: {data.get('result')}")
                return False, data
            
        except Exception as e:
            self.logger.error(f"❌ استثناء أثناء تسجيل الدخول: {e}")
            return False, {"error": str(e)}
        finally:
            # 🔓 تحرير القفل
            if self.redis:
                try:
                    self.redis.delete(self.REDIS_LOCK_KEY)
                except:
                    pass

    def ensure_login(self):
        """التأكد من تسجيل الدخول مع إعادة الاتصال إذا لزم"""
        if self._is_session_valid() and self.is_logged_in:
            self.logger.debug("✅ الجلسة سارية بالفعل")
            return True
        
        # محاولة تحميل الجلسة من Redis
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
    # Decorator for API calls
    # =========================
    def with_retry(func):
        """مُعدِّل لإعادة المحاولة"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                self.ensure_login()
                return func(self, *args, **kwargs)
            except Exception as e:
                self.logger.error(f"خطأ في تنفيذ الدالة {func.__name__}: {str(e)}")
                
                # محاولة تسجيل الدخول مرة أخرى
                self._invalidate_session()
                try:
                    self.ensure_login()
                    return func(self, *args, **kwargs)
                except Exception as e2:
                    self.logger.error(f"❌ فشل إعادة المحاولة: {e2}")
                    return None, {"error": str(e2)}
                    
        return wrapper

    # =========================
    # API Methods - معدلة
    # =========================
    @with_retry
    def check_player_exists(self, login: str) -> bool:
        """التحقق من وجود لاعب - باستخدام statistics"""
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"login": login}
        }

        self.logger.info(f"🔍 التحقق من وجود اللاعب: {login}")
        
        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['statistics'],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT
        )
        
        self.logger.info(f"📡 استجابة التحقق: HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            self.logger.warning(f"⚠️ استجابة غير 200: {resp.text[:300]}")
            return False
        
        try:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            exists = any(record.get("username") == login for record in records)
            self.logger.info(f"ℹ️ نتيجة التحقق: اللاعب '{login}' موجود = {exists}")
            return exists
        except Exception as e:
            self.logger.error(f"❌ خطأ في تحليل استجابة التحقق: {e}")
            return False

    @with_retry
    def create_player(self, login: str, password: str) -> Tuple[int, dict, Optional[str]]:
        """إنشاء لاعب جديد"""
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
        
        self.logger.info(f"📡 استجابة إنشاء اللاعب: {resp.status_code}")
        
        if resp.status_code in (401, 403):
            self.logger.error(f"❌ رفض الوصول: {resp.status_code}")
            self.logger.error(f"📄 محتوى الاستجابة: {resp.text[:500]}")
        
        try:
            data = resp.json()
            player_id = None
            if data.get("status"):
                # الحصول على معرف اللاعب
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
        
        self.logger.info(f"💰 محاولة إيداع: {amount} NSP للاعب {player_id}")

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['deposit'],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT
        )
        
        self.logger.info(f"📡 استجابة الإيداع: {resp.status_code}")
        
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
        
        self.logger.info(f"💸 محاولة سحب: {amount} NSP من اللاعب {player_id}")

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['withdraw'],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT
        )
        
        self.logger.info(f"📡 استجابة السحب: {resp.status_code}")
        
        try:
            data = resp.json()
            return resp.status_code, data
        except Exception:
            return resp.status_code, {}

    @with_retry
    def get_player_balance(self, player_id: str) -> Tuple[int, dict, float]:
        """الحصول على رصيد اللاعب"""
        payload = {"playerId": str(player_id)}
        
        self.logger.info(f"🏦 محاولة الحصول على رصيد اللاعب: {player_id}")

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS['balance'],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT
        )
        
        self.logger.info(f"📡 استجابة الرصيد: {resp.status_code}")
        
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
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT
        )

        try:
            data = resp.json()
            return data.get("result", {}).get("records", [])
        except Exception:
            return []
