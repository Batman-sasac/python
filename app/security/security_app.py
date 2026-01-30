
import jwt
import os
from dotenv import load_dotenv
from fastapi import HTTPException, Form, Depends

load_dotenv()

# .env 파일에 설정된 비밀키를 가져옵니다.
SECRET_KEY = os.getenv("JWT_SECRET_KEY") or "your-very-secret-key"
ALGORITHM = "HS256"

# 해독함수 정의
def decode_jwt_token(token: str):
    """
    프론트엔드에서 보낸 토큰을 해독하여 사용자 정보를 반환합니다.
    """
    try:
        # 1. 토큰의 서명을 확인하고 내용을 해독합니다.
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # 2. 토큰 안에 담긴 정보(주로 email이나 social_id)를 반환합니다.
        return payload 
        
    except jwt.ExpiredSignatureError:
        # 토큰 유효시간이 만료된 경우
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        # 토큰 자체가 가짜이거나 손상된 경우
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    except Exception as e:
        # 기타 에러 처리
        raise HTTPException(status_code=500, detail=f"토큰 해독 중 오류 발생: {str(e)}")

# 문지기 함수 
async def get_current_user(token: str = Form(...)):
    """
    프론트에서 Form으로 보낸 token을 가로채서 검증합니다.
    """
    payload = decode_jwt_token(token)
    email = payload.get("email")
    
    if not email:
        # 신분증이 가짜거나 만료되었으면 여기서 바로 입구컷!
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")
        
    return email # 검증된 이메일을 반환합니다.