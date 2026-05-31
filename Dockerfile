FROM python:3.11-slim

# 1. 시스템 패키지 설치 (OpenCV 및 PDF 처리에 필요한 라이브러리)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    libpq-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 파이썬 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir wheel
RUN pip install --no-cache-dir -r requirements.txt

# 4. 소스 코드 전체 복사
COPY . .

# 5. 랜덤 이벤트 리워드 (docker-compose .env 또는 -e 로 덮어쓸 수 있음)
ENV RANDOM_EVENT_ENABLED=1
ENV RANDOM_EVENT_PROB=0.15
ENV RANDOM_EVENT_SEED=default

# 6. 실행 명령어 (Gunicorn 환경)
# main:app -> main.py 파일 안에 있는 app 객체를 실행하라는 뜻
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "main:app", "--timeout", "120"]