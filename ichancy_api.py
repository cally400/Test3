# ichancy_api.py
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
# Redis key (جلسة واحدة فقط)
# =========================
REDIS_SESSION_KEY = "ichancy:global_session"
REDIS_LOCK_KEY = "ichancy:login_lock"


class IChancyAPI:
    """
    🔐 Global Agent Session
    - Session واحدة لكل المستخدمين
    - Redis للتخزين
    - Auto re-login
    """

    def __init__(self):
        self._load_config()

        self.scraper = None
        self.redis = None

        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None

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

    # =========================
    # Redis
    # =========================
    def _init_redis(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError("REDIS_URL غير موجود")

        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.redis.ping()
        logger.info("✅ Redis connected")

    # =========================
    # Scraper
    # =========================
    def _init_scraper(self):
        if self.scraper:
            return

        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard",
        }

    # =========================
    # Session helpers
    # =========================
    def _is_session_valid(self):
        if not self.session_expiry:
            return False
        return datetime.utcnow() < self.session_expiry

    def _load_session_from_redis(self):
        data = self.redis.get(REDIS_SESSION_KEY)
        if not data:
            return

        try:
            session = json.loads(data)
            self.session_cookies = session["cookies"]
            self.session_expiry = datetime.fromisoformat(session["expiry"])
            self.last_login_time = datetime.fromisoformat(session["last_login"])
            self.scraper.cookies.update(self.session_cookies)
            self.is_logged_in = self._is_session_valid()

            if self.is_logged_in:
                logger.info("♻️ Session loaded from Redis")

        except Exception as e:
            logger.error(f"❌ Failed loading session: {e}")

    def _save_session_to_redis(self):
        data = {
            "cookies": self.session_cookies,
            "expiry": self.session_expiry.isoformat(),
            "last_login": self.last_login_time.isoformat(),
        }
        self.redis.set(REDIS_SESSION_KEY, json.dumps(data), ex=3600)
        logger.info("💾 Session saved to Redis")

    def _invalidate_session(self):
        self.is_logged_in = False
        self.session_cookies = {}
        self.session_expiry = None
        self.last_login_time = None
        self.redis.delete(REDIS_SESSION_KEY)
        logger.warning("♻️ Session invalidated")

    # =========================
    # Login (واحد فقط)
    # =========================
    def login(self):
        # Redis lock لمنع Login متزامن
        if not self.redis.set(REDIS_LOCK_KEY, "1", nx=True, ex=60):
            time.sleep(2)
            self._load_session_from_redis()
            if self.is_logged_in:
                return True

        try:
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

            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            if not data.get("result"):
                raise Exception("Login failed")

            self.session_cookies = dict(self.scraper.cookies)
            self.session_expiry = datetime.utcnow() + timedelta(minutes=30)
            self.last_login_time = datetime.utcnow()
            self.is_logged_in = True

            self._save_session_to_redis()
            logger.info("✅ Global login success")
            return True

        finally:
            self.redis.delete(REDIS_LOCK_KEY)

    def ensure_login(self):
        if self.is_logged_in and self._is_session_valid():
            return True

        self._load_session_from_redis()
        if self.is_logged_in:
            return True

        return self.login()

    # =========================
    # Decorator
    # =========================
    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.ensure_login()
            resp = func(self, *args, **kwargs)

            if isinstance(resp, tuple) and resp[0] in (401, 403):
                logger.warning("🔁 Re-login triggered")
                self._invalidate_session()
                self.login()
                resp = func(self, *args, **kwargs)

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

        r = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["create"],
            json=payload,
            headers=self._headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        return r.status_code, r.json()

    @with_retry
    def check_player_exists(self, login):
        """
        تحقق مما إذا كان اسم المستخدم موجود مسبقًا
        """
        payload = {"login": login}
        r = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["check_player"],
            json=payload,
            headers=self._headers(),
            timeout=self.REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code} عند التحقق من اسم المستخدم")

        data = r.json()
        return data.get("result", {}).get("exists", False)

    @with_retry
    def deposit(self, player_id, amount):
        payload = {
            "playerId": player_id,
            "amount": amount,
            "currency": "NSP",
            "moneyStatus": 5,
        }

        r = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["deposit"],
            json=payload,
            headers=self._headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        return r.status_code, r.json()

    @with_retry
    def withdraw(self, player_id, amount):
        payload = {
            "playerId": player_id,
            "amount": amount,
            "currency": "NSP",
            "moneyStatus": 5,
        }

        r = self.scraper.post(
            self.ORIGIN + self.ENDPOINTS["withdraw"],
            json=payload,
            headers=self._headers(),
            timeout=self.REQUEST_TIMEOUT,
        )

        return r.status_code, r.json()

