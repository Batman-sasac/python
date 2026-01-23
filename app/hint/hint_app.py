from fastapi import APIRouter. Request, HTTPException
from database import get_db
import json

@app.get("/study/hint/{quiz_id}")
async def get_quiz_hint(request: Request, quiz_id:int):
    user_email = request.state.user_email

    conn = get_db()
    cur = conn.cursor()

    try:
        # 1. DB 해당 퀴즈 정답 가져오기 answers
        cur.execute("SELECT answers FROM ocr_data WHERE id = %s AND user_email = %s", (quiz_id,user_email))
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")

        # JSONB 저장 방식일 때의 로직
        correct_answers = row[0] if isinstance(row[0], list) 
        else json.load(row[0])

        # 정답 리스트를 순회하며 힌트 데이터 가공
        h1_hints =[]
        for ans in correct_answers:
            ans = str(ans).strip()
            if not ans:
                hint_list.append({"h1": "", "h2": "", "h3": ""})
                continue

            hint_list.append({
                "h1": get_chosung(ans), # 초성
                "h2": ans[0],           # 첫 글자
                "h3": ans[-1]           # 마지막 글자
            })



        
        return {
            "status": "seccess",
            "quiz_id": quiz_id,
            "data": hint_list
        }

    finally:
        cur.close()
        conn,close()
