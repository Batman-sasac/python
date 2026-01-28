from fastapi import APIRouter. Request, HTTPException
from database import get_db
import json

@app.get("/study/hint/{quiz_id}")
async def get_quiz_hint(request: Request, quiz_id:int):
    user_email = request.state.user_email

    마지막 힌트 제공 로직까지 Supabase SDK 버전으로 깔끔하게 변환해 드릴게요.

이 코드의 핵심은 json.loads 과정이 생략된다는 점과, 결과가 없을 때 single()을 사용해 깔끔하게 예외 처리를 하는 것입니다. 또한 get_chosung 함수는 기존에 정의하신 것을 그대로 사용한다고 가정했습니다.

🛠️ Supabase SDK 버전 hint.py
Python

import os
from fastapi import APIRouter, Request, HTTPException
from database import supabase  # database.py에서 설정한 클라이언트
# get_chosung 함수는 기존 위치에서 임포트하거나 정의되어 있어야 합니다.

app = APIRouter(tags=["Study"])

@app.get("/study/hint/{quiz_id}")
async def get_quiz_hint(request: Request, quiz_id: int):
    # 1. 미들웨어에서 추출한 유저 이메일
    user_email = request.state.user_email

    try:
        # 2. DB에서 정답 리스트 가져오기 (SDK 버전)
        # .single()을 쓰면 결과가 없을 때 자동으로 에러를 감지하기 쉬워집니다.
        res = supabase.table("ocr_data") \
            .select("answers") \
            .eq("id", quiz_id) \
            .eq("user_email", user_email) \
            .single() \
            .execute()

        correct_answers = res.data.get("answers", [])

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
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없거나 접근 권한이 없습