FROM python:3.9-slim

# 避免 tzdata 互動
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential \
    libglib2.0-0 libgl1 libsm6 libxrender1 libxext6 unzip \
 && rm -rf /var/lib/apt/lists/*

# 提升打包工具版本
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 建立工作目錄
WORKDIR /app

# 先安裝依賴（快取友好）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . .

# 預設指令（可依需要調整）
EXPOSE 5000