# 학습 카테고리 API — ocr_data.subject_name 컬럼 사용 (별도 테이블 없음)

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.security_app import get_current_user
from core.database import supabase

logger = logging.getLogger(__name__)

app = APIRouter(prefix="/categories", tags=["Categories"])


class CategoryUpdateRequest(BaseModel):
    quiz_id: int = Field(..., description="ocr_data.id (학습 ID)")
    subject_name: str = Field(..., min_length=1, max_length=50, description="카테고리(과목) 이름")


class CategoryRenameRequest(BaseModel):
    old_name: str = Field(..., min_length=1, max_length=50)
    new_name: str = Field(..., min_length=1, max_length=50)


@app.post("")
async def set_category(
    data: CategoryUpdateRequest,
    email: str = Depends(get_current_user),
):
    """학습(ocr_data)의 subject_name(카테고리) 설정·변경."""
    subject_name = data.subject_name.strip()
    if not subject_name:
        raise HTTPException(status_code=400, detail="카테고리 이름을 입력해주세요.")

    existing = (
        supabase.table("ocr_data")
        .select("id")
        .eq("id", data.quiz_id)
        .eq("user_email", email)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="학습 데이터를 찾을 수 없습니다.")

    try:
        res = (
            supabase.table("ocr_data")
            .update({"subject_name": subject_name})
            .eq("id", data.quiz_id)
            .eq("user_email", email)
            .execute()
        )
    except Exception:
        logger.exception(
            "[category] update_failed email=%s quiz_id=%s", email, data.quiz_id
        )
        raise HTTPException(status_code=500, detail="카테고리 변경에 실패했습니다.")

    row = res.data[0] if res.data else {"id": data.quiz_id, "subject_name": subject_name}
    return {
        "status": "success",
        "message": "카테고리가 변경되었습니다.",
        "data": {
            "quiz_id": row.get("id", data.quiz_id),
            "subject_name": row.get("subject_name", subject_name),
        },
    }


@app.patch("/rename")
async def rename_category(
    data: CategoryRenameRequest,
    email: str = Depends(get_current_user),
):
    """같은 subject_name을 가진 학습들을 일괄 이름 변경."""
    old_name = data.old_name.strip()
    new_name = data.new_name.strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="카테고리 이름을 입력해주세요.")
    if old_name == new_name:
        raise HTTPException(status_code=400, detail="변경 전·후 이름이 같습니다.")

    try:
        res = (
            supabase.table("ocr_data")
            .update({"subject_name": new_name})
            .eq("user_email", email)
            .eq("subject_name", old_name)
            .execute()
        )
    except Exception:
        logger.exception("[category] rename_failed email=%s", email)
        raise HTTPException(status_code=500, detail="카테고리 이름 변경에 실패했습니다.")

    updated = res.data or []
    return {
        "status": "success",
        "message": "카테고리 이름이 변경되었습니다.",
        "updated_count": len(updated),
    }


@app.get("")
async def list_categories(email: str = Depends(get_current_user)):
    """내 ocr_data에서 사용 중인 subject_name(카테고리) 목록."""
    try:
        res = (
            supabase.table("ocr_data")
            .select("subject_name")
            .eq("user_email", email)
            .execute()
        )
    except Exception:
        logger.exception("[category] list_failed email=%s", email)
        raise HTTPException(status_code=500, detail="카테고리 목록 조회에 실패했습니다.")

    counts: dict[str, int] = {}
    for row in res.data or []:
        name = (row.get("subject_name") or "학습 자료").strip() or "학습 자료"
        counts[name] = counts.get(name, 0) + 1

    categories = [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda x: x[0])
    ]

    return {
        "status": "success",
        "data": categories,
    }
