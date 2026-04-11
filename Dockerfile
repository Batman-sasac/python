FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV JWT_SECRET_KEY=${JWT_SECRET_KEY}
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENV SUPABASE_URL=${SUPABASE_URL}
ENV SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}
ENV SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}
ENV SUPABASE_JWT_SECRET_KEY=${SUPABASE_JWT_SECRET_KEY}
ENV SUPABASE_JWT_ALGORITHM=${SUPABASE_JWT_ALGORITHM}
ENV SUPABASE_JWT_EXPIRATION_TIME=${SUPABASE_JWT_EXPIRATION_TIME}

# --access-logfile /dev/null: 요청마다 한 줄씩 쌓이는 액세스 로그 비활성화(용량 폭증 방지). 필요 시 리버스 프록시 로그 사용.
# --log-level: gunicorn 마스터 로그 레벨
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8000", "--log-level", "warning", "--access-logfile", "/dev/null"]
