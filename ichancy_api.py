import os
import random
import string
import time
import traceback
from datetime import datetime, timedelta
from ichancy_session import IChancySession
from admin_logger import send_admin_log

class IChancyAPI:

    ORIGIN = "https://agents.ichancy.com"
    ENDPOINTS = {
        'signin': "/global/api/User/signIn",
        'create': "/global/api/Player/registerPlayer",
        'statistics': "/global/api/Statistics/getPlayersStatisticsPro",
        'deposit': "/global/api/Player/depositToPlayer",
        'withdraw': "/global/api/Player/withdrawFromPlayer",
        'balance': "/global/api/Player/getPlayerBalanceById"
    }

    def __init__(self):
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
        self.PARENT_ID = os.getenv("PARENT_ID")
        
        # التحقق من وجود المتغيرات البيئية
        if not all([self.USERNAME, self.PASSWORD, self.PARENT_ID]):
            missing = []
            if not self.USERNAME: missing.append("AGENT_USERNAME")
            if not self.PASSWORD: missing.append("AGENT_PASSWORD")
            if not self.PARENT_ID: missing.append("PARENT_ID")
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")
        
        self.session = None
        self.session_expiry = None
        self.max_retries = 3
        self.request_timeout = 30  # زيادة الوقت المهلة

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _new_session(self):
        """إنشاء جلسة جديدة"""
        try:
            send_admin_log("🔄 Creating New Session", "Initializing...")
            session = IChancySession(self._headers())
            
            # اختبار الاتصال أولاً
            test_response = session.scraper.get(
                self.ORIGIN, 
                headers=session.headers, 
                timeout=10,
                verify=False  # مؤقتاً للاختبار
            )
            
            if test_response.status_code == 200:
                send_admin_log("✅ Session Created", "Connection successful")
            else:
                send_admin_log("⚠️ Session Warning", f"Connection status: {test_response.status_code}")
            
            return session
        except Exception as e:
            send_admin_log("❌ Session Creation Failed", f"Error: {str(e)}\n{traceback.format_exc()}")
            raise

    def _login(self, session: IChancySession):
        """تسجيل الدخول"""
        try:
            send_admin_log("🔑 Attempting Login", f"Username: {self.USERNAME[:3]}***")
            
            payload = {
                "username": self.USERNAME,
                "password": self.PASSWORD
            }
            
            # إضافة مزيد من المعلومات للتصحيح
            full_url = self.ORIGIN + self.ENDPOINTS['signin']
            send_admin_log("🌐 Login Request", f"URL: {full_url}")
            
            r = session.scraper.post(
                full_url,
                json=payload,
                headers=session.headers,
                timeout=self.request_timeout,
                verify=False  # مؤقتاً للاختبار
            )
            
            send_admin_log("📥 Login Response", f"Status: {r.status_code}")
            
            if r.status_code != 200:
                send_admin_log("❌ Login HTTP Error", f"Status: {r.status_code}\nResponse: {r.text[:200]}")
                raise Exception(f"HTTP {r.status_code}: {r.reason}")
            
            try:
                data = r.json()
                send_admin_log("📊 Login JSON", f"Response keys: {list(data.keys())}")
                
                if data.get("result"):
                    self.session_expiry = datetime.now() + timedelta(minutes=30)
                    send_admin_log("✅ Login Successful", "Session established")
                    return True
                else:
                    error_msg = data.get("message", data.get("error", "Unknown error"))
                    send_admin_log("❌ Login API Error", f"Error: {error_msg}")
                    raise Exception(f"Login failed: {error_msg}")
                    
            except ValueError as e:
                send_admin_log("❌ JSON Parse Error", f"Response text: {r.text[:200]}")
                raise Exception(f"Invalid JSON response: {str(e)}")
                
        except Exception as e:
            send_admin_log("❌ Login Exception", f"{str(e)}\n{traceback.format_exc()}")
            raise

    def _get_valid_session(self):
        """الحصول على جلسة صالحة مع إعادة المحاولة"""
        for attempt in range(self.max_retries):
            try:
                send_admin_log(f"🔄 Session Attempt", f"Attempt {attempt + 1}/{self.max_retries}")
                
                # إذا كانت الجلسة صالحة
                if self.session and self.session_expiry:
                    time_diff = (self.session_expiry - datetime.now()).total_seconds()
                    if time_diff > 60:  # إذا بقي أكثر من دقيقة
                        if hasattr(self.session, 'is_valid') and self.session.is_valid():
                            send_admin_log("✅ Using Existing Session", f"Time left: {int(time_diff)}s")
                            return self.session
                    else:
                        send_admin_log("⏰ Session Expiring", "Creating new session...")
                
                # إنشاء جلسة جديدة
                self.session = self._new_session()
                self._login(self.session)
                return self.session
                
            except Exception as e:
                error_msg = f"Attempt {attempt + 1} failed: {str(e)}"
                send_admin_log("⚠️ Session Attempt Failed", error_msg)
                
                if attempt == self.max_retries - 1:
                    final_error = f"Failed to establish session after {self.max_retries} attempts"
                    send_admin_log("❌ All Attempts Failed", final_error)
                    raise Exception(final_error)
                
                # انتظار تصاعدي قبل إعادة المحاولة
                wait_time = 2 ** attempt
                send_admin_log("⏳ Waiting", f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)

    def _ensure_login(self):
        """التأكد من أن الجلسة صالحة"""
        return self._get_valid_session()

    def _make_request(self, endpoint, payload, method='post', timeout=30):
        """دالة مساعدة لتنفيذ الطلبات"""
        for attempt in range(self.max_retries):
            try:
                session = self._get_valid_session()
                
                full_url = self.ORIGIN + endpoint
                send_admin_log(f"🌐 {method.upper()} Request", 
                             f"URL: {endpoint}\nAttempt: {attempt + 1}/{self.max_retries}")
                
                if method.lower() == 'post':
                    r = session.scraper.post(
                        full_url,
                        json=payload,
                        headers=session.headers,
                        timeout=timeout,
                        verify=False
                    )
                else:
                    r = session.scraper.get(
                        full_url,
                        headers=session.headers,
                        timeout=timeout,
                        verify=False
                    )
                
                send_admin_log(f"📥 Response", f"Status: {r.status_code}")
                
                if r.status_code in [401, 403, 419]:
                    send_admin_log("🔑 Session Expired", f"Status {r.status_code}, refreshing...")
                    self.session = None
                    self.session_expiry = None
                    continue
                    
                return r
                
            except Exception as e:
                send_admin_log(f"⚠️ Request Failed", f"Attempt {attempt + 1}: {str(e)}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(1)

    def check_player_exists(self, username: str):
        """التحقق من وجود لاعب بالاسم"""
        try:
            send_admin_log("🔍 Checking Player", f"Username: {username}")
            
            # بدلاً من استخدام statistics endpoint الذي قد يكون معقداً
            # سنستخدم approach أبسط: محاولة إنشاء الحساب ستظهر إذا كان موجوداً
            
            # في الوقت الحالي، نفترض أنه غير موجود لتجنب المنع
            # يمكنك تعديل هذا بناءً على API المنصة
            return False
            
        except Exception as e:
            send_admin_log("⚠️ Check Player Error", str(e))
            return False

    def create_player_with_credentials(self, username: str, password: str):
        """إنشاء لاعب"""
        try:
            email = f"{username}@agent.nsp"
            payload = {
                "player": {
                    "email": email,
                    "password": password,
                    "parentId": self.PARENT_ID,
                    "login": username,
                    "currency": "NSP",
                    "country": "SA",  # السعودية
                    "language": "ar",
                    "phone": "",
                    "firstName": username,
                    "lastName": "Player"
                }
            }
            
            send_admin_log("👤 Creating Player", f"Username: {username}\nEmail: {email}")
            
            r = self._make_request(
                self.ENDPOINTS['create'],
                payload,
                timeout=40
            )
            
            # محاولة تحليل الاستجابة
            response_text = r.text
            data = {}
            
            try:
                if response_text:
                    data = r.json()
            except:
                # إذا فشل تحليل JSON، نستخدم النص
                data = {"raw_response": response_text[:500]}
            
            send_admin_log("📊 Create Response", 
                         f"Status: {r.status_code}\n"
                         f"Success: {r.status_code == 200}\n"
                         f"Has ID: {'id' in data}")
            
            if r.status_code == 200:
                player_id = data.get('id') or data.get('playerId')
                
                if player_id:
                    send_admin_log("✅ Player Created Successfully",
                                 f"Username: {username}\nID: {player_id}")
                    
                    # إذا لم يكن هناك id في data، نعيد username كـ player_id
                    if not player_id:
                        player_id = username
                    
                    return r.status_code, data, player_id, email
                else:
                    # حتى إذا كانت 200 ولكن لا يوجد ID
                    send_admin_log("⚠️ Player Created but no ID",
                                 f"Response: {data}")
                    return r.status_code, data, None, email
            else:
                error_msg = f"HTTP {r.status_code}"
                if isinstance(data, dict):
                    if "message" in data:
                        error_msg = data["message"]
                    elif "error" in data:
                        error_msg = data["error"]
                
                send_admin_log("❌ Create Player Failed",
                             f"Status: {r.status_code}\nError: {error_msg}")
                
                return r.status_code, data, None, email
                
        except Exception as e:
            send_admin_log("❌ Create Player Exception",
                         f"Error: {str(e)}\n{traceback.format_exc()}")
            return 500, {"error": str(e), "traceback": traceback.format_exc()}, None, None

    # باقي الدوال تبقى كما هي...
    def deposit_to_player(self, player_id: str, amount: float):
        """إيداع"""
        try:
            payload = {
                "playerId": player_id,
                "amount": amount,
                "currency": "NSP",
                "currencyCode": "NSP",
                "moneyStatus": 5
            }
            
            send_admin_log("💰 Deposit Request", f"Player: {player_id}, Amount: {amount}")
            
            r = self._make_request(
                self.ENDPOINTS['deposit'],
                payload,
                timeout=30
            )
            
            data = r.json() if r.content else {}
            
            send_admin_log("💳 Deposit Response",
                         f"Status: {r.status_code}\n"
                         f"Player: {player_id}\n"
                         f"Amount: {amount}")
            
            return r.status_code, data
            
        except Exception as e:
            send_admin_log("❌ Deposit Error", str(e))
            return 500, {"error": str(e)}

    def get_player_balance(self, player_id: str):
        """جلب الرصيد"""
        try:
            payload = {"playerId": player_id}
            
            r = self._make_request(
                self.ENDPOINTS['balance'],
                payload,
                timeout=20
            )
            
            data = r.json() if r.content else {}
            
            return r.status_code, data
            
        except Exception as e:
            send_admin_log("❌ Balance Error", str(e))
            return 500, {"error": str(e)}

    def logout(self):
        """إغلاق الجلسة"""
        if self.session:
            self.session = None
            self.session_expiry = None
            send_admin_log("🔒 Session Closed", "Manual logout")
