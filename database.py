import psycopg2
import os
from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(url, key)

def get_db():
    """Supabase를 통한 DB 연결 반환"""
    return supabase

print("--- DB 연결 테스트 시작 ---")
try:
    # 'ocr_data'라는 이름의 테이블이 실제로 있는지 확인하세요!
    # 만약 테이블 이름이 다르다면 그 이름으로 바꿔주어야 합니다.
    response = supabase.table("users").select("*").limit(1).execute()
    
    print("✅ 연결 성공! Supabase에서 데이터를 가져왔습니다.")
    print(f"조회 결과: {response.data}")

    if response.data:
        print(f"성공! 데이터: {response.data}")
    else:
        print("연결은 됐으나 데이터가 비어있습니다. (RLS나 테이블명 확인 필요)")

except Exception as e:
    print("❌ 연결 실패!")
    print(f"오류 원인: {e}")
    print(f"확인된 URL: {url}") # URL이 None으로 나오는지 확인용