# Dockerfile - متوافق مع Debian 12
FROM python:3.11-slim-bullseye  # تغيير إلى bullseye

# تثبيت تبعيات النظام
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    libgbm1 \
    libxshmfence1 \
    libxtst6 \
    libxss1 \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# تثبيت ChromeDriver
RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/120.0.6099.109/linux64/chromedriver-linux64.zip \
    && unzip chromedriver-linux64.zip \
    && mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf chromedriver-linux64.zip chromedriver-linux64

WORKDIR /app

COPY requirements.txt .
COPY . .

# تثبيت dependencies بايثون
RUN pip install --no-cache-dir -r requirements.txt

# تعيين متغيرات البيئة
ENV DISPLAY=:99
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV GOOGLE_CHROME_BIN=/usr/bin/google-chrome
ENV PYTHONUNBUFFERED=1

# تشغيل التطبيق
CMD ["python", "main.py"]
