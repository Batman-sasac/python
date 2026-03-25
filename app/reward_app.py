from fastapi import APIRouter, Depends, Form
from core.database import supabase
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Tuple, Optional

from app.security_app import get_current_user


app = APIRouter(tags=["Reward"])

REASON_ATTENDANCE = "출석체크"
REWARD_AMOUNT = 10

# 연속 학습일 보너스(2일 이상): service.reward_service — study_logs 저장 후 study_app에서 지급


def _auto_attendance_check(email: str) -> Tuple[bool, int]:
    """
    앱 실행 시 자동 출석체크: rewards DB에 당일 출석체크 row가 없으면 리워드 적립.
    - 당일 row 있음 → (False, 현재 포인트)
    - 당일 row 없음 → INSERT 후 users.points 갱신, (True, 갱신된 포인트)
    """
    today = date.today()
    try:
        # 1. 당일 출석체크 row 존재 여부 확인 (rewards 테이블)
        check_res = supabase.table("reward_history") \
            .select("id") \
            .eq("user_email", email) \
            .eq("reason", REASON_ATTENDANCE) \
            .gte("created_at", f"{today}T00:00:00") \
            .lt("created_at", f"{today}T23:59:59") \
            .execute()

        if check_res.data and len(check_res.data) > 0:
            user_res = supabase.table("users").select("points").eq("email", email).single().execute()
            current_pt = user_res.data.get("points", 0) if user_res.data else 0
            return False, current_pt

        # 2. 당일 row 없음 → rewards 테이블에 INSERT (리워드 적립)
        supabase.table("reward_history").insert({
            "user_email": email,
            "reward_amount": REWARD_AMOUNT,
            "reason": REASON_ATTENDANCE,
            "created_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        }).execute()

        # 3. users.points 업데이트
        user_res = supabase.table("users").select("points").eq("email", email).single().execute()
        current_points = user_res.data.get("points", 0) if user_res.data else 0
        new_total = current_points + REWARD_AMOUNT
        supabase.table("users").update({"points": new_total}).eq("email", email).execute()

        print(f"🎊 [자동 출석체크] {email}: rewards 적립 완료 ({REWARD_AMOUNT}P, 총: {new_total}P)")
        return True, new_total

    except Exception as e:
        print(f"❌ 출석체크 리워드 처리 오류: {e}")
        return False, 0


# main.py /index 등에서 호출 시 사용 (Form + Depends)
async def check_attendance_and_reward(
    token: str = Form(...),
    email: str = Depends(get_current_user),
) -> Tuple[bool, int]:
    """출석체크 리워드 (기존 호환용). _auto_attendance_check 위임."""
    return _auto_attendance_check(email)


# --- 앱 실행 시 자동 출석체크 API: 당일 row 없으면 rewards 적립 ---
@app.post("/reward/attendance")
async def auto_attendance_check(email: str = Depends(get_current_user)):
    """
    앱 실행 시 호출. 자동 출석체크 후 당일 출석체크 row가 없으면 rewards DB에 적립.
    - GET/POST 모두 지원 (앱 로드 시 GET으로 호출 가능)
    """
    is_new, points = _auto_attendance_check(email)

    print(f"is_new: {is_new}, points: {points}")
    return {
        "status": "success",
        "is_new_reward": is_new,
        "baseXP": REWARD_AMOUNT if is_new else 0,
        "bonusXP": 0,
        "total_points": points,
        "message": "출석 보상이 지급되었습니다." if is_new else "오늘 이미 출석 보상을 받았습니다.",
    }


# --- 총 리워드 상위 5명 조회 API ---
@app.get("/reward/leaderboard")
async def get_reward_leaderboard():
    """
    users DB에서 총 리워드(points)가 높은 순 상위 5명을 반환.
    반환: [{ total_reward, nickname }, ...]
    """
    try:
        res = supabase.table("users") \
            .select("points, nickname") \
            .order("points", desc=True) \
            .limit(5) \
            .execute()
        items = [
            {"total_reward": row.get("points", 0), "nickname": row.get("nickname") or ""}
            for row in (res.data or [])
        ]
        return {"status": "success", "leaderboard": items}
    except Exception as e:
        print(f"❌ 리더보드 조회 오류: {e}")
        return {"status": "error", "leaderboard": [], "message": str(e)}