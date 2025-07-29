FROM python:3.11-slim

# 시스템 의존성 설치 (ML 패키지들을 위해)
RUN apt-get update && apt-get install -y \
    iputils-ping \
    dnsutils \
    curl \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pip 업그레이드
RUN pip install --no-cache-dir --upgrade pip

# requirements 복사 및 설치 (캐시 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

ENV LANGFUSE_DISABLE_TELEMETRY=true

# 포트 노출
EXPOSE 8000

# 애플리케이션 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]