
#ichancy_api.py - النسخة المعدلة مع الإشعارات وإعادة الاتصال التلقائي

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
import traceback

class IChancyAPI:
    def __init__(self, telegram_bot_token=None, telegram_chat_id=None):
        self._setup_logging()
        self._load_config()
        
        # إعدادات التلغرام
        self.TELEGRAM_BOT_TOKEN = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_CHAT_ID = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "-1003317405069")
        self.telegram_enabled = bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)
        
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
        self.max_retries = 10
        self.consecutive_failures = 0
        self.total_reconnects = 0
        self.start_time = datetime.now()
        
        # إعدادات التوقيت
        self._session_refresh_interval = 1200  # 20 دقيقة
        self._health_check_interval = 300  # 5 دقائق
        self._auto_reconnect_check_interval = 30  # 30 ثانية
        
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
        self._send_startup_notification()
        
    def _setup_logging(self):
        """تهيئة نظام التسجيل المتقدم"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
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
        
        # إعدادات الجلسة
        self.SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "1800"))
        self.MAX_SESSION_AGE = int(os.getenv("MAX_SESSION_AGE", "7200"))
        self.HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "300"))
        self.AUTO_RECONNECT_DELAY = int(os.getenv("AUTO_RECONNECT_DELAY", "10"))

    # ========== نظام إشعارات التلغرام ==========
    
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
            if response.status_code == 200:
                return True
            else:
                self.logger.error(f"فشل إرسال رسالة التلغرام: {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"خطأ في إرسال رسالة التلغرام: {str(e)}")
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
    
    def _send_session_notification(self, event_type: str, details: str = ""):
        """إرسال إشعار حالة الجلسة"""
        session_info = self.get_session_info()
        
        emoji = "✅"
        if "error" in event_type.lower() or "fail" in event_type.lower():
            emoji = "❌"
        elif "reconnect" in event_type.lower() or "retry" in event_type.lower():
            emoji = "🔄"
        elif "warning" in event_type.lower():
            emoji = "⚠️"
        elif "expired" in event_type.lower():
            emoji = "⏰"
        
        message = f"""
{emoji} <b>{event_type}</b>
━━━━━━━━━━━━━━━━━━
🆔 <b>معرف الجلسة:</b> {session_info.get('session_id', 'N/A')}
🔐 <b>الحالة:</b> {'✅ متصل' if session_info.get('is_logged_in') else '❌ منقطع'}
⏰ <b>الصلاحية حتى:</b> {session_info.get('session_expiry', 'N/A')}
🔄 <b>عدد إعادة الاتصال:</b> {self.total_reconnects}
📊 <b>معدل النجاح:</b> {self._calculate_success_rate()}%
━━━━━━━━━━━━━━━━━━
📝 <b>التفاصيل:</b>
{details}
        """
        self._send_telegram_message(message)
    
    def _send_error_notification(self, error_message: str, function_name: str = ""):
        """إرسال إشعار خطأ"""
        message = f"""
🚨 <b>خطأ في النظام</b>
━━━━━━━━━━━━━━━━━━
📅 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
⚙️ <b>الدالة:</b> {function_name}
❌ <b>الخطأ:</b> {error_message[:200]}
🔄 <b>المحاولات الفاشلة:</b> {self.consecutive_failures}
━━━━━━━━━━━━━━━━━━
<i>جاري محاولة الإصلاح التلقائي...</i>
        """
        self._send_telegram_message(message)
    
    def _send_reconnect_notification(self, attempt: int, max_attempts: int, delay: int):
        """إرسال إشعار إعادة الاتصال"""
        message = f"""
🔄 <b>محاولة إعادة اتصال</b>
━━━━━━━━━━━━━━━━━━
🎯 <b>المحاولة:</b> {attempt}/{max_attempts}
⏳ <b>الانتظار:</b> {delay} ثانية
📊 <b>الإجمالي:</b> {self.total_reconnects} عملية إعادة اتصال
🔗 <b>الحالة:</b> جاري إعادة الاتصال...
━━━━━━━━━━━━━━━━━━
<i>سيتم إعلامك عند النجاح</i>
        """
        self._send_telegram_message(message)
    
    def _send_success_notification(self, operation: str, details: str = ""):
        """إرسال إشعار نجاح"""
        message = f"""
✅ <b>{operation} - ناجح</b>
━━━━━━━━━━━━━━━━━━
📅 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
🔄 <b>عدد العمليات:</b> {self.stats['operations_count']}
⏰ <b>مدة التشغيل:</b> {self._get_uptime()}
📊 <b>معدل النجاح:</b> {self._calculate_success_rate()}%
━━━━━━━━━━━━━━━━━━
📝 <b>التفاصيل:</b>
{details}
        """
        self._send_telegram_message(message)
    
    def _send_daily_report(self):
        """إرسال تقرير يومي"""
        uptime = self._get_uptime()
        success_rate = self._calculate_success_rate()
        
        message = f"""
📊 <b>تقرير أداء يومي</b>
━━━━━━━━━━━━━━━━━━
📅 <b>التاريخ:</b> {datetime.now().strftime('%Y-%m-%d')}
⏰ <b>مدة التشغيل:</b> {uptime}
🔄 <b>عمليات الدخول:</b> {self.stats['total_logins']}
❌ <b>فشل الدخول:</b> {self.stats['failed_logins']}
🔗 <b>إعادة الاتصال:</b> {self.total_reconnects}
📈 <b>معدل النجاح:</b> {success_rate}%
🔐 <b>الحالة الحالية:</b> {'✅ نشط' if self.is_logged_in else '❌ غير نشط'}
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
    
    # ========== نظام إعادة الاتصال التلقائي ==========
    
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
                    self.logger.warning("🔌 فقدان الاتصال، بدء إعادة الاتصال التلقائي...")
                    self.consecutive_failures += 1
                    
                    # إرسال إشعار الفشل
                    self._send_session_notification(
                        "فقدان الاتصال",
                        f"المحاولات الفاشلة المتتالية: {self.consecutive_failures}"
                    )
                    
                    # محاولة إعادة الاتصال
                    if self._smart_reconnect():
                        self.consecutive_failures = 0
                        self.total_reconnects += 1
                        self._send_session_notification(
                            "تم استعادة الاتصال",
                            f"تمت إعادة الاتصال بعد {self.consecutive_failures} محاولات فاشلة"
                        )
                    else:
                        # زيادة تأخير المحاولة التالية
                        extra_delay = min(self.consecutive_failures * 30, 300)
                        self.logger.info(f"⏳ زيادة التأخير إلى {extra_delay} ثانية")
                        time.sleep(extra_delay)
                
                # إرسال تقرير يومي في منتصف الليل
                if datetime.now().hour == 0 and datetime.now().minute < 5:
                    self._send_daily_report()
                    time.sleep(300)  # تأخير 5 دقائق لتجنب التكرار
                    
            except Exception as e:
                self.logger.error(f"❌ خطأ في حلقة إعادة الاتصال: {str(e)}")
                time.sleep(60)
    
    def _smart_reconnect(self, max_attempts=5):
        """إعادة اتصال ذكية مع محاولات متعددة"""
        for attempt in range(1, max_attempts + 1):
            try:
                # إرسال إشعار المحاولة
                delay = self._calculate_reconnect_delay(attempt)
                self._send_reconnect_notification(attempt, max_attempts, delay)
                
                # الانتظار قبل المحاولة
                time.sleep(delay)
                
                # إعادة تهيئة السكرابر
                self.scraper = None
                self.session_cookies = {}
                self.is_logged_in = False
                
                # محاولة تسجيل دخول جديد
                self.logger.info(f"🔄 محاولة إعادة اتصال {attempt}/{max_attempts}")
                
                success, data = self.login(max_retries=3)
                
                if success:
                    self.logger.info(f"✅ نجحت إعادة الاتصال في المحاولة {attempt}")
                    self.stats['last_success'] = datetime.now().strftime('%H:%M:%S')
                    return True
                else:
                    error_msg = data.get('error', 'خطأ غير معروف')
                    self.logger.warning(f"⚠️  فشلت محاولة {attempt}: {error_msg}")
                    
                    # تغيير User-Agent للمحاولة التالية
                    self._rotate_user_agent()
                    
            except Exception as e:
                self.logger.error(f"❌ خطأ في محاولة إعادة الاتصال {attempt}: {str(e)}")
        
        # فشلت جميع المحاولات
        self.logger.error("❌ فشلت جميع محاولات إعادة الاتصال")
        return False
    
    def _calculate_reconnect_delay(self, attempt):
        """حساب تأخير إعادة الاتصال"""
        # تأخير تصاعدي: 5, 15, 30, 60, 120 ثانية
        delays = [5, 15, 30, 60, 120]
        return delays[min(attempt - 1, len(delays) - 1)]
    
    # ========== نظام ضربات القلب المحسن ==========
    
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
                time.sleep(self.HEARTBEAT_INTERVAL)
                
                if self.is_logged_in:
                    # إجراء فحص صحي
                    if self._perform_health_check():
                        # تحديث وقت انتهاء الصلاحية
                        self.session_expiry = datetime.now() + timedelta(seconds=self.SESSION_TIMEOUT)
                        self.logger.debug("✅ فحص صحي ناجح")
                        
                        # التحقق من تجديد الجلسة
                        if self._is_session_expired():
                            self.logger.info("🔄 جلسة منتهية، جاري التجديد...")
                            self._refresh_session()
                    else:
                        self.logger.warning("⚠️  فحص صحي فاشل")
                        self.is_logged_in = False
                        
            except Exception as e:
                self.logger.error(f"❌ خطأ في حلقة ضربات القلب: {str(e)}")
                time.sleep(60)
    
    # ========== الدوال الأساسية المعدلة ==========
    
    def _init_scraper(self):
        """تهيئة السكرابر مع بدء الأنظمة المساعدة"""
        with self._session_lock:
            try:
                self.scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'mobile': False,
                        'desktop': True
                    },
                    delay=10
                )
                
                self.scraper.timeout = 30
                
                # بدء الأنظمة المساعدة
                self._start_heartbeat()
                self._start_auto_reconnect()
                
                return True
                    
            except Exception as e:
                self.logger.error(f"❌ فشل في تهيئة السكرابر: {str(e)}")
                self._send_error_notification(str(e), "_init_scraper")
                return False
    
    def login(self, max_retries=None):
        """تسجيل دخول مع تتبع الإحصائيات"""
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

                self.logger.info(f"🔐 محاولة تسجيل دخول {attempt + 1}/{max_retries}")
                
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
                    self._generate_session_id()
                    
                    self.logger.info("✅ تم تسجيل الدخول بنجاح")
                    
                    # إرسال إشعار النجاح
                    self._send_session_notification(
                        "تسجيل دخول ناجح",
                        f"المحاولة: {attempt + 1}\nمعرف الجلسة: {self.session_id}"
                    )
                    
                    self._retry_count = 0
                    self.consecutive_failures = 0
                    
                    return True, data
                else:
                    error_msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول")
                    self.logger.warning(f"⚠️  فشل تسجيل دخول: {error_msg}")
                    self.stats['failed_logins'] += 1
                    
                    if attempt < max_retries - 1:
                        self._smart_login_retry(attempt)
                        continue
                    
                    # إرسال إشعار الفشل
                    self._send_session_notification(
                        "فشل تسجيل دخول",
                        f"الخطأ: {error_msg}\nالمحاولة: {attempt + 1}/{max_retries}"
                    )
                    
                    return False, data

            except Exception as e:
                self.logger.error(f"❌ خطأ في تسجيل الدخول (محاولة {attempt + 1}): {str(e)}")
                self.stats['failed_logins'] += 1
                self.stats['last_error'] = str(e)
                
                if attempt < max_retries - 1:
                    self._smart_login_retry(attempt)
                else:
                    self._retry_count += 1
                    self._send_error_notification(str(e), "login")
                    return False, {"error": str(e)}
        
        return False, {"error": "تجاوز الحد الأقصى لمحاولات تسجيل الدخول"}
    
    def ensure_login(self):
        """التأكد من تسجيل الدخول مع إعادة الاتصال التلقائي"""
        with self._session_lock:
            # التحقق من الجلسة الحالية
            if (self.is_logged_in and 
                self.scraper and 
                self._is_session_valid() and 
                not self._is_session_expired()):
                
                self.logger.debug("✅ الجلسة سارية وصالحة")
                return True
            
            self.logger.info("🔄 محاولة تأسيس/استعادة الجلسة...")
            
            # محاولة تسجيل دخول جديد
            success, data = self.login()
            
            if not success:
                error_msg = data.get("error", data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول"))
                self.logger.error(f"❌ فشل في تأسيس الجلسة: {error_msg}")
                
                # إرسال إشعار الفشل
                self._send_session_notification(
                    "فشل تأسيس الجلسة",
                    f"الخطأ: {error_msg}\nسيتم المحاولة تلقائياً"
                )
                
                # نظام إعادة الاتصال التلقائي سيتولى المهمة
                return False
            
            return True
    
    def _perform_health_check(self):
        """فحص صحي مع إرسال إشعارات"""
        try:
            if not self.scraper or not self.is_logged_in:
                return False
                
            payload = {"page": 1, "pageSize": 1}
            
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS['statistics'],
                json=payload,
                headers=self._get_headers(),
                timeout=15
            )
            
            is_healthy = resp.status_code == 200 and 'result' in resp.text
            
            if not is_healthy:
                self.logger.warning(f"⚠️  فحص صحي فاشل: {resp.status_code}")
                self._send_session_notification(
                    "فحص صحي فاشل",
                    f"كود الحالة: {resp.status_code}"
                )
            
            return is_healthy
            
        except Exception as e:
            self.logger.debug(f"فحص صحي فاشل: {str(e)}")
            return False
    
    def _refresh_session(self):
        """تجديد الجلسة مع إشعارات"""
        try:
            if self._perform_health_check():
                self.session_expiry = datetime.now() + timedelta(seconds=self.SESSION_TIMEOUT)
                self.logger.info(f"✅ تم تجديد الجلسة حتى: {self.session_expiry.strftime('%H:%M:%S')}")
                return True
            else:
                self.logger.info("🔄 جلسة منتهية، جاري تسجيل دخول جديد...")
                self._send_session_notification("انتهت صلاحية الجلسة", "جاري التجديد...")
                return self.login()[0]
                
        except Exception as e:
            self.logger.error(f"❌ فشل في تجديد الجلسة: {str(e)}")
            self._send_error_notification(str(e), "_refresh_session")
            return False
    
    # ========== decorator معدل مع إشعارات ==========
    
    def with_retry(func):
        """مُعدِّل محسن مع تتبع الإحصائيات"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.stats['operations_count'] += 1
            function_name = func.__name__
            
            for attempt in range(3):
                try:
                    self.ensure_login()
                    
                    result = func(self, *args, **kwargs)
                    
                    if result is None:
                        continue
                    
                    # التحقق من وجود مشاكل
                    if isinstance(result, tuple) and len(result) >= 2:
                        status, data = result[0], result[1]
                        
                        if status == 403 or (isinstance(data, dict) and any(
                            keyword in str(data).lower() 
                            for keyword in ['captcha', 'cloudflare', 'security', 'block']
                        )):
                            self.logger.warning(f"⚠️  مشكلة أمان في {function_name}")
                            
                            if attempt < 2:
                                self._rotate_user_agent()
                                time.sleep(2 ** attempt)
                                self.is_logged_in = False
                                continue
                    
                    # إرسال إشعار نجاح للعمليات المهمة
                    if function_name in ['deposit_to_player', 'withdraw_from_player', 'create_player']:
                        details = f"{function_name} - نجاح"
                        if len(args) > 0:
                            details += f"\nالمعامل: {args[0]}"
                        self._send_success_notification(function_name, details)
                    
                    return result
                    
                except Exception as e:
                    self.logger.error(f"❌ خطأ في {function_name} (محاولة {attempt + 1}): {str(e)}")
                    self._send_error_notification(str(e), function_name)
                    
                    if attempt < 2:
                        time.sleep(2 ** attempt)
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
    
    def send_status_report(self):
        """إرسال تقرير حالة يدوي"""
        session_info = self.get_session_info()
        
        message = f"""
📋 <b>تقرير حالة يدوي</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔐 <b>حالة الدخول:</b> {'✅ متصل' if session_info['is_logged_in'] else '❌ منقطع'}
🆔 <b>معرف الجلسة:</b> {session_info['session_id'] or 'N/A'}
⏰ <b>عمر الجلسة:</b> {session_info['session_age'] or 'N/A'}
⏳ <b>مدة التشغيل:</b> {session_info['uptime']}
🔄 <b>إعادة الاتصال:</b> {session_info['total_reconnects']}
📊 <b>معدل النجاح:</b> {session_info['success_rate']}%
━━━━━━━━━━━━━━━━━━
📈 <b>الإحصائيات:</b>
• عمليات الدخول: {session_info['stats']['total_logins']}
• فشل الدخول: {session_info['stats']['failed_logins']}
• العمليات: {session_info['stats']['operations_count']}
━━━━━━━━━━━━━━━━━━
        """
        self._send_telegram_message(message)
        return message
    
    def stop(self):
        """إيقاف النظام بأمان"""
        self.logger.info("🛑 إيقاف النظام...")
        
        # إرسال إشعار الإيقاف
        uptime = self._get_uptime()
        stop_message = f"""
🛑 <b>إيقاف النظام</b>
━━━━━━━━━━━━━━━━━━
🕒 <b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
⏳ <b>مدة التشغيل:</b> {uptime}
🔄 <b>إعادة الاتصال:</b> {self.total_reconnects}
📊 <b>معدل النجاح:</b> {self._calculate_success_rate()}%
━━━━━━━━━━━━━━━━━━
<i>تم إيقاف النظام بنجاح</i>
        """
        self._send_telegram_message(stop_message)
        
        # إيقاف الخيوط
        self._stop_threads.set()
        
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)
        
        if self._auto_reconnect_thread and self._auto_reconnect_thread.is_alive():
            self._auto_reconnect_thread.join(timeout=5)
        
        # تنظيف الموارد
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.session_id = None
        self.scraper = None
        
        self.logger.info("✅ تم إيقاف النظام بنجاح")
    
    # ========== دوال API الأصلية (معدلة قليلاً) =========
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
# ========== مثال الاستخدام ==========

if __name__ == "__main__":
    # الطريقة 1: استخدام متغيرات البيئة
    api = IChancyAPI()
    
    # الطريقة 2: تحديد التوكن والقناة مباشرة
    # api = IChancyAPI(
    #     telegram_bot_token="YOUR_BOT_TOKEN",
    #     telegram_chat_id="-1003317405069"
    # )
    
    try:
        # بدء النظام
        api.ensure_login()
        
        # إرسال تقرير الحالة
        api.send_status_report()
        
        # استخدام API بشكل طبيعي
        # players = api.get_all_players()
        # print(f"عدد اللاعبين: {len(players)}")
        
        # البقاء نشطاً
        print("✅ النظام يعمل... اضغط Ctrl+C للإيقاف")
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\n🛑 إيقاف بطلب المستخدم...")
    except Exception as e:
        print(f"❌ خطأ: {e}")
    finally:
        api.stop()
