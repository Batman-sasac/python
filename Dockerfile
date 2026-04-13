FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# --access-logfile /dev/null: 요청마다 한 줄씩 쌓이는 액세스 로그 비활성화(용량 폭증 방지). 필요 시 리버스 프록시 로그 사용.
# --log-level: gunicorn 마스터 로그 레벨
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8000", "--log-level", "warning", "--access-logfile", "/dev/null"]
