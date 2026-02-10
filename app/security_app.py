import jwt
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import HTTPException, Depends, Header
from typing import Optional

# .env는 프로젝트 루트 기준으로 로드 (app/security_app.py -> 한 단계 위가 루트)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ✅ 1. 설정값 통일 (변수명을 JWT_SECRET_KEY로 통일)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY or not JWT_SECRET_KEY.strip():
    raise RuntimeError(
        "JWT_SECRET_KEY가 .env에 설정되지 않았습니다. "
        "bat_python/.env 파일에 JWT_SECRET_KEY=... 를 추가하세요."
    )
ALGORITHM = "HS256"

print(f"현재 사용중인 키: {JWT_SECRET_KEY[:5]}...")

# ✅ 2. 토큰 생성 함수 (기존 코드 유지 또는 참고)
def create_jwt_token(email: str, social_id: str):
    payload = {
        "email": email,
        "social_id": social_id,
        "exp": datetime.utcnow() + timedelta(days=30)  # 1일 동안 유효
    }
    print(f"DEBUG: 현재 발행용 SECRET_KEY(앞5자리): {JWT_SECRET_KEY[:5]}")
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)

# ✅ 3. 핵심: 토큰 검증 및 사용자 추출 함수
async def get_current_user(authorization: Optional[str] = Header(None)):
    print(f"--- [인증 프로세스 시작] ---")# ✅ 검증 로직 안에 추가
    print(f"DEBUG: 현재 검증용 SECRET_KEY(앞5자리): {JWT_SECRET_KEY[:5]}")

    
    # 1. 헤더 존재 여부 확인
    if not authorization:
        print("❌ 에러: Authorization 헤더가 아예 없습니다.")
        raise HTTPException(status_code=401, detail="인증 헤더가 누락되었습니다.")

    print(f"수신된 헤더: {authorization[:15]}...")

    # 2. Bearer 형식 확인
    if not authorization or not authorization.startswith("Bearer "):
        print(f"❌ 형식 에러 발생 시점의 값: '{authorization}'") # 따옴표로 감싸서 공백 확인
        raise HTTPException(status_code=401, detail="'Bearer ' 형식이 아닙니다.")
    # 3. 토큰 추출 및 해독
    try:
        # token = authorization.split(" ")[1]
        token = authorization.split(" ")[1].strip().replace('"', '').replace("'", "")
        # ✅ JWT_SECRET_KEY를 사용하여 해독 (이름 주의!)
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        
        email = payload.get("email")
        if not email:
            print("❌ 에러: 토큰 내부에 email 필드가 없습니다.")
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰 페이로드입니다.")

        print(f"✅ 인증 성공! 사용자: {email}")
        return email

    except jwt.ExpiredSignatureError:
        print("❌ 에러: 토큰 유효기간 만료")
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError as e:
        # ✅ 콘솔에 구체적인 이유 출력 (Signature verification failed 등)
        print(f"❌ JWT 검증 실패 상세 원인: {str(e)}")
        raise HTTPException(status_code=401, detail=f"유효하지 않은 토큰입니다. 이유: {str(e)}")
    except Exception as e:
        print(f"❌ 알 수 없는 인증 에러: {str(e)}")
        raise HTTPException(status_code=500, detail="서버 인증 처리 중 오류가 발생했습니다.")