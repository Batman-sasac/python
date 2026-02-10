from fastapi import APIRouter, HTTPException, Depends, Form
from core.database import supabase
import json

from app.security_app import get_current_user
    

app = APIRouter(tags=["Study"])

@app.get("/study/hint/{quiz_id}")
async def get_quiz_hint( quiz_id: int,
    email: str = Depends(get_current_user)
    ):
   

    try:
        # DB: answers (jsonb) 컬럼에 정답 배열 저장됨
        res = supabase.table("ocr_data") \
            .select("answers") \
            .eq("id", quiz_id) \
            .eq("user_email", email) \
            .single() \
            .execute()

        correct_answers = res.data.get("answers") or []

        if not correct_answers:
            return {"status": "success", "quiz_id": quiz_id, "data": []}

        # 3. 힌트 데이터 가공 (파이썬 리스트 순회)
        hint_list = []
        for ans in correct_answers:
            ans = str(ans).strip()
            
            if not ans:
                hint_list.append({"h1": "", "h2": "", "h3": ""})
                continue

            hint_list.append({
                "h1": get_chosung(ans), # 초성 (기존 함수 활용)
                "h2": ans[0] if len(ans) > 0 else "",   # 첫 글자
                "h3": ans[-1] if len(ans) > 0 else ""   # 마지막 글자
            })

        return {
            "status": "success",
            "quiz_id": quiz_id,
            "data": hint_list
        }

    except Exception as e:
        print(f"❌ 힌트 생성 중 에러: {e}")
        # 데이터가 없는 경우 single()에서 에러가 발생할 수 있으므로 404 처리
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없거나 접근 권한이 없습니다.")