import cloudscraper
from datetime import datetime, timedelta

class IChancySession:
    def __init__(self, headers: dict):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows'}
        )
        self.headers = headers
        self.login_time = None

    def is_valid(self):
        if not self.login_time:
            return False
        return datetime.now() - self.login_time < timedelta(minutes=25)
