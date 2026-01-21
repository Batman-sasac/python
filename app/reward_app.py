from fastapi import APIRouter, Cookie
from database import get_db
from datetime import date
from typing import Optional


app = APIRouter(tags=["Reward"])

# 출석체크 리워드 제공 로직
async def check_attendance_and_reward(user_email: str):
    if not user_email: return False, 0
    
    conn = get_db()
    cur = conn.cursor()
    today = date.today()

    try:
        # 1. 중복 확인
        cur.execute("SELECT id FROM reward_history WHERE user_email = %s AND reason = '출석체크' AND DATE(created_at) = %s", (user_email, today))
        
        if cur.fetchone():
            # 이미 받은 경우, 현재 포인트만 조회해서 반환
            cur.execute("SELECT points FROM users WHERE email = %s", (user_email,))
            current_pt = cur.fetchone()[0]
            return False, current_pt

        # 2. 리워드 지급 및 포인트 합산
        cur.execute("INSERT INTO reward_history (user_email, reward_amount, reason) VALUES (%s, 10, '출석체크')", (user_email,))
        

        cur.execute("UPDATE users SET points = points + 1 WHERE email = %s", (user_email,))
        
        # 3. 업데이트 된 최종 포인트 조회
        cur.execute("SELECT points FROM users WHERE email = %s", (user_email,))
        new_total_points = cur.fetchone()[0]

        conn.commit()
        print(f"🎊 [리워드 지급] {user_email}: 10P 완료 (총: {new_total_points}P)")
        return True, new_total_points # 성공 여부와 포인트를 함께 반환

    except Exception as e:
        conn.rollback()
        print(f"❌ 오류: {e}")
        return False, 0
    finally:
        cur.close()
        conn.close()

# 복습 완료 시 리워드 제공
@app.post("/reward/review-study")
async def review_study_reward(user_email: Optional[str] = Cookie(None)):
    
    quiz_id = data.get("quiz_id")
    all_user_answers = data.get("user_answers")
    
    conn = get_db()
    cur = conn.cursor()

    try:

        # DB에 정답 리스트 가져오기 
        cur.execute("SELECT answers FRON ocr_data WHERE id = %s", (quiz_id,))

        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail= "퀴즈를 찾을 수 없습니다.")
        correct answers = row['answers']

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


        cur.execute("UPDATE users SET points = points + %s WHERE email = %s ", (total_reward, user_email))

        cur.execute("SELECT points FROM users WHERE email = %s", (user_email,))

        new_total_points = cur.fetchone()[0]

        conn.commit()

        
        print(f"{user_email}님은 복습을 완료하여 {total_reward}  적립 후 총{new_total_points}입니다")
    except Exception as e:
        conn.rollback()
        print(f"오류:{e}")
    finally:
        cur.close()
        conn.close()
