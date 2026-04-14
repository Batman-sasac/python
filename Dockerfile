FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 앱 로그([OCR] 등)는 Python logging → 기본 INFO. 디버깅 시 Render에서 LOG_LEVEL=DEBUG
ENV LOG_LEVEL=INFO

# --access-logfile /dev/null: 요청마다 한 줄씩 쌓이는 액세스 로그 비활성화(용량 폭증 방지). 필요 시 리버스 프록시 로그 사용.
# --log-level: gunicorn 마스터 로그 레벨 (info면 워커 기동/종료 등이 보여 WORKER TIMEOUT과 대조하기 쉬움)
# OCR 처리가 30초를 넘길 수 있어 gunicorn 기본 타임아웃(30s)으로는 502(업스트림 종료) 위험이 큽니다.
# --timeout: worker가 응답 없이 버틸 수 있는 최대 시간(초)
# --graceful-timeout: 종료 시 유예 시간(초)
# --keep-alive: keep-alive 커넥션 유지(초)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8000", "--log-level", "info", "--access-logfile", "/dev/null", "--timeout", "300", "--graceful-timeout", "30", "--keep-alive", "5"]
