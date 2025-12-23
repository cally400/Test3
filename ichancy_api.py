
import cloudscraper
import random
import string
import os
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional, List
from functools import wraps

# ملف الجلسة المشترك مع session_manager
COOKIE_FILE = "ichancy_session.json"

# إعداد اللوجينج مرة واحدة
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


class IChancyAPI:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._load_config()

        # Lazy initialization
        self.scraper = None

        # Session state
        self.is_logged_in: bool = False
        self.session_cookies: Dict = {}
        self.session_expiry: Optional[datetime] = None
        self.last_login_time: Optional[datetime] = None

    # =========================
    # إعدادات عامة
    # =========================
    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME", "twd_bot@agent.nsp")
        self.PASSWORD = os.getenv("AGENT_PASSWORD", "Twd@@123")
        self.PARENT_ID = os.getenv("PARENT_ID", "2470819")

        self.ORIGIN = os.getenv("ICHANCY_ORIGIN", "https://agents.ichancy.com")

        self.ENDPOINTS = {
            "signin": "/global/api/User/signIn",
            "create": "/global/api/Player/registerPlayer",
            "statistics": "/global/api/Statistics/getPlayersStatisticsPro",
            "deposit": "/global/api/Player/depositToPlayer",
            "withdraw": "/global/api/Player/withdrawFromPlayer",
            "balance": "/global/api/Player/getPlayerBalanceById",
        }

        self.USER_AGENT = (
            "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.5249.126 Mobile Safari/537.36"
        )
        self.REFERER = self.ORIGIN + "/dashboard"

        self.REQUEST_TIMEOUT = 25

    # =========================
    # إدارة الـ scraper والجلسة
    # =========================
    def _init_scraper(self):
        if self.scraper is not None:
            return

        self.scraper = cloudscraper.create_scraper(
            browser={
                "browser": "chrome",
                "platform": "windows",
                "mobile": False,
            }
        )

        # تحميل الكوكيز فقط إن وجدت (من session_manager)
        if self.session_cookies:
            self.scraper.cookies.update(self.session_cookies)

    def _is_session_valid(self) -> bool:
        if not self.session_expiry or not self.last_login_time:
            return False

        now = datetime.now()
        if now >= self.session_expiry:
            return False

        # حماية إضافية: لا نستخدم جلسة أقدم من ساعتين
        if now - self.last_login_time >= timedelta(hours=2):
            return False

        return True

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER,
        }

    def _check_captcha(self, response) -> bool:
        try:
            text = response.text.lower()
        except Exception:
            return False

        if "captcha" in text or "cloudflare" in text:
            self.logger.warning("⚠️ تم اكتشاف كابتشا/Cloudflare")
            return True
        return False

    def _invalidate_session(self):
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None

    def _save_session_to_file(self):
        """حفظ الجلسة مباشرة من داخل API لتفادي الاستيراد الدائري"""
        try:
            if not self.session_cookies or not self.session_expiry or not self.last_login_time:
                return

            data = {
                "cookies": self.session_cookies,
                "expiry": self.session_expiry.isoformat(),
                "last_login": self.last_login_time.isoformat(),
            }
            with open(COOKIE_FILE, "w") as f:
                json.dump(data, f)

            self.logger.info("💾 تم حفظ الجلسة في الملف من داخل ichancy_api")
        except Exception as e:
            self.logger.error(f"❌ فشل حفظ الجلسة في الملف: {e}")

    # =========================
    # ديكوريتور إعادة المحاولة
    # =========================
    @staticmethod
    def with_retry(func):
        @wraps(func)
        def wrapper(self: "IChancyAPI", *args, **kwargs):
            try:
                # ضمان تسجيل الدخول قبل أي نداء API (لكن ليس أثناء Boot)
                self.ensure_login()

                resp = func(self, *args, **kwargs)

                # إذا رجع HTTP 401/403 من الـ API نفسه، حاول إعادة تسجيل الدخول مرة واحدة فقط
                if isinstance(resp, tuple) and isinstance(resp[0], int):
                    if resp[0] in (401, 403):
                        self.logger.warning("⚠️ جلسة غير صالحة — إعادة تسجيل الدخول مرة أخرى")
                        self._invalidate_session()
                        self.ensure_login()
                        resp = func(self, *args, **kwargs)

                return resp
            except Exception as e:
                self.logger.error(f"❌ خطأ في {func.__name__}: {e}")
                return 500, {"error": str(e)}

        return wrapper

    # =========================
    # تسجيل الدخول
    # =========================
    def login(self) -> Tuple[bool, Dict]:
        self._init_scraper()

        payload = {"username": self.USERNAME, "password": self.PASSWORD}

        try:
            resp = self.scraper.post(
                self.ORIGIN + self.ENDPOINTS["signin"],
                json=payload,
                headers=self._get_headers(),
                timeout=self.REQUEST_TIMEOUT,
            )

            if resp.status_code != 200:
                self.logger.error(f"❌ فشل تسجيل الدخول HTTP {resp.status_code}")
                return False, {"error": f"HTTP {resp.status_code}"}

            if self._check_captcha(resp):
                return False, {"error": "captcha_detected"}

            try:
                data = resp.json()
            except Exception:
                self.logger.error("❌ JSON غير صالح في تسجيل الدخول")
                return False, {"error": "invalid_json"}

            if data.get("result", False):
                self.session_cookies = dict(self.scraper.cookies)
                self.session_expiry = datetime.now() + timedelta(minutes=30)
                self.last_login_time = datetime.now()
                self.is_logged_in = True

                # حفظ الجلسة في الملف (بدون استيراد session_manager)
                self._save_session_to_file()

                self.logger.info("✅ تم تسجيل الدخول بنجاح")
                return True, data

            error_msg = "login_failed"
            if data.get("notification"):
                error_msg = data["notification"][0].get("content", error_msg)
            self.logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
            return False, {"error": error_msg}

        except Exception as e:
            self.logger.error(f"❌ استثناء أثناء تسجيل الدخول: {e}")
            return False, {"error": str(e)}

    def ensure_login(self) -> bool:
        self._init_scraper()

        if self.is_logged_in and self._is_session_valid():
            return True

        success, data = self.login()
        if not success:
            raise Exception(data.get("error", "login_failed"))

        return True

    # =========================
    # إنشاء لاعب عشوائي (اختياري)
    # =========================
    @with_retry
    def create_player(
        self, login: Optional[str] = None, password: Optional[str] = None
    ) -> Tuple[int, Dict, str, str, Optional[str]]:

        self._init_scraper()

        login = login or "u" + "".join(
            random.choice(string.ascii_lowercase + string.digits) for _ in range(7)
        )
        password = password or "".join(
            random.choice(string.ascii_letters + string.digits) for _ in range(10)
        )
        email = f"{login}@example.com"

        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": self.PARENT_ID,
                "login": login,
            }
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["create"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        status_code = resp.status_code
        try:
            data = resp.json()
        except Exception:
            self.logger.error("⚠️ create_player: JSON غير صالح")
            data = {}

        # Retry للحصول على player_id
        player_id = None
        for _ in range(5):
            player_id = self.get_player_id(login)
            if player_id:
                break
            time.sleep(1)

        return status_code, data, login, password, player_id

    # =========================
    # player_id
    # =========================
    @with_retry
    def get_player_id(self, login: str) -> Optional[str]:
        self._init_scraper()

        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        if resp.status_code != 200:
            self.logger.warning(f"⚠️ get_player_id HTTP {resp.status_code} for {login}")

        try:
            data = resp.json()
        except Exception:
            self.logger.error("⚠️ get_player_id: JSON غير صالح")
            return None

        records: List[Dict] = data.get("result", {}).get("records", [])

        # 🔥 هنا كان الخطأ: كنا نستخدم username فقط
        for record in records:
            if record.get("login") == login or record.get("username") == login:
                return record.get("playerId")

        return None

    # =========================
    # إنشاء لاعب ببيانات محددة
    # =========================
    @with_retry
    def create_player_with_credentials(
        self, login: str, password: str
    ) -> Tuple[int, Dict, Optional[str], str]:

        self._init_scraper()

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
                "login": login,
            }
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["create"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        status_code = resp.status_code
        try:
            data = resp.json()
        except Exception:
            self.logger.error(
                "⚠️ create_player_with_credentials: JSON غير صالح"
            )
            data = {}

        # Retry للحصول على player_id
        player_id = None
        for _ in range(5):
            player_id = self.get_player_id(login)
            if player_id:
                break
            time.sleep(1)

        return status_code, data, player_id, email

    # =========================
    # التحقق من الإيميل
    # =========================
    @with_retry
    def check_email_exists(self, email: str) -> bool:
        self._init_scraper()

        payload = {"page": 1, "pageSize": 100, "filter": {"email": email}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except Exception:
            self.logger.error("⚠️ check_email_exists: JSON غير صالح")
            return False

        records: List[Dict] = data.get("result", {}).get("records", [])
        return any(record.get("email") == email for record in records)

    # =========================
    # التحقق من اللاعب
    # =========================
    @with_retry
    def check_player_exists(self, login: str) -> bool:
        self._init_scraper()

        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except Exception:
            self.logger.error("⚠️ check_player_exists: JSON غير صالح")
            return False

        records: List[Dict] = data.get("result", {}).get("records", [])

        # 🔥 هنا أيضًا كان الخطأ: نستخدم login وليس username فقط
        return any(
            (record.get("login") == login) or (record.get("username") == login)
            for record in records
        )

    # =========================
    # إيداع
    # =========================
    @with_retry
    def deposit_to_player(self, player_id: str, amount: float) -> Tuple[int, Dict]:
        self._init_scraper()

        payload = {
            "amount": amount,
            "comment": "Deposit from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5,
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["deposit"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        status_code = resp.status_code
        try:
            data = resp.json()
        except Exception:
            self.logger.error("⚠️ deposit_to_player: JSON غير صالح")
            data = {}

        return status_code, data

    # =========================
    # سحب
    # =========================
    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float) -> Tuple[int, Dict]:
        self._init_scraper()

        payload = {
            "amount": amount,
            "comment": "Withdrawal from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5,
        }

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["withdraw"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        status_code = resp.status_code
        try:
            data = resp.json()
        except Exception:
            self.logger.error("⚠️ withdraw_from_player: JSON غير صالح")
            data = {}

        return status_code, data

    # =========================
    # رصيد اللاعب
    # =========================
    @with_retry
    def get_player_balance(self, player_id: str) -> Tuple[int, Dict, float]:
        self._init_scraper()

        payload = {"playerId": str(player_id)}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["balance"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        status_code = resp.status_code
        try:
            data = resp.json()
        except Exception:
            self.logger.error("⚠️ get_player_balance: JSON غير صالح")
            return status_code, {}, 0.0

        results = data.get("result", [])
        balance = 0.0

        if isinstance(results, list) and results:
            try:
                balance = float(results[0].get("balance", 0))
            except Exception:
                balance = 0.0

        return status_code, data, balance

    # =========================
    # جميع اللاعبين
    # =========================
    @with_retry
    def get_all_players(self) -> list:
        self._init_scraper()

        payload = {"page": 1, "pageSize": 100, "filter": {}}

        resp = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["statistics"],
            json=payload,
            headers=self._get_headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        try:
            data = resp.json()
        except Exception:
            self.logger.error("⚠️ get_all_players: JSON غير صالح")
            return []

        return data.get("result", {}).get("records", [])
