from fastapi import APIRouter, Depends, Form
from core.database import supabase
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Tuple, Optional
import os
import hashlib

from app.security_app import get_current_user


app = APIRouter(tags=["Reward"])

REASON_ATTENDANCE = "출석체크"
REWARD_AMOUNT = 10
REASON_RANDOM_EVENT = "랜덤이벤트(10P)"
RANDOM_EVENT_REWARD_AMOUNT = 10

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


def _kst_day_range_iso() -> tuple[str, str]:
    """KST 기준 '오늘 00:00:00' ~ '내일 00:00:00' ISO 범위 문자열."""
    tz = ZoneInfo("Asia/Seoul")
    today = datetime.now(tz).date()
    start = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=tz).isoformat()
    next_day = today.toordinal() + 1
    tomorrow = date.fromordinal(next_day)
    end = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=tz).isoformat()
    return start, end


def _is_random_event_day_kst() -> bool:
    """
    '날짜 랜덤' 10P 이벤트: KST 날짜 단위로, 서버 재시작과 무관하게 동일하게 판정되도록
    (YYYY-MM-DD + seed) 해시를 사용해 확률적으로 이벤트 day를 결정한다.

    환경 변수:
      - RANDOM_EVENT_ENABLED: 1/true/yes면 활성화
      - RANDOM_EVENT_PROB: 0~1 (기본 0.15) — 하루가 이벤트 day일 확률
      - RANDOM_EVENT_SEED: 해시 시드(기본 'default') — 운영에서 고정값 권장
    """
    enabled = os.getenv("RANDOM_EVENT_ENABLED", "").lower() in ("1", "true", "yes")
    if not enabled:
        return False

    try:
        prob = float(os.getenv("RANDOM_EVENT_PROB", "0.15"))
    except Exception:
        prob = 0.15
    prob = max(0.0, min(prob, 1.0))
    if prob <= 0:
        return False
    if prob >= 1:
        return True

    tz = ZoneInfo("Asia/Seoul")
    day = datetime.now(tz).date().isoformat()
    seed = os.getenv("RANDOM_EVENT_SEED", "default")
    digest = hashlib.sha256(f"{day}|{seed}".encode("utf-8")).hexdigest()
    # 0..9999 정수로 매핑 후 prob와 비교 (정밀도 1/10000)
    n = int(digest[:8], 16) % 10000
    threshold = int(prob * 10000)
    return n < threshold


def _grant_random_event_reward_if_eligible(email: str) -> tuple[bool, bool, int]:
    """
    오늘(KST)이 이벤트 day이고, 당일에 아직 이벤트 리워드를 받지 않았으면 10P 지급.

    Returns:
      (today_is_event_day, granted_now, total_points_after)
    """
    today_is_event = _is_random_event_day_kst()
    if not today_is_event:
        user_res = supabase.table("users").select("points").eq("email", email).single().execute()
        current_pt = user_res.data.get("points", 0) if user_res.data else 0
        return False, False, current_pt

    start, end = _kst_day_range_iso()
    check_res = (
        supabase.table("reward_history")
        .select("id")
        .eq("user_email", email)
        .eq("reason", REASON_RANDOM_EVENT)
        .gte("created_at", start)
        .lt("created_at", end)
        .execute()
    )
    if check_res.data and len(check_res.data) > 0:
        user_res = supabase.table("users").select("points").eq("email", email).single().execute()
        current_pt = user_res.data.get("points", 0) if user_res.data else 0
        return True, False, current_pt

    now = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    supabase.table("reward_history").insert(
        {
            "user_email": email,
            "reward_amount": RANDOM_EVENT_REWARD_AMOUNT,
            "reason": REASON_RANDOM_EVENT,
            "created_at": now,
        }
    ).execute()
    user_res = supabase.table("users").select("points").eq("email", email).single().execute()
    current_points = user_res.data.get("points", 0) if user_res.data else 0
    new_total = int(current_points) + RANDOM_EVENT_REWARD_AMOUNT
    supabase.table("users").update({"points": new_total}).eq("email", email).execute()
    print(f"🎁 [랜덤이벤트] {email}: {RANDOM_EVENT_REWARD_AMOUNT}P 지급 (총: {new_total}P)")
    return True, True, new_total


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


# --- 랜덤 날짜 이벤트 리워드(10P): 오늘이 이벤트 day이면 1회 지급 ---
@app.post("/reward/random-event")
async def random_event_reward(email: str = Depends(get_current_user)):
    """
    '날짜 랜덤' 이벤트 10P 지급.
    - RANDOM_EVENT_ENABLED=1 인 경우에만 활성화
    - 오늘(KST)이 이벤트 day로 판정되면 당일 1회 10P 지급 (reward_history reason 기준 중복 방지)

    Response:
      - today_is_event_day: bool
      - is_new_reward: bool
      - reward_amount: int (0 또는 10)
      - total_points: int
    """
    try:
        today_is_event_day, granted, total_points = _grant_random_event_reward_if_eligible(email)
        return {
            "status": "success",
            "today_is_event_day": today_is_event_day,
            "is_new_reward": granted,
            "reward_amount": RANDOM_EVENT_REWARD_AMOUNT if granted else 0,
            "total_points": total_points,
            "message": (
                "이벤트 보상이 지급되었습니다."
                if granted
                else ("오늘은 이벤트 날이 아닙니다." if not today_is_event_day else "오늘 이미 이벤트 보상을 받았습니다.")
            ),
        }
    except Exception as e:
        print(f"❌ 랜덤 이벤트 리워드 오류: {e}")
        return {"status": "error", "message": str(e)}


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