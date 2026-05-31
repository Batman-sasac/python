# ocr 및 빈칸/원본 저장
#
# DB(ocr_data) 실제 컬럼: ocr_text, answers, user_answers, quiz_html (모두 jsonb)
# - ocr_text (jsonb): { "pages": [...], "blanks": [...], "quiz": {} }
# - answers (jsonb): 정답 배열 [ "단어1", "단어2", ... ]
# - user_answers (jsonb): 사용자 작성 답변 [ "답1", "답2", ... ]
# - quiz_html (jsonb): 퀴즈 메타 { "raw": "..." }

import io
import json
import asyncio
import time
import logging
from fastapi import APIRouter, UploadFile, File, Form, Body, Depends, Query
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, List, Optional, Any, Union
import os
from PIL import Image
from core.database import supabase

from service.clova_ocr_service import CLOVAOCRService, build_blank_candidates_from_layout
from .ocr_ws import OcrWsManager


from service.ocr_usage_service import (
    OCR_PAGE_LIMIT,
    estimate_page_count,
    get_effective_ocr_page_limit,
    get_user_ocr_usage,
    add_ocr_usage,
    check_can_use,
)


from app.security_app import get_current_user
from service.keyword_adapter import extract_keywords_from_text

logger = logging.getLogger(__name__)

app = APIRouter(tags=["OCR"])

# OCR 무료 사용량 제한을 적용하지 않을 유저 이메일 화이트리스트
OCR_UNLIMITED_EMAILS = {
    "himang0623@kakao.com",
    "wkd4fkqg8k@privaterelay.appleid.com",
    "kdabin111@hanmail.net",
    "hong612644@kakao.com",
}

def _normalize_email(value: Optional[str]) -> str:
    return (value or "").strip().lower()

# GPT 서비스 초기화
API_KEY = os.getenv("OPENAI_API_KEY")
clova_service = CLOVAOCRService(API_KEY)

# OCR 진행률 WebSocket (job_id 기반)
ocr_ws = OcrWsManager()


class _OcrJobState(BaseModel):
    status: str  # queued|running|done|error
    created_at: float
    updated_at: float
    filename: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# 인메모리 OCR job 저장소 (MVP용)
# - Render 재시작/스케일아웃 시 유실될 수 있음(근본 해결은 Redis/DB)
_OCR_JOBS: Dict[str, _OcrJobState] = {}

# 동시 OCR 실행 제한 (기본 1). 필요하면 환경변수로 조절.
_OCR_CONCURRENCY = int(os.getenv("OCR_CONCURRENCY", "1"))
_OCR_SEM = asyncio.Semaphore(max(1, _OCR_CONCURRENCY))


async def _push_job_event(job_id: str, payload: Dict[str, Any]):
    try:
        await ocr_ws.send_json(job_id, payload)
    except Exception:
        # WS 전송 실패는 OCR 자체 실패로 취급하지 않는다.
        return


@app.get("/ocr/job/{job_id}")
async def get_ocr_job(job_id: str, email: str = Depends(get_current_user)):
    """
    비동기 OCR(job_id) 상태/결과 조회.
    - MVP: 인메모리 저장. 서버 재시작 시 유실 가능.
    """
    _ = email  # 인증만 통과시키기(결과는 job_id를 아는 클라이언트만 조회 가능)
    st = _OCR_JOBS.get(job_id)
    if not st:
        return {"status": "not_found"}
    # result는 클 수 있으니 done일 때만 포함
    if st.status == "done":
        return {"status": "done", "data": st.result}
    if st.status == "error":
        return {"status": "error", "message": st.error}
    return {"status": st.status, "filename": st.filename}


@app.websocket("/ws/ocr/{job_id}")
async def ocr_progress_ws(ws: WebSocket, job_id: str):
    """
    OCR 진행률을 받기 위한 WebSocket 엔드포인트.

    ## 프론트 사용 플로우
    1) 프론트에서 job_id 생성 (UUID 등)
    2) 먼저 WS 연결:
       - ws(s)://<API_BASE>/ws/ocr/{job_id}
    3) 그 다음 HTTP 업로드:
       - POST /ocr (multipart/form-data)
       - file + (선택) crop_x/crop_y/crop_width/crop_height + (선택) job_id
    4) OCR 처리 중 서버가 페이지 완료 이벤트를 WS로 push

    주의:
    - 이 WS 핸들러는 "서버→클라이언트 push"가 목적이라, 클라이언트 메시지 내용은 사용하지 않는다.
    - 연결 유지/종료 감지를 위해 receive를 돌린다.
    """
    await ocr_ws.connect(job_id, ws)
    try:
        # keep-alive / close 감지용 (클라이언트에서 ping 텍스트를 보내도 되고, 그냥 연결만 유지해도 됨)
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ocr_ws.disconnect(job_id)
    except Exception:
        ocr_ws.disconnect(job_id)


class OcrTableBlock(BaseModel):
    rows: List[List[str]]


class LayoutBlock(BaseModel):
    """OCR 필드 박스(페이지 대비 정규화 좌표). 읽기 순서와 동일."""
    text: str
    x: float
    y: float
    width: float
    height: float


class BlankCandidate(BaseModel):
    """빈칸(학습) 후보: layout_blocks와 동일 박스 기준. keywords(핵심어)와 별개."""
    id: str
    text: str
    page_index: int
    x: float
    y: float
    width: float
    height: float


class PageItem(BaseModel):
    original_text: str
    keywords: List[str] = []
    tables: Optional[List[OcrTableBlock]] = None
    layout_blocks: Optional[List[LayoutBlock]] = None
    blank_candidates: Optional[List[BlankCandidate]] = None
    keyword_positions: Optional[List[Dict[str, Any]]] = None


class BlankItem(BaseModel):
    blank_index: int
    word: str
    page_index: int = 0


# JSON 요청 모델: 페이지·빈칸·사용자 답변 모두 JSON으로
class QuizSaveRequest(BaseModel):
    subject_name: str
    study_name: Optional[str] = None
    # 페이지별 데이터 (필수 시 pages, 단일 페이지 시 original+answers 호환)
    pages: Optional[List[PageItem]] = None
    original: Optional[str] = None
    answers: Optional[List[str]] = None
    # 빈칸 정의 (blank_index 순서 = user_answers 인덱스)
    blanks: Optional[List[BlankItem]] = None
    # 사용자 작성 답변 (빈칸 순서대로)
    user_answers: Optional[List[str]] = None
    quiz: Optional[Union[Dict[str, str], str]] = None


# OCR 없이 키워드 추출만 테스트용
class KeywordExtractRequest(BaseModel):
    text: str
    top_k_korean: Optional[int] = None
    top_k_english: Optional[int] = None


@app.post("/ocr/keywords")
async def extract_keywords_endpoint(
    payload: KeywordExtractRequest,
    email: str = Depends(get_current_user),
):
    _ = email  # 인증만 통과시키기
    try:
        # 테스트용: top_k 미지정 또는 0 이하 → 전체 키워드 반환
        top_k_korean = 0 if payload.top_k_korean is None else int(payload.top_k_korean)
        top_k_english = 0 if payload.top_k_english is None else int(payload.top_k_english)
        kw = extract_keywords_from_text(
            payload.text or "",
            top_k_korean=top_k_korean,
            top_k_english=top_k_english,
        )
        return {"status": "success", "keywords": kw, "count": len(kw)}
    except Exception as e:
        logger.exception("[OCR] keywords_endpoint_exception pid=%s err=%s", os.getpid(), e)
        return {"status": "error", "message": str(e)}


# OCR 사용량 조회 API (50회 도달 시 한도 메시지 반환)
@app.get("/ocr/usage")
async def get_ocr_usage(email: str = Depends(get_current_user)):
    """
    회원의 OCR 사용량 조회.
    pages_used >= 50 이면 "이용가능한 무료 횟수를 다 사용하셨습니다" 반환.
    """
    email_norm = _normalize_email(email)
    used = get_user_ocr_usage(email_norm)
    effective_limit = get_effective_ocr_page_limit(email_norm)
    # 프론트 계약: pages_limit 은 항상 OCR_PAGE_LIMIT(50)
    remaining = max(0, OCR_PAGE_LIMIT - used)

    # 화이트리스트 유저는 한도 메시지 없이 항상 사용 가능
    if email_norm in OCR_UNLIMITED_EMAILS:
        return {
            "status": "ok",
            "pages_used": used,
            "pages_limit": OCR_PAGE_LIMIT,
            "remaining": remaining,
            "is_unlimited": True,
        }

    if used >= effective_limit:
        return {
            "status": "limit_reached",
            "message": "이용가능한 무료 횟수를 다 사용하셨습니다",
            "pages_used": used, # 사용량
            "pages_limit": OCR_PAGE_LIMIT,
            "remaining": 0, # 남은 횟수
        }
    print(f"✅ OCR 사용량 조회: {used}")
    return {
        "status": "ok",
        "pages_used": used,
        "pages_limit": OCR_PAGE_LIMIT,
        "remaining": remaining,
    }


# 예상 소요 시간 반환
@app.post("/ocr/estimate")
async def get_estimate(file: UploadFile = File(...)):
    # 가볍게 파일 정보만 읽어서 시간 계산
    file_bytes = await file.read()
    filename = file.filename or "image.jpg"
    page_count = estimate_page_count(file_bytes, filename)
    result_msg = f"약 {page_count}페이지 분량" if page_count else "1페이지 미만"
    return {"estimated_time": result_msg}

def _crop_image_to_region(file_bytes: bytes, filename: str, px: int, py: int, pw: int, ph: int) -> bytes:
    """원본 이미지에서 (px, py) 크기 (pw, ph) 영역만 잘라 bytes로 반환. 좌표는 원본 픽셀 기준."""
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    w, h = img.size
    # 경계 클램프
    x1 = max(0, min(px, w - 1))
    y1 = max(0, min(py, h - 1))
    x2 = max(x1 + 1, min(px + pw, w))
    y2 = max(y1 + 1, min(py + ph, h))
    cropped = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    ext = (filename or "").split(".")[-1].lower()
    if ext == "png":
        cropped.save(buf, format="PNG")
    else:
        cropped.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


# 1. OCR 텍스트 추출 엔드포인트 (crop: 프론트에서 전달 시 잘린 영역만 OCR)
@app.post("/ocr")
async def run_ocr_endpoint(
    file: UploadFile = File(...),
    email: str = Depends(get_current_user),
    crop_x: Optional[str] = Form(None),
    crop_y: Optional[str] = Form(None),
    crop_width: Optional[str] = Form(None),
    crop_height: Optional[str] = Form(None),
    job_id: Optional[str] = Form(None),
    async_mode: Optional[str] = Form(None),
):
    try:
        file_bytes = await file.read()
        filename = file.filename or "image.jpg"
        email_norm = _normalize_email(email)

        # 수신한 crop 값 로그 (디버깅)
        print(f"[OCR] 수신 crop_x={crop_x!r}, crop_y={crop_y!r}, crop_width={crop_width!r}, crop_height={crop_height!r}")

        # 이미지 좌표( crop )가 오면 그 영역만 잘라서 OCR — 전체 이미지 사용 안 함
        if all(v is not None and str(v).strip() != "" for v in (crop_x, crop_y, crop_width, crop_height)):
            try:
                px, py, pw, ph = int(float(crop_x)), int(float(crop_y)), int(float(crop_width)), int(float(crop_height))
                if pw > 0 and ph > 0:
                    print(f"✅ OCR crop 수신: px={px}, py={py}, pw={pw}, ph={ph} → 좌표 영역만 OCR")
                    file_bytes = _crop_image_to_region(file_bytes, filename, px, py, pw, ph)
                    # 잘린 이미지 포맷에 맞춰 파일명 변경 (Clova 포맷 인식용)
                    ext = (filename or "").split(".")[-1].lower()
                    filename = f"cropped.{'png' if ext == 'png' else 'jpg'}"
                    print(f"✅ crop 적용 완료, 좌표 영역만 추출 대상. 크기: {len(file_bytes)} bytes")
                else:
                    print(f"⚠️ OCR crop 무시 (pw 또는 ph 0): pw={pw}, ph={ph}")
            except (ValueError, TypeError) as e:
                print(f"⚠️ OCR crop 파싱 실패: {e}")

        # 사용량 한도 체크 (OCR 호출 전)
        estimated = estimate_page_count(file_bytes, filename)

        async_raw = str(async_mode or "").strip().lower()
        force_sync = async_raw in ("0", "false", "no", "n")
        # 기본 정책: job_id가 와도 비동기로 전환하지 않는다.
        # - 프론트가 결과를 HTTP 응답으로 받는 흐름을 깨지 않기 위함
        # - 비동기는 async_mode=1(true/yes/y)로 명시했을 때만 활성화
        want_async = (not force_sync) and (async_raw in ("1", "true", "yes", "y"))
        logger.info(
            "[OCR] request_begin pid=%s mode=%s job_id=%s file=%r bytes=%s est_pages=%s",
            os.getpid(),
            "async" if want_async else "sync",
            job_id or "-",
            filename,
            len(file_bytes),
            estimated,
        )

        # 화이트리스트 유저는 사용량 제한 체크를 건너뛰고, 사용량 기록만 유지
        if email_norm not in OCR_UNLIMITED_EMAILS:
            can_use, used = check_can_use(email_norm, estimated)
            if not can_use:
                return {
                    "status": "limit_reached",
                    "message": "이용가능한 무료 횟수를 다 사용하셨습니다",
                    "pages_used": used,
                    "pages_limit": OCR_PAGE_LIMIT,
                }

        # 소켓 진행률 알림 콜백 (job_id가 있을 때만)
        #
        # - clova_ocr_service.py는 PDF의 images[]를 페이지로 보며 순회 처리한다.
        # - 각 페이지 처리 완료 시 progress_cb를 호출하도록 확장해두었고,
        #   여기서는 그 콜백에서 WebSocket push를 발생시킨다.
        #
        # 구현 디테일:
        # - clova_ocr_service는 동기 함수이며, OCR은 asyncio.to_thread로 워커 스레드에서 돈다.
        # - progress_cb는 그 스레드에서 호출되므로 WS 전송은 run_coroutine_threadsafe로 루프에 넣는다.
        # - job_id가 없으면(프론트가 WS를 안 쓰면) 콜백은 noop.
        loop = asyncio.get_running_loop()

        # 진행률 WS push는 기본 비활성화 (필요 시 환경변수로 켜기)
        progress_enabled = str(os.getenv("OCR_PROGRESS_WS", "0")).strip().lower() in (
            "1",
            "true",
            "yes",
            "y",
        )
        _progress_cb = None
        if progress_enabled and job_id:
            def _progress_cb(page_idx: int, total_pages: int, ok: bool):
                payload = {
                    "type": "ocr_progress",
                    "status": "page_done" if ok else "page_error",
                    "page": page_idx + 1,  # 1-based
                    "total_pages": total_pages,
                    "filename": filename,
                }
                try:
                    asyncio.run_coroutine_threadsafe(
                        ocr_ws.send_json(job_id, payload), loop
                    )
                except Exception:
                    return

        # (대안) 긴 OCR은 HTTP를 빨리 끝내고, job_id로 결과를 받도록 비동기 모드 제공
        if want_async:
            if not job_id:
                return {
                    "status": "error",
                    "message": "async_mode 사용 시 job_id가 필요합니다.",
                }

            now = time.time()
            _OCR_JOBS[job_id] = _OcrJobState(
                status="queued",
                created_at=now,
                updated_at=now,
                filename=filename,
            )
            loop.create_task(
                _push_job_event(
                    job_id,
                    {
                        "type": "ocr_progress",
                        "status": "queued",
                        "filename": filename,
                    },
                )
            )

            async def _run_job():
                job_t0 = time.time()
                async with _OCR_SEM:
                    st = _OCR_JOBS.get(job_id)
                    if st:
                        st.status = "running"
                        st.updated_at = time.time()
                        _OCR_JOBS[job_id] = st
                    logger.info(
                        "[OCR] async_job_running job_id=%s pid=%s file=%r bytes=%s",
                        job_id,
                        os.getpid(),
                        filename,
                        len(file_bytes),
                    )
                    await _push_job_event(
                        job_id,
                        {
                            "type": "ocr_progress",
                            "status": "started",
                            "filename": filename,
                        },
                    )
                    try:
                        # 동기 OCR을 스레드로 돌려 event loop block을 줄임
                        result = await asyncio.to_thread(
                            clova_service.process_file,
                            file_bytes,
                            filename,
                            _progress_cb,
                        )
                        if not isinstance(result, dict) or result.get("status") == "error":
                            msg = (result or {}).get("message") if isinstance(result, dict) else "OCR 실패"
                            raise RuntimeError(msg or "OCR 실패")

                        # 사용량 DB 저장
                        page_count = result.get("page_count", 1)
                        add_ocr_usage(email_norm, page_count)

                        st = _OCR_JOBS.get(job_id)
                        if st:
                            st.status = "done"
                            st.updated_at = time.time()
                            st.result = result
                            _OCR_JOBS[job_id] = st
                        elapsed = time.time() - job_t0
                        logger.info(
                            "[OCR] async_job_done job_id=%s pid=%s pages=%s elapsed_s=%.2f total_duration=%s",
                            job_id,
                            os.getpid(),
                            page_count,
                            elapsed,
                            (result or {}).get("total_duration"),
                        )
                        await _push_job_event(
                            job_id,
                            {
                                "type": "ocr_progress",
                                "status": "done",
                                "filename": filename,
                                "page_count": page_count,
                                # GET /ocr/job/{job_id} 의 data 와 동일 (프론트가 WS만으로 결과 표시 가능)
                                "data": result,
                            },
                        )
                    except Exception as e:
                        elapsed = time.time() - job_t0
                        logger.exception(
                            "[OCR] async_job_failed job_id=%s pid=%s elapsed_s=%.2f err=%s",
                            job_id,
                            os.getpid(),
                            elapsed,
                            e,
                        )
                        st = _OCR_JOBS.get(job_id)
                        if st:
                            st.status = "error"
                            st.updated_at = time.time()
                            st.error = str(e)
                            _OCR_JOBS[job_id] = st
                        await _push_job_event(
                            job_id,
                            {
                                "type": "ocr_progress",
                                "status": "error",
                                "filename": filename,
                                "message": str(e),
                            },
                        )

            loop.create_task(_run_job())
            return {
                "status": "accepted",
                "job_id": job_id,
                "is_unlimited": (email_norm in OCR_UNLIMITED_EMAILS),
            }

        # 기본: HTTP는 OCR이 끝날 때까지 열려 있지만, CPU/동기 OCR은 스레드에서 실행해
        # 이벤트 루프와 다른 API 요청이 같은 워커에서 멈추지 않게 한다.
        sync_t0 = time.time()
        result = await asyncio.to_thread(
            clova_service.process_file,
            file_bytes,
            filename,
            _progress_cb,
        )
        sync_elapsed = time.time() - sync_t0
        logger.info(
            "[OCR] sync_done pid=%s file=%r bytes=%s elapsed_s=%.2f status=%s total_duration=%s",
            os.getpid(),
            filename,
            len(file_bytes),
            sync_elapsed,
            result.get("status") if isinstance(result, dict) else type(result).__name__,
            (result or {}).get("total_duration") if isinstance(result, dict) else None,
        )

        if result["status"] == "error":
            return result

        # 반환 직전: original_text / keywords가 제대로 내려가는지 확인용 요약 로그
        # - 로그 폭주 방지: 페이지는 최대 10개만, 텍스트는 앞 200자만 기록
        try:
            pages = (result or {}).get("pages") if isinstance(result, dict) else None
            pages = pages if isinstance(pages, list) else []
            logger.info(
                "[OCR] return_preview file=%r page_count=%s pages_len=%s",
                filename,
                (result or {}).get("page_count") if isinstance(result, dict) else None,
                len(pages),
            )
            for i, p in enumerate(pages[:10]):
                if not isinstance(p, dict):
                    continue
                text = (p.get("original_text") or "")
                kw = p.get("keywords") or []
                kw = kw if isinstance(kw, list) else []
                logger.info(
                    "[OCR] return_page page=%s text_len=%s keywords_n=%s keywords_top=%s",
                    i + 1,
                    len(text),
                    len(kw),
                    kw[:20],
                )
                logger.info("[OCR] return_text_head page=%s head=%r", i + 1, text[:200])
        except Exception as e:
            logger.exception("[OCR] return_preview_failed file=%r err=%s", filename, e)

        # 사용량 DB 저장
        page_count = result.get("page_count", 1)
        add_ocr_usage(email_norm, page_count)

        return {"status": "success", "data": result, "is_unlimited": (email_norm in OCR_UNLIMITED_EMAILS)}

    except Exception as e:
        logger.exception("[OCR] endpoint_exception pid=%s err=%s", os.getpid(), e)
        return {"status": "error", "message": str(e)}





# 복습 시 퀴즈 데이터 JSON으로 가져오기 (앱에서 ScaffoldingPayload 형태로 사용)
@app.get("/ocr/quiz/{quiz_id}")
async def get_quiz_for_review(quiz_id: int, email: str = Depends(get_current_user)):
    try:
        res = (
            supabase.table("ocr_data")
            .select("id, subject_name, study_name, ocr_text, user_answers, image_url")
            .eq("id", quiz_id)
            .eq("user_email", email)
            .single()
            .execute()
        )
        if not res.data:
            return {"status": "error", "message": "데이터를 찾을 수 없습니다."}

        row = res.data
        ocr_val = row.get("ocr_text") or {}
        pages = ocr_val.get("pages", [])
        blanks = ocr_val.get("blanks", [])
        quiz_val = ocr_val.get("quiz") or {}
        raw_text = quiz_val.get("raw", "") if isinstance(quiz_val, dict) else str(quiz_val)

        # 원문: pages[0].original_text 또는 quiz.raw, 여러 페이지면 \n\n으로 이어붙임
        if pages:
            extracted_text = "\n\n".join(p.get("original_text", "") for p in pages)
        else:
            extracted_text = raw_text

        # 빈칸 목록: blanks 있으면 사용, 없으면 pages[].keywords로 생성
        if blanks:
            blanks_list = [{"id": b.get("blank_index", i), "word": b.get("word", ""), "meaningLong": ""} for i, b in enumerate(blanks)]
        else:
            kw_list = []
            for p in pages:
                kw_list.extend(p.get("keywords") or [])
            blanks_list = [{"id": i, "word": w, "meaningLong": ""} for i, w in enumerate(kw_list)]

        user_answers = row.get("user_answers") or []
        layout_meta = ocr_val.get("layout_meta") or {}

        # 예전 저장본에는 blank_candidates가 없을 수 있음 → layout_blocks로 보강
        enriched_pages = []
        for pi, p in enumerate(pages or []):
            if not isinstance(p, dict):
                enriched_pages.append(p)
                continue
            pc = dict(p)
            if not pc.get("blank_candidates") and pc.get("layout_blocks"):
                pc["blank_candidates"] = build_blank_candidates_from_layout(
                    pc.get("layout_blocks"), pi
                )
            enriched_pages.append(pc)

        return {
            "status": "success",
            "data": {
                "quiz_id": row.get("id"),
                "title": row.get("study_name") or row.get("subject_name") or "학습 자료",
                "extractedText": extracted_text,
                "blanks": blanks_list,
                "user_answers": user_answers,
                "image_url": row.get("image_url"),
                # layout_blocks·tables·blank_candidates 포함해 복습 시 동일 좌표 UI 복원
                "pages": enriched_pages,
                "layout_meta": layout_meta,
            },
        }
    except Exception as e:
        print(f"퀴즈 조회 에러: {e}")
        return {"status": "error", "message": str(e)}


# 해당 학습 삭제 로직 /ocr/ocr-data/delete/{학습파일 번호}
@app.delete("/ocr/ocr-data/delete/{quiz_id}")
async def delete_ocr_data(quiz_id: int, email: str = Depends(get_current_user)):
    print(f"삭제 요청 유저: {email}")

    try:
        res = (
            supabase.table("ocr_data")
            .select("image_url")
            .eq("id", quiz_id)
            .eq("user_email", email)
            .execute()
        )

        if not res.data:
            return {"status": "error", "message": "데이터를 찾지 못했습니다"}

        file_path = res.data[0].get("image_url")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # 2. 데이터 삭제
        (
            supabase.table("ocr_data")
            .delete()
            .eq("id", quiz_id)
            .eq("user_email", email)
            .execute()
        )
        
        return {"status": "success", "message": "삭제 성공했습니다."}

    # try 블록 안에서 에러가 발생하면 이쪽으로 넘어옵니다.
    except Exception as e:
        print(f"Error occurred: {e}") # 로그를 위해 추가하는 것을 추천합니다.
        return {"status": "error", "message": str(e)}


# 학습 목록 /ocr/list
@app.get("/ocr/list")
async def get_ocr_list(
    email: str = Depends(get_current_user),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    print(f"학습 목록 요청 유저: {email}")


    try:
        start = (page - 1) * size
        end = start + size - 1
        response = (
            supabase.table("ocr_data")
            .select("id, study_name, subject_name, ocr_text, created_at")
            .eq("user_email", email)
            .order("created_at", desc=True)
            .range(start, end)
            .execute()
        )

        formatted_data = []
        for item in (response.data or []):
            ocr_val = item.get("ocr_text") or {}
            pages = ocr_val.get("pages", [])
            first_text = pages[0].get("original_text", "") if pages else ""
            ocr_str = (first_text[:50] + "...") if len(first_text) > 50 else first_text
            formatted_data.append({
                "id": item["id"],
                "study_name": item.get("study_name", ""),
                "subject_name": item.get("subject_name", ""),
                "ocr_preview": ocr_str,
                "created_at": item.get("created_at"),
            })

        return {
            "data": formatted_data,
            "page": page,
            "size": size,
            "has_more": len(formatted_data) == size,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}



        
