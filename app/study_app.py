# 재첨 후 정답 저장 

from fastapi import APIRouter, HTTPException, Cookie, Body, Request
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
import json
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = APIRouter(prefix="/study", tags=["study"])

# 퀴즈 제출 모델
class QuizSubmitRequest(BaseModel):
    quiz_id: int
    user_answers: List[str]
    correct_answers: List[str]

# 채점 로직
@app.post("/grade")
async def grade_quiz(
    payload: dict = Body(...),
    request:Request
):
    user_email = request.state.user_email
    
    # 1. 전달받은 데이터 추출 (이름을 payload로 통일)
    correct_ans = payload.get('answer', [])
    user_ans = payload.get('user_answers', [])
    quiz_id = payload.get('quiz_id')

    if not correct_ans:
        return {"status": "error", "message": "정답 데이터가 없습니다."}
    
    if not user_email:
        return {"status": "error", "message": "로그인이 필요합니다."}

    # 2. 채점 로직
    score = 0
    correct_count = 0
    total_questions = len(correct_ans)
    results = []

    for u, c in zip(user_ans, correct_ans):
        # 공백 제거 후 비교
        is_correct = (str(u).strip() == str(c).strip())
        if is_correct:
            correct_count += 1
        results.append({"user": u, "correct": c, "is_correct": is_correct})

    score = correct_count # 맞춘 개수
    
    # 3. 리워드 계산
    reward = score  # 기본 1점씩
    

    # 4. DB 저장
    conn = get_db()
    cur = conn.cursor()

    try:

        # 1. 데이터 타입 변환 (리스트 -> JSON 문자열)
        user_ans_str = json.dumps(user_ans)
    
        # 올백 여부 계산 (print문에서 쓰기 위해 선언)
        is_all_correct = (correct_count == total_questions)

    # [1] 공통 작업: 사용자의 답변 저장
        cur.execute("""
            UPDATE ocr_data 
            SET user_answers = %s 
            WHERE id = %s AND user_email = %s
        """, (user_ans, quiz_id, user_email))

    # [2] 공통 작업: 학습 로그 저장 (여기에 한 번만 작성)
        cur.execute("""
            INSERT INTO study_logs(quiz_id, user_email) 
            VALUES(%s, %s)
        """, (quiz_id, user_email))

    # [3] 조건부 작업: 리워드가 있을 때만 실행
        if reward > 0:
            cur.execute("""
                INSERT INTO reward_history (user_email, reward_amount, reason) 
                VALUES (%s, %s, %s)
            """, (user_email, reward, f"퀴즈 정답: {correct_count}/{total_questions}"))
        
            cur.execute("""
                UPDATE users 
                SET points = points + %s 
                WHERE email = %s
            """, (reward, user_email))

        # [4] 최종 확정
        conn.commit()

        # 터미널 로그 출력
        print("\n" + "🎯"*10 + " 채점 결과 " + "🎯"*10)
        print(f"사용자: {user_email}")
        print(f"정답률: {correct_count}/{total_questions}")
        print(f"🔹 사용자가 작성한 답변 내용: {user_ans}")
        print(f"최종 리워드: {reward}P {'(올백 보너스!)' if is_all_correct else ''}")
        print(f"✅ 사용자의 답변 저장 완료 (ID: {quiz_id})")


        
        return {
            "status": "success",
            "score": correct_count,
            "total": total_questions,
            "reward_given": reward,
            "is_all_correct": is_all_correct,
            "results": results
        }
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ 리워드 저장 오류: {e}")
        return {"status": "error", "message": f"리워드 저장 실패: {str(e)}"}
    finally:
        cur.close()
        conn.close()


from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

# 복습화면
@app.get("/review_study/{quiz_id}", response_class=HTMLResponse)
async def review_page(request: Request, quiz_id: int):
    
    user_email = request.state.user_email
    
    conn = get_db()
    # 딕셔너리 형태로 데이터 조회
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT id, subject_name, study_name, ocr_text, answers, quiz_html FROM ocr_data WHERE id = %s", (quiz_id,))
        quiz_data = cur.fetchone()
        
        if not quiz_data:
            return HTMLResponse(content="데이터를 찾을 수 없습니다.", status_code=404)

        # [핵심] JSON 데이터를 문자열로 변환하여 템플릿에 전달
        return templates.TemplateResponse("review_study.html", {
            "request": request,
            "quiz": quiz_data, # DB 데이터 통째로 전달
            "quiz_json": json.dumps(quiz_data, ensure_ascii=False) # JS용 JSON 문자열
        })
    finally:
        cur.close()
        conn.close()


# 복습 완료 시 리워드 제공 & 사용자 답변 저장 
@app.post("/review-study")
async def review_study_reward(request : Request):

    user_email = request.state.user_email
    
    data = await request.json()
    quiz_id = data.get("quiz_id")
    all_user_answers = data.get("user_answers")
    
    conn = get_db()
    cur = conn.cursor()

    try:

        # DB에 정답 리스트 가져오기 
        cur.execute("SELECT answers FROM ocr_data WHERE id = %s", (quiz_id,))

        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail= "퀴즈를 찾을 수 없습니다.")
        try:
            correct_answers = row[0]
            print(f"{row}")

            if isinstance(raw_answers, str):
                correct_answers = json.loads(raw_answers)
            else:
                correct_answers = raw_answers
        except TypeError:
            print(f"DEBUG: row data is {row}")
            raise


        # 정답 비교
        score =0
        results =[]

        for user_ans, real_ans in zip(all_user_answers, correct_answers):
            is_correct = str(user_ans).strip() == str(real_ans).strip().lower()

            if is_correct:
                score +=1
            
            results.append({
                "user": user_ans,
                "real": real_ans,
                "is_correct": is_correct
            })

            # 리워드 계산
            total_reward = score * 2

        cur.execute("INSERT INTO reward_history (user_email, reward_amount, reason) VALUES (%s, %s , '복습학습을 통한 정답 리워드')", (user_email, total_reward))

        cur.execute("""
            UPDATE ocr_data 
            SET user_answers = %s 
            WHERE id = %s AND user_email = %s
        """, (user_ans, quiz_id, user_email))

        cur.execute("UPDATE users SET points = points + %s WHERE email = %s ", (total_reward, user_email))

        cur.execute("SELECT points FROM users WHERE email = %s", (user_email,))

        new_total_points = cur.fetchone()[0]

        conn.commit()

        print(f"✅복습 시 사용자가 입력한 답안 {all_user_answers} ")        
        print(f"⭕ {user_email}님은 복습을 완료하여 {total_reward}  적립 후 총{new_total_points}입니다")
    except Exception as e:
        conn.rollback()
        print(f"오류:{e}")
    finally:
        cur.close()
        conn.close()