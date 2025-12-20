# ichancy_api.py - النسخة المعدلة مع تقليل الرسائل

import cloudscraper
import random
import string
import os
import logging
import time
import threading
import requests
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional, Union, Any
import json
from functools import wraps
import hashlib

class IChancyAPI:
    def __init__(self, telegram_bot_token=None, telegram_chat_id=None):
        self._setup_logging()
        self._load_config()
        
        # إعدادات التلغرام
        self.TELEGRAM_BOT_TOKEN = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_CHAT_ID = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "-1003317405069")
        self.telegram_enabled = bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)
        
        # متغيرات التحكم في الإشعارات
        self._last_notification_time = {}
        self._notification_cooldown = {
            'error': 300,      # 5 دقائق للأخطاء
            'reconnect': 60,   # دقيقة واحدة لإعادة الاتصال
            'status': 3600,    # ساعة واحدة للحالة
            'success': 1800,   # 30 دقيقة للنجاحات
        }
        
        # متغيرات الجلسة
        self.scraper = None
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None
        self.session_id = None
        self._session_lock = threading.Lock()
        self._heartbeat_thread = None
        self._auto_reconnect_thread = None
        self._stop_threads = threading.Event()
        self._retry_count = 0
        self.max_retries = 5
        self.consecutive_failures = 0
        self.total_reconnects = 0
        self.start_time = datetime.now()
        
        # إعدادات التوقيت
        self._session_refresh_interval = 1200
        self._health_check_interval = 300
        self._auto_reconnect_check_interval = 60
        
        # الإحصائيات
        self.stats = {
            'total_logins': 0,
            'failed_logins': 0,
            'reconnects': 0,
            'last_error': None,
            'last_success': None,
            'operations_count': 0
        }
        
        # بدء النظام
        self._init_scraper()
        if self.telegram_enabled:
            self._send_startup_notification()
        
    def _setup_logging(self):
        """تهيئة نظام التسجيل"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

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
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        self.REFERER = self.ORIGIN + "/dashboard"
        
        self.SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "1800"))

    # ========== نظام إشعارات التلغرام مع تقليل ==========
    
    def _can_send_notification(self, notification_type: str) -> bool:
        """التحقق من إمكانية إرسال الإشعار"""
        now = time.time()
        last_time = self._last_notification_time.get(notification_type, 0)
        cooldown = self._notification_cooldown.get(notification_type, 60)
        
        if now - last_time < cooldown:
            return False
        
        self._last_notification_time[notification_type] = now
        return True
    
    def _send_telegram_message(self, message: str, parse_mode="HTML"):
        """إرسال رسالة إلى قناة التلغرام"""
        if not self.telegram_enabled:
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': self.TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
                
        except Exception:
            return False
    
    def _send_startup_notification(self):
        """إرسال إشعار بدء التشغيل"""
        message = f"""
🚀 <b>بدء تشغيل نظام IChancy API</b>
━━━━━━━━━━━━━━━━━━
📅 <b>التاريخ:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👤 <b>الحساب:</b> {self.USERNAME[:10]}...
🆔 <b>Parent ID:</b> {self.PARENT_ID}
🔗 <b>السيرفر:</b> {self.ORIGIN}
━━━━━━━━━━━━━━━━━━
✅ <i>النظام جاهز للعمل</i>
        """
        self._send_telegram_message(message)
    
    def _send_important_notification(self, event_type: str, details: str = ""):
        """إرسال إشعار مهم فقط (مع تقليل التكرار)"""
        if not self._can_send_notification('status'):
            return
        
        session_info = self.get_session_info()
        
        emoji = "✅"
        if "error" in event_type.lower() or "fail" in event_type.lower():
            emoji = "❌"
        elif "reconnect" in event_type.lower():
            emoji = "🔄"
        elif "warning" in event_type.lower():
            emoji = "⚠️"
        
        message = f"""
{emoji} <b>{event_type}</b>
━━━━━━━━━━━━━━━━━━
🆔 <b>معرف الجلسة:</b> {session_info.get('session_id', 'N/A')[:8]}
🔐 <b>الحالة:</b> {'✅ متصل' if session_info.get('is_logged_in') else '❌ منقطع'}
🔄 <b>إعادة الاتصال:</b> {self.total_reconnects}
📊 <b>معدل النجاح:</b> {self._calculate_success_rate()}%
━━━━━━━━━━━━━━━━━━
📝 <b>التفاصيل:</b>
{details[:100]}
        """
        self._send_telegram_message(message)
    
    def _send_error_notification(self, error_message: str, function_name: str = ""):
        """إرسال إشعار خطأ مهم فقط"""
        if not self._can_send_notification('error'):
            return
        
        message = f"""
🚨 <b>خطأ في النظام</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
⚙️ <b>الدالة:</b> {function_name}
❌ <b>الخطأ:</b> {error_message[:100]}
🔄 <b>المحاولات:</b> {self.consecutive_failures}
━━━━━━━━━━━━━━━━━━
<i>جاري الإصلاح التلقائي...</i>
        """
        self._send_telegram_message(message)
    
    def _send_daily_summary(self):
        """إرسال ملخص يومي فقط"""
        if not self._can_send_notification('status'):
            return
        
        uptime = self._get_uptime()
        success_rate = self._calculate_success_rate()
        
        message = f"""
📊 <b>ملخص أداء النظام</b>
━━━━━━━━━━━━━━━━━━
📅 <b>التاريخ:</b> {datetime.now().strftime('%Y-%m-%d')}
⏰ <b>مدة التشغيل:</b> {uptime}
🔄 <b>عمليات الدخول:</b> {self.stats['total_logins']}
❌ <b>فشل الدخول:</b> {self.stats['failed_logins']}
🔗 <b>إعادة الاتصال:</b> {self.total_reconnects}
📈 <b>معدل النجاح:</b> {success_rate}%
🔐 <b>الحالة:</b> {'✅ نشط' if self.is_logged_in else '❌ غير نشط'}
━━━━━━━━━━━━━━━━━━
<i>النظام يعمل بشكل طبيعي</i>
        """
        self._send_telegram_message(message)
    
    # ========== دوال مساعدة ==========
    
    def _calculate_success_rate(self):
        """حساب معدل النجاح"""
        total = self.stats['total_logins']
        failed = self.stats['failed_logins']
        
        if total == 0:
            return 100
        return round(((total - failed) / total) * 100, 2)
    
    def _get_uptime(self):
        """الحصول على مدة التشغيل"""
        uptime = datetime.now() - self.start_time
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        
        if days > 0:
            return f"{days} يوم, {hours} ساعة"
        elif hours > 0:
            return f"{hours} ساعة, {minutes} دقيقة"
        else:
            return f"{minutes} دقيقة"
    
    # ========== نظام إعادة الاتصال التلقائي المبسط ==========
    
    def _start_auto_reconnect(self):
        """بدء نظام إعادة الاتصال التلقائي"""
        if self._auto_reconnect_thread and self._auto_reconnect_thread.is_alive():
            return
            
        self._stop_threads.clear()
        self._auto_reconnect_thread = threading.Thread(
            target=self._auto_reconnect_loop,
            daemon=True,
            name="AutoReconnect"
        )
        self._auto_reconnect_thread.start()
        self.logger.info("🔄 بدأ نظام إعادة الاتصال التلقائي")
    
    def _auto_reconnect_loop(self):
        """حلقة إعادة الاتصال التلقائي"""
        while not self._stop_threads.is_set():
            try:
                time.sleep(self._auto_reconnect_check_interval)
                
                # التحقق من حالة الاتصال
                if not self.is_logged_in or not self._perform_health_check():
                    self.consecutive_failures += 1
                    
                    # إرسال إشعار فقط بعد عدة محاولات فاشلة
                    if self.consecutive_failures >= 3 and self._can_send_notification('reconnect'):
                        self._send_important_notification(
                            "محاولة إعادة اتصال",
                            f"المحاولات الفاشلة: {self.consecutive_failures}"
                        )
                    
                    # محاولة إعادة الاتصال
                    if self._simple_reconnect():
                        self.consecutive_failures = 0
                        self.total_reconnects += 1
                        
                        # إشعار النجاح مرة واحدة فقط
                        if self._can_send_notification('success'):
                            self._send_important_notification(
                                "تم استعادة الاتصال",
                                f"بعد {self.total_reconnects} محاولات"
                            )
                    else:
                        # زيادة التأخير
                        extra_delay = min(self.consecutive_failures * 10, 120)
                        time.sleep(extra_delay)
                
                # إرسال ملخص يومي في منتصف الليل
                current_time = datetime.now()
                if current_time.hour == 0 and current_time.minute < 5:
                    self._send_daily_summary()
                    time.sleep(300)  # تأخير 5 دقائق
                    
            except Exception as e:
                self.logger.error(f"خطأ في حلقة إعادة الاتصال: {str(e)}")
                time.sleep(60)
    
    def _simple_reconnect(self, max_attempts=3):
        """إعادة اتصال مبسطة"""
        for attempt in range(1, max_attempts + 1):
            try:
                # الانتظار قبل المحاولة
                time.sleep(2 ** attempt)  # تأخير متزايد
                
                # إعادة تهيئة
                self.scraper = None
                self.session_cookies = {}
                self.is_logged_in = False
                
                # محاولة تسجيل دخول
                success, _ = self.login(max_retries=2)
                
                if success:
                    return True
                    
            except Exception:
                continue
        
        return False
    
    # ========== نظام ضربات القلب المبسط ==========
    
    def _start_heartbeat(self):
        """بدء نظام ضربات القلب"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
            
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="SessionHeartbeat"
        )
        self._heartbeat_thread.start()
        self.logger.info("❤️  بدأ نظام ضربات القلب")
    
    def _heartbeat_loop(self):
        """حلقة ضربات القلب"""
        while not self._stop_threads.is_set():
            try:
                time.sleep(self._health_check_interval)
                
                if self.is_logged_in:
                    # إجراء فحص صحي
                    if self._perform_health_check():
                        # تحديث وقت انتهاء الصلاحية
                        self.session_expiry = datetime.now() + timedelta(seconds=self.SESSION_TIMEOUT)
                    else:
                        self.is_logged_in = False
                        
            except Exception:
                time.sleep(60)
    
    # ========== الدوال الأساسية ==========
    
    def _init_scraper(self):
        """تهيئة السكرابر"""
        with self._session_lock:
            try:
                self.scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'mobile': False
                    },
                    delay=5
                )
                
                self.scraper.timeout = 30
                
                # بدء الأنظمة المساعدة
                self._start_heartbeat()
                self._start_auto_reconnect()
                
                return True
                    
            except Exception as e:
                self.logger.error(f"فشل في تهيئة السكرابر: {str(e)}")
                return False
    
    def _get_headers(self):
        """الحصول على هيدرات الطلب"""
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER
        }
    
    def login(self, max_retries=None):
        """تسجيل دخول"""
        max_retries = max_retries or self.max_retries
        self.stats['total_logins'] += 1
        
        for attempt in range(max_retries):
            try:
                if not self.scraper:
                    self._init_scraper()
                    
                payload = {
                    "username": self.USERNAME,
                    "password": self.PASSWORD
                }

                self.logger.info(f"محاولة تسجيل دخول {attempt + 1}/{max_retries}")
                
                resp = self.scraper.post(
                    self.ORIGIN + self.ENDPOINTS['signin'],
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30
                )

                data = resp.json()

                if data.get("result", False):
                    # حفظ الجلسة
                    self.session_cookies = dict(self.scraper.cookies)
                    self.session_expiry = datetime.now() + timedelta(seconds=self.SESSION_TIMEOUT)
                    self.last_login_time = datetime.now()
                    self.is_logged_in = True
                    
                    # إنشاء معرف الجلسة
                    self._generate_session_id()
                    
                    self.logger.info("تم تسجيل الدخول بنجاح")
                    
                    self._retry_count = 0
                    self.consecutive_failures = 0
                    
                    return True, data
                else:
                    self.stats['failed_logins'] += 1
                    
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    
                    return False, data

            except Exception as e:
                self.logger.error(f"خطأ في تسجيل الدخول: {str(e)}")
                self.stats['failed_logins'] += 1
                self.stats['last_error'] = str(e)
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    self._retry_count += 1
                    return False, {"error": str(e)}
        
        return False, {"error": "تجاوز الحد الأقصى لمحاولات تسجيل الدخول"}
    
    def _generate_session_id(self):
        """إنشاء معرف فريد للجلسة"""
        if not self.session_cookies:
            self.session_id = None
            return
            
        cookies_str = str(self.session_cookies)
        timestamp = datetime.now().isoformat()
        hash_input = f"{cookies_str}{timestamp}{self.USERNAME}"
        
        self.session_id = hashlib.md5(hash_input.encode()).hexdigest()[:8]
    
    def ensure_login(self):
        """التأكد من تسجيل الدخول"""
        with self._session_lock:
            # التحقق من الجلسة الحالية
            if (self.is_logged_in and 
                self.scraper and 
                self._is_session_valid()):
                
                return True
            
            self.logger.info("محاولة تأسيس/استعادة الجلسة...")
            
            # محاولة تسجيل دخول جديد
            success, data = self.login()
            
            if not success:
                error_msg = data.get("error", "فشل تسجيل الدخول")
                self.logger.error(f"فشل في تأسيس الجلسة: {error_msg}")
                
                # إرسال إشعار خطأ مهم فقط
                if self._can_send_notification('error'):
                    self._send_error_notification(error_msg, "ensure_login")
                
                return False
            
            # إرسال إشعار نجاح مهم فقط
            if self._can_send_notification('success'):
                self._send_important_notification("تأسيس الجلسة", "تم بنجاح")
            
            return True
    
    def _is_session_valid(self):
        """التحقق من صلاحية الجلسة"""
        if not self.session_cookies or not self.session_expiry:
            return False
            
        if datetime.now() >= self.session_expiry:
            return False
                
        return True
    
    def _perform_health_check(self):
        """فحص صحي مبسط"""
        try:
            if not self.scraper or not self.is_logged_in:
                return False
                
            payload = {"page": 1, "pageSize": 1}
            
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS['statistics'],
                json=payload,
                headers=self._get_headers(),
                timeout=10
            )
            
            return resp.status_code == 200
            
        except Exception:
            return False
    
    # ========== decorator مبسط ==========
    
    def with_retry(func):
        """مُعدِّل لإعادة المحاولة"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for attempt in range(2):  # محاولتان فقط
                try:
                    self.ensure_login()
                    return func(self, *args, **kwargs)
                except Exception as e:
                    self.logger.error(f"خطأ في {func.__name__}: {str(e)}")
                    if attempt == 0:
                        time.sleep(2)
                        self.is_logged_in = False
                    else:
                        return None, {"error": str(e)}
            return None, {"error": "فشل بعد عدة محاولات"}
        return wrapper
    
    # ========== دوال المعلومات ==========
    
    def get_session_info(self):
        """الحصول على معلومات الجلسة"""
        session_age = None
        if self.last_login_time:
            session_age = str(datetime.now() - self.last_login_time).split('.')[0]
        
        return {
            "is_logged_in": self.is_logged_in,
            "session_id": self.session_id,
            "session_expiry": self.session_expiry.strftime("%H:%M:%S") if self.session_expiry else None,
            "session_age": session_age,
            "consecutive_failures": self.consecutive_failures,
            "total_reconnects": self.total_reconnects,
            "uptime": self._get_uptime(),
            "success_rate": self._calculate_success_rate()
        }
    
    def send_status_report(self):
        """إرسال تقرير حالة يدوي"""
        if not self._can_send_notification('status'):
            return "يجب الانتظار قبل إرسال تقرير آخر"
        
        session_info = self.get_session_info()
        
        message = f"""
📋 <b>تقرير حالة يدوي</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
🔐 <b>حالة الدخول:</b> {'✅ متصل' if session_info['is_logged_in'] else '❌ منقطع'}
🆔 <b>معرف الجلسة:</b> {session_info['session_id'] or 'N/A'}
⏳ <b>مدة التشغيل:</b> {session_info['uptime']}
🔄 <b>إعادة الاتصال:</b> {session_info['total_reconnects']}
📊 <b>معدل النجاح:</b> {session_info['success_rate']}%
━━━━━━━━━━━━━━━━━━
        """
        self._send_telegram_message(message)
        return "تم إرسال التقرير"
    
    def stop(self):
        """إيقاف النظام"""
        self.logger.info("🛑 إيقاف النظام...")
        
        # إرسال إشعار إيقاف مهم فقط
        if self.telegram_enabled and self._can_send_notification('status'):
            uptime = self._get_uptime()
            stop_message = f"""
🛑 <b>إيقاف النظام</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
⏳ <b>مدة التشغيل:</b> {uptime}
🔄 <b>إعادة الاتصال:</b> {self.total_reconnects}
📊 <b>معدل النجاح:</b> {self._calculate_success_rate()}%
━━━━━━━━━━━━━━━━━━
            """
            self._send_telegram_message(stop_message)
        
        # إيقاف الخيوط
        self._stop_threads.set()
        
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=3)
        
        if self._auto_reconnect_thread and self._auto_reconnect_thread.is_alive():
            self._auto_reconnect_thread.join(timeout=3)
        
        # تنظيف الموارد
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.session_id = None
        self.scraper = None
        
        self.logger.info("✅ تم إيقاف النظام")
    
    # ========== دوال API الأساسية ==========
    
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

# ========== استخدام مباشر (اختياري) ==========

if __name__ == "__main__":
    # إنشاء API - ستستخدم متغيرات البيئة للتلغرام
    api = IChancyAPI()
    
    try:
        # محاولة الاتصال
        if api.ensure_login():
            print("✅ تم الاتصال بنجاح")
            print(api.get_session_info())
            
            # البقاء نشطاً
            print("النظام يعمل... اضغط Ctrl+C للإيقاف")
            while True:
                time.sleep(60)
        else:
            print("❌ فشل في الاتصال")
            
    except KeyboardInterrupt:
        print("\n🛑 إيقاف بطلب المستخدم...")
    except Exception as e:
        print(f"❌ خطأ: {e}")
    finally:
        api.stop()
