"""
연속 학습일 보너스 등 리워드 보조 로직.
study_logs.completed_at 날짜(KST 기준 YYYY-MM-DD)로 연속일을 계산한다.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.database import supabase

REASON_STREAK = "연속학습"
STREAK_MIN_DAYS = 2
STREAK_REWARD_AMOUNT = 10


def compute_consecutive_study_days(email: str) -> int:
    """오늘(KST)부터 역으로 이어지는 연속 학습일 수 (study_logs.completed_at 기준)."""
    tz = ZoneInfo("Asia/Seoul")
    today = datetime.now(tz).date()
    logs_res = (
        supabase.table("study_logs")
        .select("completed_at")
        .eq("user_email", email)
        .execute()
    )
    study_dates: set[str] = set()
    for row in logs_res.data or []:
        completed = row.get("completed_at")
        if not completed:
            continue
        if isinstance(completed, str):
            study_dates.add(completed[:10])
        else:
            study_dates.add(str(completed)[:10])
    consecutive = 0
    check = today
    while check.isoformat() in study_dates:
        consecutive += 1
        check -= timedelta(days=1)
    return consecutive


def _streak_reward_granted_today_kst(email: str) -> bool:
    """당일(KST) 이미 연속학습 보너스를 받았는지."""
    tz = ZoneInfo("Asia/Seoul")
    today = datetime.now(tz).date()
    start = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=tz).isoformat()
    next_day = today + timedelta(days=1)
    end = datetime(next_day.year, next_day.month, next_day.day, 0, 0, 0, tzinfo=tz).isoformat()
    res = (
        supabase.table("reward_history")
        .select("id")
        .eq("user_email", email)
        .eq("reason", REASON_STREAK)
        .gte("created_at", start)
        .lt("created_at", end)
        .execute()
    )
    return bool(res.data)


def grant_streak_reward_if_eligible(email: str) -> tuple[bool, int, int, int | None]:
    """
    study_logs 저장 직후 호출. 연속 학습일 >= STREAK_MIN_DAYS 이고 당일 미지급이면 보너스 지급.

    Returns:
        (지급 여부, 연속일, 이번에 지급한 보너스 포인트, 지급 후 총 포인트)
        미지급 시 보너스는 0, 총 포인트는 None.
    """
    streak = compute_consecutive_study_days(email)
    if streak < STREAK_MIN_DAYS:
        return False, streak, 0, None
    if _streak_reward_granted_today_kst(email):
        return False, streak, 0, None
    try:
        now = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        supabase.table("reward_history").insert(
            {
                "user_email": email,
                "reward_amount": STREAK_REWARD_AMOUNT,
                "reason": REASON_STREAK,
                "created_at": now,
            }
        ).execute()
        user_res = supabase.table("users").select("points").eq("email", email).single().execute()
        current = (user_res.data or {}).get("points") or 0
        new_total = int(current) + STREAK_REWARD_AMOUNT
        supabase.table("users").update({"points": new_total}).eq("email", email).execute()
        return True, streak, STREAK_REWARD_AMOUNT, new_total
    except Exception as e:
        print(f"❌ 연속학습 리워드 처리 오류: {e}")
        return False, streak, 0, None
