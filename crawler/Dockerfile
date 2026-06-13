FROM python:3.9-slim

# 避免 tzdata 互動
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 安裝系統工具與必要套件
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git build-essential unzip \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libpangocairo-1.0-0 libxshmfence1 libxrender1 libfontconfig1 \
    libxkbcommon0 libxfixes3 \
 && rm -rf /var/lib/apt/lists/*

# 升級 pip、setuptools、wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 安裝 Playwright 與瀏覽器
RUN pip install --no-cache-dir playwright \
    && playwright install chromium

# 建立工作目錄
WORKDIR /app

# 安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . .

# 暴露服務端口
EXPOSE 6000