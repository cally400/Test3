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
        
    def _setup_logging(self):
        """تهيئة نظام التسجيل"""
        logging.basicConfig(
            level=logging.DEBUG,  # تغيير إلى DEBUG لرؤية المزيد
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
        """تهيئة السكرابر مع إعدادات إضافية"""
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False,
                    'desktop': True
                },
                delay=10,
                captcha={
                    'provider': '2captcha',
                    'api_key': os.getenv('CAPTCHA_API_KEY', '')
                } if os.getenv('CAPTCHA_API_KEY') else None
            )
            
            # إعدادات إضافية للطلبات
            self.scraper.headers.update({
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'DNT': '1',
                'Sec-GPC': '1',
            })
            
            self.logger.info("✅ تم تهيئة السكرابر بنجاح")
            
        except Exception as e:
            self.logger.error(f"❌ فشل في تهيئة السكرابر: {e}")
            raise

    def _is_session_valid(self):
        """التحقق من صلاحية الجلسة"""
        if not self.session_expiry or not self.last_login_time:
            return False
            
        if datetime.now() > self.session_expiry:
            self.logger.info("انتهت صلاحية الجلسة")
            return False
            
        return True

    def login(self):
        """تسجيل دخول الوكيل مع معالجة أفضل للأخطاء"""
        self.login_attempts += 1
        
        if not self.scraper:
            self._init_scraper()
            
        # أولاً: تحقق من اتصال الموقع
        try:
            test_resp = self.scraper.get(self.BASE_URL, timeout=10)
            self.logger.info(f"✅ اتصال الموقع: {test_resp.status_code}")
        except Exception as e:
            self.logger.error(f"❌ لا يمكن الاتصال بالموقع: {e}")
            return False, {"error": f"لا يمكن الاتصال بالموقع: {str(e)}"}

        payload = {
            "username": self.USERNAME,
            "password": self.PASSWORD
        }

        try:
            url = self.BASE_URL + self.ENDPOINTS['signin']
            self.logger.info(f"محاولة تسجيل الدخول إلى: {url}")
            
            resp = self.scraper.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            
            self.logger.info(f"استجابة تسجيل الدخول: {resp.status_code}")
            self.logger.debug(f"رأس الاستجابة: {resp.headers}")
            
            # التحقق من نوع المحتوى
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' in content_type:
                self.logger.warning("الاستجابة هي HTML وليست JSON")
                # ربما تمت إعادة التوجيه إلى صفحة تسجيل دخول
                if resp.status_code == 200 and '<!DOCTYPE html>' in resp.text[:100]:
                    return False, {"error": "تم إعادة التوجيه إلى صفحة HTML، ربما هناك CAPTCHA"}
            
            # محاولة تحليل JSON
            try:
                data = resp.json()
                self.logger.info(f"تم تحليل JSON بنجاح: {data.get('result', 'N/A')}")
            except json.JSONDecodeError as e:
                self.logger.error(f"❌ فشل في تحليل JSON: {e}")
                self.logger.debug(f"نص الاستجابة: {resp.text[:500]}")
                return False, {"error": f"استجابة غير صالحة: {resp.text[:100]}"}
            
            if data.get("result", False):
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=30)
                self.last_login_time = datetime.now()
                self.is_logged_in = True
                self.login_attempts = 0
                
                self.logger.info(f"✅ تم تسجيل الدخول بنجاح")
                self.logger.info(f"عدد الكوكيز: {len(self.session_cookies)}")
                return True, data
            else:
                error_msg = data.get("notification", [{}])[0].get("content", "فشل تسجيل الدخول")
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
        if self.login_attempts >= self.max_login_attempts:
            self.logger.error("❌ تجاوز الحد الأقصى لمحاولات تسجيل الدخول")
            raise Exception("تجاوز الحد الأقصى لمحاولات تسجيل الدخول")
            
        if not self.scraper:
            self._init_scraper()
            
        if self._is_session_valid() and self.is_logged_in:
            self.logger.info("✅ الجلسة سارية بالفعل")
            return True
            
        self.logger.info("🔄 الجلسة منتهية، جاري تسجيل الدخول...")
        success, data = self.login()
        
        if not success:
            error_msg = "فشل تسجيل الدخول"
            if isinstance(data, dict):
                if 'error' in data:
                    error_msg = data['error']
                elif 'notification' in data and data['notification']:
                    error_msg = data['notification'][0].get('content', error_msg)
            
            self.logger.error(f"❌ فشل في تسجيل الدخول: {error_msg}")
            raise Exception(f"فشل في تسجيل الدخول: {error_msg}")
            
        return True
