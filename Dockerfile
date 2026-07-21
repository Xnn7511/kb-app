FROM python:3.11-slim

# 安装系统依赖（tesseract OCR + 中文语言包）
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-chi-tra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY backend/ ./backend/
COPY frontend/dist/ ./frontend/dist/

# 创建数据目录（不在仓库中，运行时生成）
RUN mkdir -p data/chroma data/config uploads/raw

WORKDIR /app/backend

EXPOSE 8080

# Render 使用 PORT 环境变量
CMD python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
