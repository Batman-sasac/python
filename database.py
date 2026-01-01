import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_db():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS")
        )
        return conn
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        return None