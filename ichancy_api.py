# ichancy_api.py - النسخة المعدلة مع نظام تحديث الرسائل

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
        
        # متغيرات نظام الرسائل
        self._last_message_id = None  # حفظ معرف آخر رسالة
        self._message_update_interval = 60  # تحديث الرسالة كل 60 ثانية
        self._last_message_update = 0
        self._current_status_message = ""  # حفظ محتوى الرسالة الحالية
        self._message_cooldowns = {
            'error': 300,      # 5 دقائق للأخطاء
            'reconnect': 120,  # دقيقتان لإعادة الاتصال
            'success': 600,    # 10 دقائق للنجاحات
            'status': 3600,    # ساعة للحالة
        }
        self._last_notification_time = {}
        
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
        self._status_monitor_thread = None
        self._stop_threads = threading.Event()
        self._retry_count = 0
        self.max_retries = 10
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
            'last_success': datetime.now().strftime('%H:%M:%S'),
            'operations_count': 0,
            'last_status_update': datetime.now().strftime('%H:%M:%S')
        }
        
        # بدء النظام
        self._init_scraper()
        if self.telegram_enabled:
            self._send_initial_status_message()
            self._start_status_monitor()
        
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

    # ========== نظام رسائل التلغرام المتقدم ==========
    
    def _send_telegram_message(self, message: str, parse_mode="HTML", message_id=None):
        """إرسال أو تحديث رسالة في التلغرام"""
        if not self.telegram_enabled:
            return None
            
        try:
            if message_id:
                # تحديث رسالة موجودة
                url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/editMessageText"
                payload = {
                    'chat_id': self.TELEGRAM_CHAT_ID,
                    'message_id': message_id,
                    'text': message,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }
            else:
                # إرسال رسالة جديدة
                url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    'chat_id': self.TELEGRAM_CHAT_ID,
                    'text': message,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if not message_id and 'result' in data and 'message_id' in data['result']:
                    self._last_message_id = data['result']['message_id']
                return True
            return False
                
        except Exception as e:
            self.logger.error(f"خطأ في إرسال/تحديث رسالة التلغرام: {str(e)}")
            return False
    
    def _can_send_notification(self, notification_type: str) -> bool:
        """التحقق من إمكانية إرسال إشعار"""
        now = time.time()
        last_time = self._last_notification_time.get(notification_type, 0)
        cooldown = self._message_cooldowns.get(notification_type, 60)
        
        return now - last_time >= cooldown
    
    def _update_notification_time(self, notification_type: str):
        """تحديث وقت آخر إشعار"""
        self._last_notification_time[notification_type] = time.time()
    
    def _send_initial_status_message(self):
        """إرسال رسالة الحالة الأولية"""
        message = self._generate_status_message("🚀 بدء التشغيل")
        if self._send_telegram_message(message):
            self._current_status_message = message
            self._last_message_update = time.time()
            self.logger.info("✅ تم إرسال رسالة الحالة الأولية")
    
    def _start_status_monitor(self):
        """بدء مراقب تحديث الرسالة"""
        if self._status_monitor_thread and self._status_monitor_thread.is_alive():
            return
            
        self._status_monitor_thread = threading.Thread(
            target=self._status_monitor_loop,
            daemon=True,
            name="StatusMonitor"
        )
        self._status_monitor_thread.start()
        self.logger.info("📊 بدأ مراقب تحديث الرسالة")
    
    def _status_monitor_loop(self):
        """حلقة تحديث الرسالة"""
        while not self._stop_threads.is_set():
            try:
                time.sleep(self._message_update_interval)
                
                # تحديث الرسالة إذا مر وقت كافٍ
                now = time.time()
                if now - self._last_message_update >= self._message_update_interval:
                    self._update_status_message()
                    
            except Exception as e:
                self.logger.error(f"خطأ في مراقب الرسالة: {str(e)}")
                time.sleep(60)
    
    def _update_status_message(self):
        """تحديث رسالة الحالة الحالية"""
        if not self._last_message_id or not self.telegram_enabled:
            return
        
        new_message = self._generate_status_message("🔄 تحديث الحالة")
        if new_message != self._current_status_message:
            if self._send_telegram_message(new_message, message_id=self._last_message_id):
                self._current_status_message = new_message
                self._last_message_update = time.time()
                self.stats['last_status_update'] = datetime.now().strftime('%H:%M:%S')
    
    def _generate_status_message(self, title="📊 حالة النظام"):
        """إنشاء رسالة الحالة"""
        session_info = self.get_session_info()
        
        # حالة الاتصال مع إيموجي
        connection_status = "✅ متصل" if self.is_logged_in else "❌ منقطع"
        connection_emoji = "🟢" if self.is_logged_in else "🔴"
        
        # وقت التشغيل
        uptime = self._get_uptime()
        
        # معدل النجاح
        success_rate = self._calculate_success_rate()
        
        # آخر تحديث
        last_update = self.stats['last_status_update']
        
        # معلومات الجلسة
        session_expiry = session_info.get('session_expiry', 'N/A')
        if session_expiry != 'N/A':
            try:
                expiry_time = datetime.strptime(session_expiry, '%Y-%m-%d %H:%M:%S')
                remaining = expiry_time - datetime.now()
                if remaining.total_seconds() > 0:
                    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    session_expiry = f"{hours}:{minutes:02d}"
                else:
                    session_expiry = "منتهية"
            except:
                session_expiry = session_expiry[-8:] if len(session_expiry) > 8 else session_expiry
        
        message = f"""
{title}
━━━━━━━━━━━━━━━━━━
{connection_emoji} <b>الحالة:</b> {connection_status}
⏰ <b>الصلاحية:</b> {session_expiry}
🆔 <b>المعرف:</b> {session_info.get('session_id', 'N/A')[:8]}
━━━━━━━━━━━━━━━━━━
📈 <b>الإحصائيات:</b>
• التشغيل: {uptime}
• النجاح: {success_rate}%
• إعادة اتصال: {self.total_reconnects}
• محاولات فاشلة: {self.consecutive_failures}
━━━━━━━━━━━━━━━━━━
📊 <b>الأداء:</b>
• عمليات الدخول: {self.stats['total_logins']}
• فشل الدخول: {self.stats['failed_logins']}
• العمليات: {self.stats['operations_count']}
━━━━━━━━━━━━━━━━━━
🕒 <b>آخر تحديث:</b> {last_update}
━━━━━━━━━━━━━━━━━━
📝 <b>آخر خطأ:</b>
{self.stats['last_error'][:50] if self.stats['last_error'] else 'لا توجد أخطاء'}
        """
        
        return message.strip()
    
    def _send_important_notification(self, event_type: str, details: str = ""):
        """إرسال إشعار مهم مع التحديث"""
        if not self._can_send_notification('status'):
            return
        
        # تحديث الرسالة الرئيسية أولاً
        self._update_status_message()
        
        # إرسال إشعار منفصل إذا كان مهماً
        if "error" in event_type.lower() and self._can_send_notification('error'):
            self._send_error_notification(details, event_type)
            self._update_notification_time('error')
        
        elif "reconnect" in event_type.lower() and self._can_send_notification('reconnect'):
            self._send_reconnect_notification(details)
            self._update_notification_time('reconnect')
    
    def _send_error_notification(self, error_message: str, context: str = ""):
        """إرسال إشعار خطأ"""
        message = f"""
🚨 <b>خطأ في النظام</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
📌 <b>السياق:</b> {context}
❌ <b>الخطأ:</b> {error_message[:100]}
━━━━━━━━━━━━━━━━━━
<i>تم تحديث حالة النظام</i>
        """
        self._send_telegram_message(message)
    
    def _send_reconnect_notification(self, details: str = ""):
        """إرسال إشعار إعادة اتصال"""
        message = f"""
🔄 <b>إعادة اتصال</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
📌 <b>التفاصيل:</b> {details[:80]}
🔢 <b>الإجمالي:</b> {self.total_reconnects}
━━━━━━━━━━━━━━━━━━
<i>تم تحديث حالة النظام</i>
        """
        self._send_telegram_message(message)
    
    def send_manual_status_report(self):
        """إرسال تقرير حالة يدوي"""
        if not self.telegram_enabled:
            return "غير مفعل"
        
        # تحديث الرسالة الحالية
        self._update_status_message()
        
        # إرسال تقرير منفصل
        report_message = f"""
📋 <b>تقرير حالة يدوي</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
⏰ <b>بدء التشغيل:</b> {self.start_time.strftime('%H:%M:%S')}
🔄 <b>المدة:</b> {self._get_uptime()}
📊 <b>معدل النجاح:</b> {self._calculate_success_rate()}%
━━━━━━━━━━━━━━━━━━
✅ <i>تم تحديث حالة النظام الرئيسية</i>
        """
        
        self._send_telegram_message(report_message)
        return "تم إرسال التقرير وتحديث الحالة"
    
    # ========== دوال مساعدة ==========
    
    def _calculate_success_rate(self):
        """حساب معدل النجاح"""
        total = self.stats['total_logins']
        failed = self.stats['failed_logins']
        
        if total == 0:
            return 100
        success_rate = round(((total - failed) / total) * 100, 1)
        return success_rate
    
    def _get_uptime(self):
        """الحصول على مدة التشغيل"""
        uptime = datetime.now() - self.start_time
        
        if uptime.days > 0:
            return f"{uptime.days} يوم"
        
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours} ساعة"
        return f"{minutes} دقيقة"
    
    # ========== نظام إعادة الاتصال التلقائي ==========
    
    def _start_auto_reconnect(self):
        """بدء نظام إعادة الاتصال التلقائي"""
        if self._auto_reconnect_thread and self._auto_reconnect_thread.is_alive():
            return
            
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
                    
                    # إرسال إشعار بعد عدة محاولات فاشلة
                    if self.consecutive_failures >= 2:
                        self._send_important_notification(
                            "فقدان الاتصال",
                            f"المحاولة {self.consecutive_failures}"
                        )
                    
                    # محاولة إعادة الاتصال
                    if self._simple_reconnect():
                        self.consecutive_failures = 0
                        self.total_reconnects += 1
                        self.stats['last_success'] = datetime.now().strftime('%H:%M:%S')
                        
                        # تحديث الرسالة فقط
                        self._update_status_message()
                    
            except Exception as e:
                self.logger.error(f"خطأ في إعادة الاتصال: {str(e)}")
                self.stats['last_error'] = str(e)
                time.sleep(30)
    
    def _simple_reconnect(self, max_attempts=3):
        """إعادة اتصال مبسطة"""
        for attempt in range(max_attempts):
            try:
                # الانتظار قبل المحاولة
                wait_time = 2 ** (attempt + 1)
                time.sleep(wait_time)
                
                # إعادة تهيئة
                self.scraper = None
                self.session_cookies = {}
                self.is_logged_in = False
                
                # محاولة تسجيل دخول
                success, _ = self.login(max_retries=2)
                
                if success:
                    return True
                    
            except Exception as e:
                self.logger.error(f"محاولة {attempt + 1} فشلت: {str(e)}")
                continue
        
        return False
    
    # ========== نظام ضربات القلب ==========
    
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
                    if self._perform_health_check():
                        self.session_expiry = datetime.now() + timedelta(seconds=self.SESSION_TIMEOUT)
                        # تحديث الرسالة كل فترة
                        if time.time() - self._last_message_update >= 300:  # كل 5 دقائق
                            self._update_status_message()
                    else:
                        self.is_logged_in = False
                        
            except Exception as e:
                self.logger.error(f"خطأ في ضربات القلب: {str(e)}")
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
                self.stats['last_error'] = str(e)
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
                    self.stats['last_success'] = datetime.now().strftime('%H:%M:%S')
                    
                    self._retry_count = 0
                    self.consecutive_failures = 0
                    
                    # تحديث الرسالة
                    if self.telegram_enabled:
                        self._update_status_message()
                    
                    return True, data
                else:
                    error_msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول")
                    self.stats['failed_logins'] += 1
                    self.stats['last_error'] = error_msg
                    
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
            if (self.is_logged_in and 
                self.scraper and 
                self._is_session_valid()):
                
                return True
            
            self.logger.info("محاولة تأسيس/استعادة الجلسة...")
            
            success, data = self.login()
            
            if not success:
                error_msg = data.get("error", "فشل تسجيل الدخول")
                self.logger.error(f"فشل في تأسيس الجلسة: {error_msg}")
                return False
            
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
    
    # ========== decorator ==========
    
    def with_retry(func):
        """مُعدِّل لإعادة المحاولة"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for attempt in range(2):
                try:
                    self.ensure_login()
                    result = func(self, *args, **kwargs)
                    
                    # تحديث الرسالة بعد العملية الناجحة
                    if result and attempt == 0 and self.telegram_enabled:
                        self._update_status_message()
                    
                    return result
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
            "session_expiry": self.session_expiry.strftime("%Y-%m-%d %H:%M:%S") if self.session_expiry else None,
            "session_age": session_age,
            "consecutive_failures": self.consecutive_failures,
            "total_reconnects": self.total_reconnects,
            "uptime": self._get_uptime(),
            "success_rate": self._calculate_success_rate(),
            "stats": self.stats
        }
    
    def stop(self):
        """إيقاف النظام"""
        self.logger.info("🛑 إيقاف النظام...")
        
        # إرسال رسالة إيقاف نهائية
        if self.telegram_enabled:
            final_message = f"""
🛑 <b>إيقاف النظام</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
⏰ <b>مدة التشغيل:</b> {self._get_uptime()}
📊 <b>معدل النجاح:</b> {self._calculate_success_rate()}%
🔄 <b>إعادة الاتصال:</b> {self.total_reconnects}
━━━━━━━━━━━━━━━━━━
✅ <i>تم إيقاف النظام بنجاح</i>
            """
            self._send_telegram_message(final_message)
        
        # إيقاف الخيوط
        self._stop_threads.set()
        
        threads = [self._heartbeat_thread, self._auto_reconnect_thread, self._status_monitor_thread]
        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=3)
        
        # تنظيف الموارد
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.session_id = None
        self.scraper = None
        self._last_message_id = None
        
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

# ========== استخدام مباشر ==========

if __name__ == "__main__":
    api = IChancyAPI()
    
    try:
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
