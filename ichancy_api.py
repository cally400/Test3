import requests
import random
import string
import os
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional
import json
from functools import wraps
from cookie_manager import load_cookies_into_session


class IChancyAPI:
    def __init__(self):
        self._setup_logging()
        self._load_config()

        # جلسة Requests بدل cloudscraper
        self.session = requests.Session()

        # تحميل الكوكيز التي يجددها Playwright
        if load_cookies_into_session(self.session):
            self.logger.info("تم تحميل الكوكيز — الجلسة جاهزة")
        else:
            self.logger.error("فشل تحميل الكوكيز — تأكد من وجود ichancy_cookies.json")

        # إضافة الهيدرات
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Origin": self.ORIGIN,
            "Referer": self.REFERER
        })

    # -----------------------------
    # الإعدادات
    # -----------------------------
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        self.USERNAME = os.getenv("AGENT_USERNAME")
        self.PASSWORD = os.getenv("AGENT_PASSWORD")
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
            "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.5249.126 Mobile Safari/537.36"
        )
        self.REFERER = self.ORIGIN + "/dashboard"

    # -----------------------------
    # أدوات مساعدة
    # -----------------------------
    def _post(self, endpoint, payload):
        url = self.ORIGIN + endpoint
        try:
            resp = self.session.post(url, json=payload, timeout=30)

            if resp.status_code == 403:
                self.logger.error("403 Forbidden — الكوكيز منتهية")
                return 403, {"error": "forbidden"}

            if resp.status_code == 401:
                self.logger.error("401 Unauthorized — الجلسة غير صالحة")
                return 401, {"error": "unauthorized"}

            try:
                return resp.status_code, resp.json()
            except:
                return resp.status_code, {}
        except Exception as e:
            self.logger.error(f"POST Error: {e}")
            return 500, {"error": str(e)}

    # -----------------------------
    # decorator ذكي
    # -----------------------------
    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)

            # لو الدالة رجعت tuple فيها status
            if isinstance(result, tuple) and len(result) >= 2:
                status = result[0]
                if status in (401, 403):
                    self.logger.warning("الجلسة منتهية — انتظر التجديد التلقائي")
                    return result

            # لو رجعت bool أو أي شيء آخر → رجّعه كما هو
            return result

        return wrapper

    # -----------------------------
    # إنشاء لاعب جديد
    # -----------------------------
    @with_retry
    def create_player(self, login=None, password=None):
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

        status, data = self._post(self.ENDPOINTS['create'], payload)
        player_id = self.get_player_id(login)

        return status, data, login, password, player_id

    # -----------------------------
    # الحصول على playerId
    # -----------------------------
    @with_retry
    def get_player_id(self, login: str) -> Optional[str]:
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"login": login}
        }

        status, data = self._post(self.ENDPOINTS['statistics'], payload)

        try:
            records = data.get("result", {}).get("records", [])
            for record in records:
                if record.get("username") == login:
                    return record.get("playerId")
        except:
            pass

        return None

    # -----------------------------
    # إنشاء لاعب ببيانات محددة
    # -----------------------------
    @with_retry
    def create_player_with_credentials(self, login: str, password: str):
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

        status, data = self._post(self.ENDPOINTS['create'], payload)
        player_id = self.get_player_id(login)

        return status, data, player_id, email

    # -----------------------------
    # التحقق من وجود إيميل
    # -----------------------------
    @with_retry
    def check_email_exists(self, email: str) -> bool:
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"email": email}
        }

        status, data = self._post(self.ENDPOINTS['statistics'], payload)

        try:
            records = data.get("result", {}).get("records", [])
            return any(record.get("email") == email for record in records)
        except:
            return False

    # -----------------------------
    # التحقق من وجود لاعب
    # -----------------------------
    @with_retry
    def check_player_exists(self, login: str) -> bool:
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {"login": login}
        }

        status, data = self._post(self.ENDPOINTS['statistics'], payload)

        try:
            records = data.get("result", {}).get("records", [])
            return any(record.get("username") == login for record in records)
        except:
            return False

    # -----------------------------
    # إيداع
    # -----------------------------
    @with_retry
    def deposit_to_player(self, player_id: str, amount: float):
        payload = {
            "amount": amount,
            "comment": "Deposit from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }

        return self._post(self.ENDPOINTS['deposit'], payload)

    # -----------------------------
    # سحب
    # -----------------------------
    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float):
        payload = {
            "amount": amount,
            "comment": "Withdrawal from API",
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }

        return self._post(self.ENDPOINTS['withdraw'], payload)

    # -----------------------------
    # رصيد اللاعب
    # -----------------------------
    @with_retry
    def get_player_balance(self, player_id: str):
        payload = {"playerId": str(player_id)}

        status, data = self._post(self.ENDPOINTS['balance'], payload)

        try:
            results = data.get("result", [])
            balance = results[0].get("balance", 0) if results else 0
            return status, data, balance
        except:
            return status, data, 0

    # -----------------------------
    # جميع اللاعبين
    # -----------------------------
    @with_retry
    def get_all_players(self):
        payload = {
            "page": 1,
            "pageSize": 100,
            "filter": {}
        }

        status, data = self._post(self.ENDPOINTS['statistics'], payload)

        try:
            return data.get("result", {}).get("records", [])
        except:
            return []
