
# ichancy_api_selenium.py - باستخدام Selenium مجاناً
import os
import time
import json
import logging
import redis
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime, timedelta
import random

class IChancySeleniumAPI:
    """API باستخدام Selenium مجاناً لتجاوز الكابتشا"""
    
    def __init__(self, headless=True):
        self._setup_logging()
        self._load_config()
        self.driver = None
        self.headless = headless
        self.is_logged_in = False
        self.redis = None
        
        # مفاتيح Redis
        self.REDIS_SESSION_KEY = "ichancy:selenium_session"
        self.REDIS_LOCK_KEY = "ichancy:selenium_lock"
        
        self._init_redis()
        self._init_driver()
    
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)
    
    def _load_config(self):
        """تحميل الإعدادات"""
        self.BASE_URL = os.getenv("ICHANCY_ORIGIN", "https://agents.ichancy.com")
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
        self.PARENT_ID = os.getenv("PARENT_ID")
        
        # User Agents متنوعة
        self.USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
    
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
    
    def _init_driver(self):
        """تهيئة متصفح Chrome غير مكتشف"""
        if self.driver:
            return
        
        try:
            options = uc.ChromeOptions()
            
            # إعدادات للتخفي
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-notifications')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-infobars')
            options.add_argument('--disable-web-security')
            options.add_argument('--allow-running-insecure-content')
            
            # تغيير User-Agent عشوائياً
            user_agent = random.choice(self.USER_AGENTS)
            options.add_argument(f'user-agent={user_agent}')
            
            # إعدادات للخوادم بدون واجهة
            if self.headless:
                options.add_argument('--headless=new')
            
            # إعدادات إضافية
            prefs = {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_settings.popups": 0,
                "download_restrictions": 3,
                "safebrowsing.enabled": True
            }
            options.add_experimental_option("prefs", prefs)
            
            # إخفاء WebDriver
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # إنشاء Driver
            self.driver = uc.Chrome(
                options=options,
                version_main=120  # استخدام إصدار Chrome 120
            )
            
            # تنفيذ scripts للتخفي
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.driver.execute_script(
                """
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                """
            )
            self.driver.execute_script(
                """
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                """
            )
            
            self.logger.info("✅ تم تهيئة متصفح Selenium بنجاح")
            
        except Exception as e:
            self.logger.error(f"❌ فشل تهيئة المتصفح: {e}")
            raise
    
    def _wait_and_click(self, by, value, timeout=10):
        """انتظار عنصر والنقر عليه"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            time.sleep(random.uniform(0.5, 1.5))  # تأخير بشري
            element.click()
            return True
        except TimeoutException:
            self.logger.warning(f"⏳ انتهى الوقت للعنصر: {value}")
            return False
    
    def _wait_and_send_keys(self, by, value, text, timeout=10):
        """انتظار عنصر وإدخال نص"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            time.sleep(random.uniform(0.3, 0.8))  # تأخير بشري
            
            # محاكاة الكتابة البشرية
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            return True
        except TimeoutException:
            self.logger.warning(f"⏳ انتهى الوقت لإدخال النص في: {value}")
            return False
    
    def _is_element_present(self, by, value, timeout=5):
        """التحقق من وجود عنصر"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return True
        except:
            return False
    
    def login(self):
        """تسجيل الدخول إلى لوحة التحكم"""
        try:
            self.logger.info("🚀 بدء تسجيل الدخول...")
            
            # الانتقال إلى صفحة تسجيل الدخول
            login_url = f"{self.BASE_URL}/dashboard"
            self.driver.get(login_url)
            time.sleep(random.uniform(3, 5))
            
            # التحقق من وجود حقول تسجيل الدخول
            username_selectors = [
                (By.NAME, "username"),
                (By.ID, "username"),
                (By.XPATH, "//input[@type='text' and contains(@placeholder, 'username')]"),
                (By.CSS_SELECTOR, "input[type='text']")
            ]
            
            password_selectors = [
                (By.NAME, "password"),
                (By.ID, "password"),
                (By.XPATH, "//input[@type='password']"),
                (By.CSS_SELECTOR, "input[type='password']")
            ]
            
            # البحث عن حقل اسم المستخدم
            username_found = False
            for by, value in username_selectors:
                if self._wait_and_send_keys(by, value, self.USERNAME, timeout=15):
                    username_found = True
                    break
            
            if not username_found:
                raise Exception("لم يتم العثور على حقل اسم المستخدم")
            
            time.sleep(random.uniform(1, 2))
            
            # البحث عن حقل كلمة المرور
            password_found = False
            for by, value in password_selectors:
                if self._wait_and_send_keys(by, value, self.PASSWORD, timeout=15):
                    password_found = True
                    break
            
            if not password_found:
                raise Exception("لم يتم العثور على حقل كلمة المرور")
            
            time.sleep(random.uniform(1, 2))
            
            # البحث عن زر تسجيل الدخول
            login_button_selectors = [
                (By.XPATH, "//button[@type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Sign In')]"),
                (By.XPATH, "//button[contains(text(), 'Login')]"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//input[@type='submit']")
            ]
            
            login_success = False
            for by, value in login_button_selectors:
                if self._wait_and_click(by, value, timeout=15):
                    login_success = True
                    break
            
            if not login_success:
                # محاولة النقر باستخدام JavaScript
                self.driver.execute_script("document.querySelector('button[type=\"submit\"]').click();")
            
            # انتظار تحميل الصفحة التالية
            time.sleep(random.uniform(5, 8))
            
            # التحقق من نجاح تسجيل الدخول
            current_url = self.driver.current_url
            if "dashboard" in current_url and "login" not in current_url:
                self.is_logged_in = True
                self.logger.info("✅ تم تسجيل الدخول بنجاح")
                
                # حفظ الكوكيز في Redis
                self._save_cookies()
                return True, {"status": True, "message": "تم تسجيل الدخول بنجاح"}
            else:
                # التحقق من رسائل الخطأ
                error_selectors = [
                    (By.CLASS_NAME, "error"),
                    (By.CLASS_NAME, "alert-danger"),
                    (By.CLASS_NAME, "text-danger"),
                    (By.XPATH, "//div[contains(@class, 'error')]")
                ]
                
                for by, value in error_selectors:
                    try:
                        error_element = self.driver.find_element(by, value)
                        error_text = error_element.text
                        self.logger.error(f"❌ خطأ في تسجيل الدخول: {error_text}")
                        return False, {"error": error_text}
                    except:
                        continue
                
                self.logger.error("❌ فشل تسجيل الدخول - غير معروف")
                return False, {"error": "فشل تسجيل الدخول"}
                
        except Exception as e:
            self.logger.error(f"❌ استثناء في تسجيل الدخول: {str(e)}")
            
            # حفظ لقطة شاشة للتصحيح
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"login_error_{timestamp}.png"
                self.driver.save_screenshot(screenshot_path)
                self.logger.info(f"📸 تم حفظ لقطة الشاشة: {screenshot_path}")
            except:
                pass
            
            return False, {"error": str(e)}
    
    def _save_cookies(self):
        """حفظ الكوكيز في Redis"""
        try:
            cookies = self.driver.get_cookies()
            self.redis.setex(
                self.REDIS_SESSION_KEY,
                1800,  # 30 دقيقة
                json.dumps({
                    "cookies": cookies,
                    "timestamp": datetime.now().isoformat(),
                    "url": self.driver.current_url
                })
            )
            self.logger.info("💾 تم حفظ الكوكيز في Redis")
        except Exception as e:
            self.logger.error(f"❌ فشل حفظ الكوكيز: {e}")
    
    def _load_cookies(self):
        """تحميل الكوكيز من Redis"""
        try:
            data = self.redis.get(self.REDIS_SESSION_KEY)
            if not data:
                return False
            
            session_data = json.loads(data)
            cookies = session_data.get("cookies", [])
            
            if not cookies:
                return False
            
            # الانتقال إلى الموقع أولاً
            self.driver.get(self.BASE_URL)
            time.sleep(2)
            
            # إضافة الكوكيز
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    continue
            
            # تحديث الصفحة
            self.driver.refresh()
            time.sleep(3)
            
            # التحقق من أننا مسجلين الدخول
            if "dashboard" in self.driver.current_url and "login" not in self.driver.current_url:
                self.is_logged_in = True
                self.logger.info("✅ تم استعادة الجلسة من الكوكيز")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"❌ فشل تحميل الكوكيز: {e}")
            return False
    
    def ensure_login(self):
        """التأكد من تسجيل الدخول"""
        if self.is_logged_in:
            # التحقق السريع من أن الجلسة لا تزال نشطة
            try:
                self.driver.get(f"{self.BASE_URL}/dashboard")
                time.sleep(2)
                if "login" not in self.driver.current_url:
                    return True
            except:
                pass
        
        # محاولة تحميل الجلسة من الكوكيز
        if self._load_cookies():
            return True
        
        # تسجيل الدخول جديد
        success, result = self.login()
        if not success:
            raise Exception(f"فشل تسجيل الدخول: {result.get('error', 'غير معروف')}")
        
        return True
    
    def check_player_exists(self, username):
        """التحقق من وجود اللاعب"""
        try:
            self.ensure_login()
            
            # الانتقال إلى صفحة اللاعبين
            players_url = f"{self.BASE_URL}/dashboard/players"
            self.driver.get(players_url)
            time.sleep(random.uniform(4, 6))
            
            # البحث عن حقل البحث
            search_selectors = [
                (By.XPATH, "//input[@placeholder='Search players']"),
                (By.XPATH, "//input[contains(@placeholder, 'search')]"),
                (By.CSS_SELECTOR, "input[type='search']"),
                (By.NAME, "search")
            ]
            
            search_found = False
            for by, value in search_selectors:
                if self._wait_and_send_keys(by, value, username, timeout=10):
                    search_found = True
                    break
            
            if not search_found:
                self.logger.warning("⚠️ لم يتم العثور على حقل البحث")
                return False, {"error": "لم يتم العثور على حقل البحث"}
            
            time.sleep(random.uniform(2, 4))
            
            # النقر على زر البحث أو انتظار النتائج
            search_button_selectors = [
                (By.XPATH, "//button[contains(text(), 'Search')]"),
                (By.XPATH, "//button[@type='submit']"),
                (By.CSS_SELECTOR, "button[type='submit']")
            ]
            
            for by, value in search_button_selectors:
                if self._wait_and_click(by, value, timeout=5):
                    time.sleep(random.uniform(3, 5))
                    break
            
            # البحث عن النتائج في الجدول
            try:
                # انتظار تحميل الجدول
                time.sleep(random.uniform(3, 5))
                
                # البحث عن اسم المستخدم في الصفحة
                page_source = self.driver.page_source
                
                # طريقة 1: البحث في نص الصفحة
                if username.lower() in page_source.lower():
                    self.logger.info(f"✅ اللاعب '{username}' موجود")
                    return True, {"exists": True}
                
                # طريقة 2: البحث في الجداول
                table_selectors = [
                    (By.TAG_NAME, "table"),
                    (By.CLASS_NAME, "table"),
                    (By.XPATH, "//table")
                ]
                
                for by, value in table_selectors:
                    try:
                        tables = self.driver.find_elements(by, value)
                        for table in tables:
                            if username in table.text:
                                self.logger.info(f"✅ اللاعب '{username}' موجود في الجدول")
                                return True, {"exists": True}
                    except:
                        continue
                
                self.logger.info(f"ℹ️ اللاعب '{username}' غير موجود")
                return False, {"exists": False}
                
            except Exception as e:
                self.logger.error(f"❌ خطأ في البحث: {e}")
                return False, {"error": str(e)}
                
        except Exception as e:
            self.logger.error(f"❌ استثناء في التحقق من اللاعب: {e}")
            return False, {"error": str(e)}
    
    def create_player(self, username, password):
        """إنشاء لاعب جديد"""
        try:
            self.ensure_login()
            
            # الانتقال إلى صفحة إنشاء لاعب جديد
            create_url = f"{self.BASE_URL}/dashboard/players/create"
            self.driver.get(create_url)
            time.sleep(random.uniform(4, 6))
            
            # حقل اسم المستخدم
            username_selectors = [
                (By.NAME, "login"),
                (By.NAME, "username"),
                (By.ID, "login"),
                (By.ID, "username"),
                (By.XPATH, "//input[@placeholder='Username']"),
                (By.XPATH, "//input[@placeholder='Login']")
            ]
            
            username_filled = False
            for by, value in username_selectors:
                if self._wait_and_send_keys(by, value, username, timeout=10):
                    username_filled = True
                    break
            
            if not username_filled:
                raise Exception("لم يتم العثور على حقل اسم المستخدم")
            
            time.sleep(random.uniform(1, 2))
            
            # حقل كلمة المرور
            password_selectors = [
                (By.NAME, "password"),
                (By.ID, "password"),
                (By.XPATH, "//input[@type='password' and contains(@placeholder, 'password')]")
            ]
            
            password_filled = False
            for by, value in password_selectors:
                if self._wait_and_send_keys(by, value, password, timeout=10):
                    password_filled = True
                    break
            
            if not password_filled:
                raise Exception("لم يتم العثور على حقل كلمة المرور")
            
            time.sleep(random.uniform(1, 2))
            
            # حقل تأكيد كلمة المرور
            confirm_selectors = [
                (By.NAME, "confirm_password"),
                (By.NAME, "password_confirmation"),
                (By.ID, "confirm_password"),
                (By.XPATH, "//input[@placeholder='Confirm Password']")
            ]
            
            for by, value in confirm_selectors:
                if self._wait_and_send_keys(by, value, password, timeout=5):
                    break
            
            time.sleep(random.uniform(1, 2))
            
            # حقل البريد الإلكتروني
            email = f"{username}@player.ichancy.com"
            email_selectors = [
                (By.NAME, "email"),
                (By.ID, "email"),
                (By.XPATH, "//input[@type='email']")
            ]
            
            for by, value in email_selectors:
                if self._wait_and_send_keys(by, value, email, timeout=5):
                    break
            
            time.sleep(random.uniform(1, 2))
            
            # النقر على زر الإنشاء
            create_button_selectors = [
                (By.XPATH, "//button[contains(text(), 'Create')]"),
                (By.XPATH, "//button[contains(text(), 'Save')]"),
                (By.XPATH, "//button[@type='submit']"),
                (By.CSS_SELECTOR, "button[type='submit']")
            ]
            
            created = False
            for by, value in create_button_selectors:
                if self._wait_and_click(by, value, timeout=10):
                    created = True
                    break
            
            if not created:
                # محاولة باستخدام JavaScript
                self.driver.execute_script("""
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.includes('Create') || buttons[i].textContent.includes('Save')) {
                            buttons[i].click();
                            break;
                        }
                    }
                """)
            
            # انتظار النتيجة
            time.sleep(random.uniform(5, 8))
            
            # التحقق من نجاح الإنشاء
            success_indicators = [
                "Player created successfully",
                "تم إنشاء اللاعب بنجاح",
                "success",
                "Created successfully"
            ]
            
            page_source = self.driver.page_source
            for indicator in success_indicators:
                if indicator.lower() in page_source.lower():
                    self.logger.info(f"✅ تم إنشاء اللاعب '{username}' بنجاح")
                    
                    # محاولة الحصول على معرف اللاعب
                    player_id = self._extract_player_id(username)
                    
                    return 200, {
                        "status": True,
                        "message": "تم إنشاء اللاعب بنجاح",
                        "username": username,
                        "email": email
                    }, player_id
            
            # التحقق من الأخطاء
            error_indicators = [
                "already exists",
                "مستخدم مسبقاً",
                "error",
                "فشل"
            ]
            
            for indicator in error_indicators:
                if indicator.lower() in page_source.lower():
                    error_msg = f"اللاعب '{username}' موجود مسبقاً أو حدث خطأ"
                    self.logger.error(f"❌ {error_msg}")
                    return 400, {
                        "status": False,
                        "error": error_msg
                    }, None
            
            # إذا لم نجد رسالة نجاح أو خطأ واضحة
            # نتحقق من تغيير URL أو ظهور رسالة جديدة
            current_url = self.driver.current_url
            if "create" not in current_url and "players" in current_url:
                # ربما نجحت العملية
                player_id = self._extract_player_id(username)
                return 200, {
                    "status": True,
                    "message": "تم إنشاء اللاعب (مرجح)",
                    "username": username,
                    "email": email
                }, player_id
            
            self.logger.warning("⚠️ لا يمكن تحديد نتيجة إنشاء اللاعب")
            return 500, {
                "status": False,
                "error": "لا يمكن تحديد نتيجة العملية"
            }, None
            
        except Exception as e:
            self.logger.error(f"❌ استثناء في إنشاء اللاعب: {e}")
            
            # حفظ لقطة شاشة
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"create_error_{timestamp}.png"
                self.driver.save_screenshot(screenshot_path)
                self.logger.info(f"📸 تم حفظ لقطة الشاشة: {screenshot_path}")
            except:
                pass
            
            return 500, {
                "status": False,
                "error": str(e)
            }, None
    
    def _extract_player_id(self, username):
        """استخراج معرف اللاعب"""
        try:
            # الانتقال إلى صفحة اللاعبين والبحث عن المعرف
            players_url = f"{self.BASE_URL}/dashboard/players"
            self.driver.get(players_url)
            time.sleep(4)
            
            # البحث عن اللاعب في الجدول
            try:
                # البحث عن الصف الذي يحتوي على اسم المستخدم
                rows = self.driver.find_elements(By.XPATH, "//tr")
                for row in rows:
                    if username in row.text:
                        # محاولة استخراج المعرف من الصف
                        cells = row.find_elements(By.TAG_NAME, "td")
                        for cell in cells:
                            text = cell.text.strip()
                            # البحث عن معرف (عادة يبدأ بـ P أو رقم)
                            if text.startswith("P") or text.isdigit():
                                return text
            except:
                pass
            
            # إذا لم نجد، نستخدم معرف مؤقت
            return f"P{int(time.time())}"
            
        except:
            return None
    
    def close(self):
        """إغلاق المتصفح"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("👋 تم إغلاق المتصفح")
            except:
                pass
    
    def __del__(self):
        """التنظيف"""
        self.close()
