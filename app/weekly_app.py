# 학습 주기 세팅 및 주마다의 그래프 도출 

from fastapi import APIRouter, Cookie, Body, HTTPException
from typing import Optional
from fastapi.responses import HTMLResponse
import psycopg2
import os
from database import get_db

app = APIRouter(prefix="/weekly", tags=["Weekly"])


# 출석률*정답률에 따른 그래프 도출을 위한 데이터 
@app.get("/stats/weekly-growth")
async def get_weekly_growth(user_email: str = Cookie(None)):
    if not user_email:
        return {"error": "로그인이 필요합니다."}

    conn = get_db()
    cur = conn.cursor()
    
    try:
        # ocr_data를 기준으로 주간 성장 점수 도출
        # (노트 생성일 = 출석일 / 정답률 = 임시로 100% 또는 생성 빈칸 수 비례 설정 가능)
        cur.execute("""
            WITH weekly_stats AS (
                SELECT 
                    DATE_TRUNC('week', created_at)::date as week_start,
                    COUNT(DISTINCT DATE(created_at)) as attend_days,
                    -- 실제 채점 데이터가 없을 경우, 문제를 생성한 성실도를 점수로 환산 (예: 생성 개수 비례)
                    COUNT(id) * 10.0 as activity_score 
                FROM ocr_data
                WHERE user_email = %s
                GROUP BY 1
            )
            SELECT 
                week_start,
                -- (활동 점수 * 출석률(attend_days/7)) 형식으로 점수화
                LEAST((activity_score * (attend_days / 7.0)), 100) as growth_score
            FROM weekly_stats
            ORDER BY week_start DESC
            LIMIT 5;
        """, (user_email,))
        
        rows = cur.fetchall()
        
        # 최신 데이터가 오른쪽으로 가도록 뒤집기
        rows_reversed = list(reversed(rows))
        
        # 그래프용 라벨 및 데이터 생성
        labels = []
        scores = []
        
        for i, row in enumerate(rows_reversed):
            # 주차별 라벨 생성
            diff = len(rows_reversed) - 1 - i
            if diff == 0:
                label = "이번 주"
            elif diff == 1:
                label = "지난 주"
            else:
                label = f"{diff}주 전"
            
            labels.append(label)
            scores.append(round(row[1], 1))

        # 데이터가 5개보다 적을 경우를 대비해 기본값 채우기 (선택사항)
        while len(labels) < 5:
            labels.insert(0, f"{len(labels)+1}주 전")
            scores.insert(0, 0)

        return {
            "labels": labels,
            "data": scores  # 프론트엔드 Chart.js에서 사용하기 쉬운 이름
        }
    except Exception as e:
        print(f"그래프 데이터 도출 오류: {e}")
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()


@app.post("/set-goal")
async def set_study_goal(
    payload: dict = Body(...), 
    user_email: Optional[str] = Cookie(None)
):
    
    target_count = payload.get("target_count")
    if not target_count or int(target_count) < 1:
        return {"status": "error", "message": "올바른 목표 횟수를 입력하세요."}

    conn = get_db()
    cur = conn.cursor()
    try:
        # 기존 목표가 있는지 확인 후 업데이트 또는 삽입 (UPSERT 로직)
        cur.execute("""
            INSERT INTO study_goals (user_email, target_count, is_active)
            VALUES (%s, %s, TRUE)
            ON CONFLICT (user_email) 
            DO UPDATE SET target_count = EXCLUDED.target_count, created_at = CURRENT_TIMESTAMP;
        """, (user_email, int(target_count)))
        
        # 참고: ON CONFLICT를 쓰려면 user_email에 UNIQUE 제약조건이 있어야 합니다.
        # 없다면 DELETE 후 INSERT 하는 방식으로 처리하세요.
        
        conn.commit()
        return {"status": "success", "message": f"주간 목표가 {target_count}회로 설정되었습니다!"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()


@app.get("/setting", response_class=HTMLResponse)
async def index_page(user_email: Optional[str] = Cookie(None)): # 변수명 확인!
    print(f"현재 브라우저에서 넘어온 쿠키 값: {user_email}") # 서버 터미널에 출력됨
    
    with open("templates/weeklyTarget.html", "r", encoding="utf-8") as f:
        return f.read()