import os
import random
import string
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
        self.session = None
        self.session_expiry = None
        self.max_retries = 3  # عدد المحاولات عند فشل الجلسة

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard"
        }

    def _new_session(self):
        """إنشاء جلسة جديدة"""
        return IChancySession(self._headers())

    def _login(self, session: IChancySession):
        """تسجيل الدخول"""
        payload = {"username": self.USERNAME, "password": self.PASSWORD}
        r = session.scraper.post(
            self.ORIGIN + self.ENDPOINTS['signin'], 
            json=payload, 
            headers=session.headers, 
            timeout=15
        )
        data = r.json()
        if not data.get("result"):
            raise Exception(f"Login failed: {data}")
        
        # حفظ وقت انتهاء الصلاحية (مثال: 30 دقيقة)
        self.session_expiry = datetime.now() + timedelta(minutes=30)
        return True

    def _get_valid_session(self):
        """الحصول على جلسة صالحة مع إعادة المحاولة"""
        for attempt in range(self.max_retries):
            try:
                # إذا كانت الجلسة موجودة ولا تزال صالحة
                if self.session and self.session_expiry and datetime.now() < self.session_expiry:
                    if hasattr(self.session, 'is_valid') and self.session.is_valid():
                        return self.session
                
                # إنشاء جلسة جديدة
                self.session = self._new_session()
                self._login(self.session)
                return self.session
                
            except Exception as e:
                send_admin_log("⚠️ Session Login Attempt Failed", 
                             f"Attempt {attempt + 1}/{self.max_retries}\nError: {str(e)}")
                
                if attempt == self.max_retries - 1:
                    send_admin_log("❌ All Login Attempts Failed", 
                                 "Unable to establish session")
                    raise Exception(f"Failed to establish session after {self.max_retries} attempts")
                
                # انتظار قبل إعادة المحاولة
                import time
                time.sleep(2 ** attempt)  # Exponential backoff

    def _ensure_login(self):
        """التأكد من أن الجلسة صالحة (للتوافق مع الكود القديم)"""
        return self._get_valid_session()

    def _make_request(self, endpoint, payload, method='post', timeout=15):
        """دالة مساعدة لتنفيذ الطلبات مع إعادة المحاولة"""
        for attempt in range(self.max_retries):
            try:
                session = self._get_valid_session()
                
                if method.lower() == 'post':
                    r = session.scraper.post(
                        self.ORIGIN + endpoint,
                        json=payload,
                        headers=session.headers,
                        timeout=timeout
                    )
                else:
                    r = session.scraper.get(
                        self.ORIGIN + endpoint,
                        headers=session.headers,
                        timeout=timeout
                    )
                
                # التحقق من الاستجابة
                if r.status_code in [401, 403]:  # غير مصرح أو انتهت الجلسة
                    send_admin_log("🔑 Session Expired", "Refreshing session...")
                    self.session = None  # إجبار إنشاء جلسة جديدة
                    continue
                    
                return r
                
            except Exception as e:
                send_admin_log(f"⚠️ Request Failed (Attempt {attempt + 1})", str(e))
                if attempt == self.max_retries - 1:
                    raise
                
                import time
                time.sleep(1)

    # ======================
    # إنشاء حساب
    # ======================
    def create_player_with_credentials(self, login: str, password: str):
        try:
            email = f"{login}@agent.nsp"
            payload = {
                "player": {
                    "email": email,
                    "password": password,
                    "parentId": self.PARENT_ID,
                    "login": login
                }
            }

            r = self._make_request(
                self.ENDPOINTS['create'],
                payload,
                timeout=20
            )

            data = r.json() if r.content else {}
            
            if r.status_code == 200:
                send_admin_log(
                    "✅ Create Player",
                    f"👤 {login}\n📧 {email}\nID: {data.get('id', 'N/A')}"
                )
            else:
                send_admin_log(
                    "❌ Create Player Failed",
                    f"Status: {r.status_code}\nResponse: {data}"
                )

            return r.status_code, data

        except Exception as e:
            send_admin_log("❌ API Error", f"create_player\n{str(e)}")
            return 500, {"error": str(e)}

    # ======================
    # إيداع
    # ======================
    def deposit_to_player(self, player_id: str, amount: float):
        try:
            payload = {
                "playerId": player_id,
                "amount": amount,
                "currency": "NSP",
                "currencyCode": "NSP",
                "moneyStatus": 5
            }
            
            r = self._make_request(
                self.ENDPOINTS['deposit'],
                payload,
                timeout=15
            )
            
            data = r.json() if r.content else {}
            
            send_admin_log(
                "💰 Deposit",
                f"Player: {player_id}\nAmount: {amount}\nStatus: {r.status_code}"
            )
            return r.status_code, data
            
        except Exception as e:
            send_admin_log("❌ Deposit Error", str(e))
            return 500, {"error": str(e)}

    def logout(self):
        """إغلاق الجلسة الحالية"""
        if self.session:
            # إذا كان هناك دالة لإغلاق الجلسة
            if hasattr(self.session, 'close'):
                self.session.close()
            self.session = None
            self.session_expiry = None
            send_admin_log("🔒 Session Closed", "Logged out successfully")
