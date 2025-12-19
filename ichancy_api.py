import os
import random
import string
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

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": self.ORIGIN,
            "Referer": self.ORIGIN + "/dashboard"
        }

    def _new_session(self):
        return IChancySession(self._headers())

    def _login(self, session: IChancySession):
        payload = {"username": self.USERNAME, "password": self.PASSWORD}
        r = session.scraper.post(self.ORIGIN + self.ENDPOINTS['signin'], json=payload, headers=session.headers, timeout=15)
        data = r.json()
        if not data.get("result"):
            raise Exception("Login failed")
        session.login_time = datetime.now()

    def _ensure_login(self, session):
        if not session.is_valid():
            self._login(session)

    # ======================
    # إنشاء حساب
    # ======================
    def create_player_with_credentials(self, login: str, password: str):
        session = self._new_session()
        try:
            self._ensure_login(session)
            email = f"{login}@agent.nsp"

            payload = {
                "player": {
                    "email": email,
                    "password": password,
                    "parentId": self.PARENT_ID,
                    "login": login
                }
            }

            r = session.scraper.post(
                self.ORIGIN + self.ENDPOINTS['create'],
                json=payload,
                headers=session.headers,
                timeout=20
            )

            data = r.json()
            if r.status_code == 200:
                send_admin_log(
                    "✅ Create Player",
                    f"👤 {login}\n📧 {email}"
                )
            else:
                send_admin_log(
                    "❌ Create Player Failed",
                    str(data)
                )

            return r.status_code, data

        except Exception as e:
            send_admin_log("❌ API Error", f"create_player\n{str(e)}")
            return 500, {"error": str(e)}

    # ======================
    # إيداع
    # ======================
    def deposit_to_player(self, player_id: str, amount: float):
        session = self._new_session()
        try:
            self._ensure_login(session)
            payload = {
                "playerId": player_id,
                "amount": amount,
                "currency": "NSP",
                "currencyCode": "NSP",
                "moneyStatus": 5
            }
            r = session.scraper.post(
                self.ORIGIN + self.ENDPOINTS['deposit'],
                json=payload,
                headers=session.headers,
                timeout=15
            )
            send_admin_log(
                "💰 Deposit",
                f"Player: {player_id}\nAmount: {amount}"
            )
            return r.status_code, r.json()
        except Exception as e:
            send_admin_log("❌ Deposit Error", str(e))
            return 500, {"error": str(e)}

