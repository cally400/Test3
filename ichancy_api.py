import cloudscraper
import random
import string
import os
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict
from functools import wraps

class IChancySession:
    """جلسة مستقلة لكل عملية/مستخدم"""
    def __init__(self, headers: Dict[str, str]):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.headers = headers
        self.login_time = None
        self.cookies = {}

    def is_valid(self):
        if not self.login_time:
            return False
        return datetime.now() - self.login_time < timedelta(hours=2)


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
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard"
        }

    def _login(self, session: IChancySession):
        payload = {"username": self.USERNAME, "password": self.PASSWORD}
        r = session.scraper.post(self.ORIGIN + self.ENDPOINTS['signin'], json=payload, headers=session.headers, timeout=15)
        data = r.json()
        if not data.get("result"):
            raise Exception("Login failed")
        session.login_time = datetime.now()
        session.cookies = dict(session.scraper.cookies)

    def _ensure_login(self, session: IChancySession):
        if not session.is_valid():
            self._login(session)

    def with_retry(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            session = IChancySession(self._headers())
            try:
                self._ensure_login(session)
                return func(self, session, *args, **kwargs)
            except Exception as e:
                self.logger.error(f"❌ API Error in {func.__name__}: {e}")
                return 500, {"error": str(e)}
        return wrapper

    # ======================
    # وظائف اللاعبين
    # ======================
    @with_retry
    def create_player_with_credentials(self, session: IChancySession, login: str, password: str):
        email = f"{login}@agent.nsp"
        payload = {"player": {"email": email, "password": password, "parentId": self.PARENT_ID, "login": login}}
        r = session.scraper.post(self.ORIGIN + self.ENDPOINTS['create'], json=payload, headers=session.headers, timeout=20)
        data = r.json()
        return r.status_code, data

    @with_retry
    def check_player_exists(self, session: IChancySession, login: str) -> bool:
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}
        r = session.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=session.headers)
        data = r.json()
        records = data.get("result", {}).get("records", [])
        return any(record.get("username") == login for record in records)

    @with_retry
    def deposit_to_player(self, session: IChancySession, player_id: str, amount: float):
        payload = {"playerId": player_id, "amount": amount, "currency": "NSP", "currencyCode": "NSP", "moneyStatus": 5}
        r = session.scraper.post(self.ORIGIN + self.ENDPOINTS['deposit'], json=payload, headers=session.headers)
        return r.status_code, r.json()

    @with_retry
    def withdraw_from_player(self, session: IChancySession, player_id: str, amount: float):
        payload = {"playerId": player_id, "amount": amount, "currency": "NSP", "currencyCode": "NSP", "moneyStatus": 5}
        r = session.scraper.post(self.ORIGIN + self.ENDPOINTS['withdraw'], json=payload, headers=session.headers)
        return r.status_code, r.json()

    @with_retry
    def get_player_balance(self, session: IChancySession, player_id: str):
        payload = {"playerId": str(player_id)}
        r = session.scraper.post(self.ORIGIN + self.ENDPOINTS['balance'], json=payload, headers=session.headers)
        data = r.json()
        balance = data.get("result", [{}])[0].get("balance", 0)
        return r.status_code, data, balance

    @with_retry
    def get_all_players(self, session: IChancySession):
        payload = {"page": 1, "pageSize": 100, "filter": {}}
        r = session.scraper.post(self.ORIGIN + self.ENDPOINTS['statistics'], json=payload, headers=session.headers)
        data = r.json()
        return data.get("result", {}).get("records", [])

