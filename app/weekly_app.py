# 학습 주기 세팅 및 주마다의 그래프 도출

from fastapi import APIRouter, Body, Depends, Form
from typing import Optional
from datetime import datetime, date, timedelta
from database import supabase

from app.security_app import get_current_user

app = APIRouter(prefix="/cycle", tags=["Weekly"])


# 1. 학습 목표 설정 (UPDATE)
@app.post("/set-goal")
async def set_study_goal(
    email: str = Depends(get_current_user),
    cycle_count: Optional[int] = Form(None),
    payload: Optional[dict] = Body(None),
):

    print(f"학습 목표 설정 유저:{email}")

    payload_count = payload.get("cycle_count") if payload else None
    resolved_count = cycle_count if cycle_count is not None else payload_count

    if not resolved_count or int(resolved_count) < 1:
        return {"status": "error", "message": "올바른 목표 횟수를 입력하세요."}

    try:
        supabase.table("users") \
            .update({"monthly_goal": int(resolved_count)}) \
            .eq("email", email).execute()

        return {
            "status": "success",
            "target_count": resolved_count,
            "monthly_goal": resolved_count,
            "message": "목표가 성공적으로 저장되었습니다."
        }
    except Exception as e:
        return {"status": "error", "message": f"DB 저장 실패: {str(e)}"}


# 2. 주간 성장 그래프 데이터 (SELECT & 가공)
@app.get("/stats/weekly-growth")
async def get_weekly_growth(
    email: str = Depends(get_current_user)
):

    print(f"주간 성장 데이터 유저:{email}")

    try:
        five_weeks_ago = (date.today() - timedelta(weeks=5)).isoformat()

        res = supabase.table("ocr_data") \
            .select("id, created_at") \
            .eq("user_email", email) \
            .gte("created_at", five_weeks_ago) \
            .execute()

        data = res.data

        weekly_map = {}
        for item in data:
            dt = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
            week_start = (dt.date() - timedelta(days=dt.weekday())).isoformat()

            if week_start not in weekly_map:
                weekly_map[week_start] = {"attend_dates": set(), "count": 0}

            weekly_map[week_start]["attend_dates"].add(dt.date())
            weekly_map[week_start]["count"] += 1

        labels = []
        scores = []
        today_monday = date.today() - timedelta(days=date.today().weekday())

        for i in range(4, -1, -1):
            target_date = (today_monday - timedelta(weeks=i))
            target_iso = target_date.isoformat()

            if i == 0:
                label = "이번 주"
            elif i == 1:
                label = "지난 주"
            else:
                label = f"{i}주 전"

            labels.append(label)

            stats = weekly_map.get(target_iso)
            if stats:
                attend_days = len(stats["attend_dates"])
                activity_score = stats["count"] * 10.0
                growth_score = min((activity_score * (attend_days / 7.0)), 100)
                scores.append(round(growth_score, 1))
            else:
                scores.append(0)

        return {"labels": labels, "data": scores}
    except Exception as e:
        return {"error": str(e)}


# 3. 학습 통계 비교 (이번 달 vs 지난 달)
@app.get("/learning-stats")
async def get_learning_stats(
    email: str = Depends(get_current_user)
):

    today = date.today()
    this_month_start = today.replace(day=1).isoformat()
    last_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat()

    try:
        this_res = supabase.table("study_logs") \
            .select("id", count="exact") \
            .eq("user_email", email) \
            .gte("completed_at", this_month_start).execute()
        this_month_count = this_res.count

        last_res = supabase.table("study_logs") \
            .select("id", count="exact") \
            .eq("user_email", email) \
            .gte("completed_at", last_month_start) \
            .lt("completed_at", this_month_start).execute()
        last_month_count = last_res.count

        user_res = supabase.table("users").select("monthly_goal").eq("email", email).single().execute()
        target_count = user_res.data.get("monthly_goal") if user_res.data else 0

        return {
            "status": "success",
            "compare": {
                "last_month_name": f"{datetime.fromisoformat(last_month_start).month}월",
                "last_month_count": last_month_count,
                "this_month_name": f"{today.month}월",
                "this_month_count": this_month_count,
                "target_count": target_count,
                "diff": this_month_count - last_month_count
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
