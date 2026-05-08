import requests
import uuid
import time
import json
import re
import os
import statistics
import logging
import io  
from pdf2image import convert_from_bytes 
from pypdf import PdfReader

from service.keyword_adapter import extract_keywords_from_text

# LLM 키워드 추출 복구 시: 아래 import 주석 해제 + CLOVAOCRService.__init__ 및 process_file 내 LLM 블록 주석 해제,
# 동시에 형태소 어댑터 호출 부분을 주석 처리
# from openai import OpenAI

logger = logging.getLogger(__name__)


def _norm_for_match(s: str) -> str:
    """키워드/박스 텍스트 매칭용 정규화: 공백/개행/특수문자를 줄이고 소문자화."""
    if not s:
        return ""
    s2 = re.sub(r"\s+", "", str(s)).lower()
    # 한글/영문/숫자만 남기고 제거 (OCR 잡음/구두점 영향 최소화)
    s2 = re.sub(r"[^0-9a-z가-힣]", "", s2)
    return s2


def build_keyword_positions_from_layout(keywords, layout_blocks, page_index: int):
    """
    키워드(명사) 리스트를 layout_blocks(텍스트+좌표) 중 가장 잘 맞는 박스에 매칭해
    프론트 좌표 하이라이트용 목록을 만든다.

    규칙:
    - 포함 매칭 우선: norm(block.text)에 norm(keyword)가 포함되는 박스를 후보로
    - 후보가 여러 개면 "가장 짧은 박스 텍스트"를 우선 (딱 맞는 박스일 확률↑)
      동률이면 reading order(앞에 나온 박스) 우선
    - 매칭 실패 키워드는 제외 (프론트에서 텍스트 기반 fallback 가능)
    """
    if not keywords or not layout_blocks:
        return []

    # 사전 정규화
    blocks = []
    for idx, b in enumerate(layout_blocks):
        if not isinstance(b, dict):
            continue
        text = (b.get("text") or "").strip()
        if not text:
            continue
        blocks.append(
            {
                "idx": idx,
                "text": text,
                "norm": _norm_for_match(text),
                "x": float(b.get("x", 0)),
                "y": float(b.get("y", 0)),
                "width": float(b.get("width", 0)),
                "height": float(b.get("height", 0)),
            }
        )

    if not blocks:
        return []

    out = []
    seen = set()
    for kw in keywords:
        word = (str(kw) if kw is not None else "").strip()
        if not word:
            continue
        if word in seen:
            continue
        seen.add(word)

        nkw = _norm_for_match(word)
        if not nkw:
            continue

        candidates = [b for b in blocks if nkw and nkw in b["norm"]]
        if not candidates:
            continue

        # 가장 짧은 텍스트(정규화 기준) → 딱 맞는 박스 선호, 동률이면 idx(읽기순) 작은 것
        best = min(candidates, key=lambda b: (len(b["norm"]), b["idx"]))
        out.append(
            {
                "id": f"{page_index}-{best['idx']}-{word}",
                "word": word,
                "page_index": page_index,
                "x": best["x"],
                "y": best["y"],
                "width": best["width"],
                "height": best["height"],
            }
        )
    return out


def _cell_infer_text(cell):
    """Clova General OCR 표 셀: cellTextLines[].cellWords[].inferText"""
    lines = cell.get("cellTextLines") or []
    parts = []
    for line in lines:
        for w in (line.get("cellWords") or []):
            t = (w or {}).get("inferText", "")
            if t:
                parts.append(t)
    return " ".join(parts).strip()


def _clova_tables_to_page_tables(tables_raw):
    """images[].tables → 프론트용 [{ 'rows': [[str, ...], ...] }, ...]"""
    if not tables_raw:
        return []
    out = []
    for tbl in tables_raw:
        cells = tbl.get("cells") or []
        if not cells:
            continue
        by_row = {}
        for cell in cells:
            r = int(cell.get("rowIndex", 0))
            c = int(cell.get("columnIndex", 0))
            text = _cell_infer_text(cell)
            if r not in by_row:
                by_row[r] = []
            by_row[r].append((c, text))
        rows = []
        for r in sorted(by_row.keys()):
            cols = sorted(by_row[r], key=lambda x: x[0])
            rows.append([t for _, t in cols])
        if rows:
            out.append({"rows": rows})
    return out


def _tables_raw_to_plain_text(tables_raw):
    """
    표 영역 텍스트를 한 덩어리 문자열로 합친다.
    original_text / GPT 키워드 입력이 동일한 페이지 문자열을 쓰도록 fields 결과와 합치기 위해 사용한다.
    """
    blocks = _clova_tables_to_page_tables(tables_raw)
    if not blocks:
        return ""
    lines = []
    for tbl in blocks:
        for row in tbl.get("rows") or []:
            line = " ".join((c or "").strip() for c in row if (c or "").strip())
            if line:
                lines.append(line)
    return "\n".join(lines)


def _merge_field_text_and_tables(field_text: str, tables_raw) -> str:
    """필드 기반 본문 + 표 셀 텍스트를 한 페이지의 통합 원문으로 만든다."""
    tbl_plain = _tables_raw_to_plain_text(tables_raw)
    ft = (field_text or "").strip()
    tt = (tbl_plain or "").strip()
    if ft and tt:
        return f"{ft}\n\n{tt}"
    return ft or tt


def _vertices(field):
    return (field.get("boundingPoly") or {}).get("vertices") or []


def _field_x_center(field):
    verts = _vertices(field)
    if not verts:
        return 0.0
    xs = [float(v.get("x", 0)) for v in verts]
    return sum(xs) / len(xs)


def _field_y_center(field):
    verts = _vertices(field)
    if not verts:
        return 0.0
    ys = [float(v.get("y", 0)) for v in verts]
    return sum(ys) / len(ys)


def _field_x_range(field):
    verts = _vertices(field)
    xs = [float(v.get("x", 0)) for v in verts]
    if not xs:
        return (0.0, 0.0)
    return (min(xs), max(xs))


def _infer_page_width(fields, image):
    info = image.get("convertedImageInfo") or {}
    w = info.get("width")
    if w is not None:
        return float(w)
    xs = []
    for f in fields:
        for v in _vertices(f):
            xs.append(float(v.get("x", 0)))
    return max(xs) if xs else 1000.0


def _infer_page_height(fields, image):
    info = image.get("convertedImageInfo") or {}
    h = info.get("height")
    if h is not None:
        return float(h)
    ys = []
    for f in fields:
        for v in _vertices(f):
            ys.append(float(v.get("y", 0)))
    return max(ys) if ys else 1.0


def _field_bbox_norm(field, page_w, page_h):
    """텍스트 박스를 페이지 대비 0~1 정규화 (프론트에서 그대로 배치용)."""
    verts = _vertices(field)
    if not verts:
        return None
    xs = [float(v.get("x", 0)) for v in verts]
    ys = [float(v.get("y", 0)) for v in verts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    pw = max(page_w, 1.0)
    ph = max(page_h, 1.0)
    t = (field.get("inferText") or "").strip()
    if not t:
        return None
    return {
        "text": t,
        "x": x0 / pw,
        "y": y0 / ph,
        "width": (x1 - x0) / pw,
        "height": (y1 - y0) / ph,
    }


def _layout_blocks_reading_order(fields, image):
    """읽기 순서(줄 단위 Y → 줄 안 X)와 동일한 순서로 필드 박스 나열."""
    if not fields:
        return []
    w = _infer_page_width(fields, image)
    h = _infer_page_height(fields, image)
    y_th = max(14.0, _median_field_height(fields) * 0.65)
    lines = _cluster_into_lines(fields, y_th)
    lines.sort(key=_line_mean_y)
    blocks = []
    for line in lines:
        for f in sorted(line, key=lambda x: _field_x_range(x)[0]):
            bb = _field_bbox_norm(f, w, h)
            if bb:
                blocks.append(bb)
    return blocks


def build_blank_candidates_from_layout(layout_blocks, page_index: int):
    """
    빈칸(학습) 후보 목록: `layout_blocks`와 동일한 OCR 필드 박스를 선택 UI용으로 내려준다.
    `keywords`(추출 키워드)와 별개이며, 필드 단위 텍스트·좌표를 그대로 쓴다.
    """
    if not layout_blocks:
        return []
    out = []
    for idx, block in enumerate(layout_blocks):
        if not isinstance(block, dict):
            continue
        text = (block.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "id": f"{page_index}-{idx}",
                "text": text,
                "page_index": page_index,
                "x": float(block.get("x", 0)),
                "y": float(block.get("y", 0)),
                "width": float(block.get("width", 0)),
                "height": float(block.get("height", 0)),
            }
        )
    return out


def _median_field_height(fields):
    hs = []
    for f in fields:
        verts = _vertices(f)
        ys = [float(v.get("y", 0)) for v in verts]
        if len(ys) >= 2:
            hs.append(max(ys) - min(ys))
    return statistics.median(hs) if hs else 14.0


def _cluster_into_lines(fields, y_threshold):
    if not fields:
        return []
    fields = sorted(fields, key=_field_y_center)
    lines = []
    current = [fields[0]]
    anchor_y = _field_y_center(fields[0])
    for f in fields[1:]:
        y = _field_y_center(f)
        if abs(y - anchor_y) > y_threshold:
            lines.append(current)
            current = [f]
            anchor_y = y
        else:
            current.append(f)
    lines.append(current)
    return lines


def _join_line_tokens(line):
    """같은 줄에서 X순; 캡슐/박스로 잘린 단어는 가로 간격이 좁으면 이어 붙임."""
    if not line:
        return ""
    ordered = sorted(line, key=lambda f: _field_x_range(f)[0])
    parts = []
    prev_f = None
    for f in ordered:
        t = (f.get("inferText") or "").strip()
        if not t:
            continue
        if prev_f is None:
            parts.append(t)
            prev_f = f
            continue
        p0, p1 = _field_x_range(prev_f)
        c0, c1 = _field_x_range(f)
        gap = c0 - p1
        pw = max(p1 - p0, 1.0)
        est = max(pw / max(len(parts[-1]), 1), 4.0)
        if gap < est * 1.6:
            parts[-1] += t
        else:
            parts.append(t)
        prev_f = f
    return " ".join(parts)


def _line_mean_y(line):
    if not line:
        return 0.0
    return sum(_field_y_center(f) for f in line) / len(line)


def _should_use_two_columns(fields, width):
    if len(fields) < 8:
        return False
    mid = width * 0.5
    left_n = sum(1 for f in fields if _field_x_center(f) < mid)
    right_n = len(fields) - left_n
    if left_n < 3 or right_n < 3:
        return False
    if left_n / len(fields) > 0.72 or right_n / len(fields) > 0.72:
        return False
    ratio = min(left_n, right_n) / max(left_n, right_n)
    return ratio >= 0.12


def _fields_single_column(fields, y_threshold):
    lines = _cluster_into_lines(fields, y_threshold)
    return "\n".join(_join_line_tokens(line) for line in lines)


def _fields_to_page_text(fields, image):
    """기본: 읽기 순서(줄 단위 Y → 줄 안 X). 표/비표·구석 표 모두 전 페이지 2단으로 가정하지 않음.
    전형적 2단 단어장만 맞추려면 환경변수 OCR_TWO_COLUMN_LAYOUT=1 로 2단 보정을 켤 수 있음."""
    if not fields:
        return ""
    width = _infer_page_width(fields, image)
    y_th = max(14.0, _median_field_height(fields) * 0.65)

    use_two = os.getenv("OCR_TWO_COLUMN_LAYOUT", "").lower() in ("1", "true", "yes")
    if not use_two or not _should_use_two_columns(fields, width):
        return _fields_single_column(fields, y_th)

    mid = width * 0.5
    left = [f for f in fields if _field_x_center(f) < mid]
    right = [f for f in fields if _field_x_center(f) >= mid]
    if not left or not right:
        return _fields_single_column(fields, y_th)

    left_lines = _cluster_into_lines(left, y_th)
    right_lines = _cluster_into_lines(right, y_th)
    left_lines.sort(key=_line_mean_y)
    right_lines.sort(key=_line_mean_y)

    n = max(len(left_lines), len(right_lines))
    out_lines = []
    for i in range(n):
        lt = _join_line_tokens(left_lines[i]) if i < len(left_lines) else ""
        rt = _join_line_tokens(right_lines[i]) if i < len(right_lines) else ""
        if lt and rt:
            out_lines.append(f"{lt}  |  {rt}")
        elif lt:
            out_lines.append(lt)
        else:
            out_lines.append(rt)
    return "\n".join(out_lines)


class CLOVAOCRService:
    def __init__(self, api_key):
        self.api_key = api_key
        # --- OpenAI 클라이언트 (페이지별 LLM 키워드 추출용, 현재 비활성화 — service/keyword_adapter 사용) ---
        # self.gpt_client = OpenAI(api_key=api_key)
        # self.model = "gpt-4o"

        # 네이버 클로바 설정 (환경변수)
        self.clova_url = os.getenv("CLOVA_OCR_URL")
        self.clova_secret = os.getenv("CLOVA_OCR_SECRET")

    
    def get_estimation_message(self, files_data, secret_key):
        """
        [Service]
        - 입력: [{'filename': '...', 'bytes': b'...'}, ...]
        - 로직: PDF(40초/장), 이미지(30초/장) 합산
        """

        print(f"사용 중인 키: {self.clova_secret}")
        total_seconds = 0

        for file in files_data:
            filename = file.get('filename', '')
            file_bytes = file.get('bytes', b'')
            file_ext = filename.split('.')[-1].lower()

            if file_ext == 'pdf':
                try:
                    reader = PdfReader(io.BytesIO(file_bytes), strict=False)
                    pages = len(reader.pages)
                    # PDF: 페이지당 40초
                    total_seconds += (max(pages, 1) * 40)
                except Exception:
                    total_seconds += 40
            else:
                # 이미지(jpg, png 등): 장당 30초
                total_seconds += 30

        minutes = total_seconds // 60
        seconds = total_seconds % 60
        
        if minutes > 0:
            return f"약 {minutes}분 {seconds}초 소요 예정"
        return f"약 {seconds}초 소요 예정"
    
    
    
    def extract_text_with_clova(self, file_bytes, filename, progress_cb=None):
        """네이버 클로바 OCR을 사용하여 페이지별로 텍스트 추출.
        file_bytes: 원본 또는 ocr_app에서 crop된 잘린 이미지 bytes (좌표 적용 후 넘어옴).

        progress_cb:
        - 페이지 단위 진행률을 외부(WebSocket 등)로 전달하기 위한 콜백.
        - 시그니처: progress_cb(page_idx: int, total_pages: int, ok: bool) -> None
          - page_idx: 0-based
          - total_pages: images[] 길이 (PDF면 페이지 수)
          - ok: 해당 페이지 처리 성공 여부 (현재는 fields 비어도 ok=True로 보고 "완료" 이벤트를 발행)
        """
        pages_text = []
        pages_tables = []
        pages_layout = []

        try:
            if not self.clova_url or not self.clova_secret:
                logger.error(
                    "CLOVA OCR 환경변수가 설정되지 않았습니다. CLOVA_OCR_URL=%s, CLOVA_OCR_SECRET=%s",
                    bool(self.clova_url),
                    bool(self.clova_secret),
                )
                return None

            # 파일 확장자 확인
            raw_ext = filename.split('.')[-1].lower() if '.' in filename else 'jpg'
            

                # 2. 클로바가 선호하는 포맷으로 매핑 (jpeg -> jpg)
            if raw_ext in ['jpg', 'jpeg', 'jpe']:
                file_ext = 'jpg'
            elif raw_ext == 'png':
                file_ext = 'png'
            elif raw_ext == 'pdf':
                file_ext = 'pdf'
            elif raw_ext in ['tiff', 'tif']:
                file_ext = 'tiff'
            else:
                file_ext = 'jpg'  # 알 수 없는 경우 기본값 jpg


            # 클로바 OCR 요청 데이터 구성 (lang은 message 최상위, 공식값: ko/ja/zh-TW)
            request_json = {
                'version': 'V2',
                'requestId': str(uuid.uuid4()),
                'timestamp': int(round(time.time() * 1000)),
                'lang': 'ko',
                'images': [{'format': file_ext, 'name': 'ocr_request'}],
                'enableTableDetection': True
            }

            headers = {'X-OCR-SECRET': self.clova_secret}
            payload = {'message': json.dumps(request_json)}
            
            files = [('file', (filename, file_bytes, 'application/octet-stream'))]

            # 다중 페이지 PDF는 처리 시간이 길어지므로 read timeout을 여유 있게 둔다.
            # 기본값 300초, 환경변수 CLOVA_OCR_READ_TIMEOUT 으로 조정 가능.
            read_timeout = int(os.getenv("CLOVA_OCR_READ_TIMEOUT", "300"))
            connect_timeout = int(os.getenv("CLOVA_OCR_CONNECT_TIMEOUT", "10"))
            timeout_cfg = (connect_timeout, read_timeout)
            started_at = time.time()

            req_id = request_json.get("requestId")
            logger.info(
                "[OCR/Clova] http_post_begin request_id=%s pid=%s file=%r bytes=%s timeout_connect=%ss read=%ss",
                req_id,
                os.getpid(),
                filename,
                len(file_bytes),
                connect_timeout,
                read_timeout,
            )

            # 클로바 API 호출
            try:
                response = requests.post(
                    self.clova_url, 
                    headers=headers, 
                    data=payload, 
                    files=files,
                    timeout=timeout_cfg
                )
            except requests.Timeout:
                elapsed = time.time() - started_at
                logger.error(
                    "Clova API 타임아웃. filename=%s, requestId=%s, elapsed=%.2fs, timeout=%s",
                    filename,
                    request_json.get("requestId"),
                    elapsed,
                    timeout_cfg,
                )
                return None
            except requests.RequestException as e:
                elapsed = time.time() - started_at
                logger.exception(
                    "Clova API 요청 실패. filename=%s, requestId=%s, elapsed=%.2fs, error=%s",
                    filename,
                    request_json.get("requestId"),
                    elapsed,
                    e,
                )
                return None
            
            if response.status_code == 200:
                http_ms = (time.time() - started_at) * 1000.0
                try:
                    result = response.json()
                except Exception:
                    logger.error(
                        "CLOVA OCR 응답 JSON 파싱 실패. status=%s, body=%s",
                        response.status_code,
                        (response.text or "")[:2000],
                    )
                    return None

                images_preview = result.get("images", []) or []
                logger.info(
                    "[OCR/Clova] http_post_ok request_id=%s pid=%s http_ms=%.1f images_len=%s",
                    req_id,
                    os.getpid(),
                    http_ms,
                    len(images_preview),
                )
                
                # [핵심] 클로바는 PDF의 각 페이지를 'images' 리스트의 개별 요소로 반환합니다.
                # Clova OCR 응답:
                # - PDF: images[]에 각 페이지 결과가 들어온다. (images.length == 페이지 수)
                # - 단일 이미지: images[] 길이 1
                images = result.get('images', []) or []
                total_pages = len(images)
                for page_idx, image in enumerate(images):
                    tables_raw = image.get('tables')
                    pages_tables.append(_clova_tables_to_page_tables(tables_raw))
                    fields = image.get('fields', [])
                    if not fields:
                        # 표만 있고 필드 박스가 없는 페이지도 원문·키워드에 반영
                        merged = _merge_field_text_and_tables("", tables_raw)
                        pages_text.append(merged)
                        pages_layout.append([])
                        if callable(progress_cb):
                            try:
                                progress_cb(page_idx=page_idx, total_pages=total_pages, ok=True)
                            except Exception:
                                logger.exception("progress_cb 호출 실패 (빈 fields). page_idx=%s", page_idx)
                        continue

                    full_page_text = _fields_to_page_text(fields, image)
                    merged = _merge_field_text_and_tables(full_page_text, tables_raw)
                    pages_text.append(merged.strip())
                    pages_layout.append(_layout_blocks_reading_order(fields, image))
                    print(f"✅ {len(pages_text)}페이지 추출 및 정렬 완료")
                    if callable(progress_cb):
                        try:
                            progress_cb(page_idx=page_idx, total_pages=total_pages, ok=True)
                        except Exception:
                            logger.exception("progress_cb 호출 실패. page_idx=%s", page_idx)

                if not result.get("images"):
                    logger.warning(
                        "CLOVA OCR 성공 응답이지만 images가 비어 있습니다. filename=%s, requestId=%s",
                        filename,
                        request_json.get("requestId"),
                    )
                return pages_text, pages_tables, pages_layout
            else:
                elapsed = time.time() - started_at
                logger.error(
                    "Clova API 에러. status=%s, filename=%s, requestId=%s, elapsed=%.2fs, body=%s",
                    response.status_code,
                    filename,
                    request_json.get("requestId"),
                    elapsed,
                    (response.text or "")[:2000],
                )
                return None
        except Exception as e:
            logger.exception("OCR 처리 중 예외 발생. filename=%s, error=%s", filename, e)
            return None


    
    def process_file(self, file_bytes, filename, progress_cb=None):
        """텍스트 추출 및 페이지별 키워드 추출 실행.
        file_bytes: ocr_app에서 전달 — crop 적용 시 잘린 이미지 bytes만 넘어옴.
        """
        total_start = time.time()
        logger.info(
            "[OCR] process_file_start pid=%s file=%r bytes=%s",
            os.getpid(),
            filename,
            len(file_bytes),
        )
        # 1. OCR 텍스트 추출 (전달받은 이미지 = 원본 또는 잘린 영역만)
        extracted = self.extract_text_with_clova(file_bytes, filename, progress_cb=progress_cb)
        clova_elapsed = time.time() - total_start

        if extracted is None:
            logger.error(
                "[OCR] process_file_clova_failed pid=%s file=%r clova_elapsed_s=%.2f",
                os.getpid(),
                filename,
                clova_elapsed,
            )
            return {"status": "error", "message": "OCR 텍스트를 추출하지 못했습니다."}

        all_pages_text, all_pages_tables, all_pages_layout = extracted

        if not all_pages_text:
            return {"status": "error", "message": "OCR 텍스트를 추출하지 못했습니다."}

        # --- (보존) LLM 기반 페이지별 키워드 추출 — 복구 시 위 `from openai import OpenAI` 및 __init__의 gpt_client 주석 해제 후 아래 활성화,
        #     그리고 아래 "형태소 어댑터" 블록은 주석 처리
        # gpt_start = time.time()
        # all_keywords = []
        # for i, page_text in enumerate(all_pages_text):
        #     try:
        #         response = self.gpt_client.chat.completions.create(
        #             model=self.model,
        #             messages=[
        #                 {
        #                     "role": "system",
        #                     "content": (
        #                         "제공된 텍스트에서 학습에 필요한 핵심 단어(명사)만 추출하세요.\n"
        #                         "1. 한글 명사와 영어 단어(명사) 모두 추출하세요. 텍스트에 영어가 있으면 영어 단어도 반드시 포함하세요.\n"
        #                         "2. 숫자나 중요한 고유명사도 포함하세요.\n"
        #                         "3. 반드시 ['단어1', '단어2'] 형태의 JSON 배열로만 답변하세요.\n"
        #                         "4. 조사, 형용사는 제외하고 명사만 포함하세요."
        #                     ),
        #                 },
        #                 {
        #                     "role": "user",
        #                     "content": f"다음 텍스트에서 한글 명사와 영어 단어를 모두 포함해 키워드만 뽑아줘:\n\n{page_text}",
        #                 },
        #             ],
        #             temperature=0,
        #         )
        #         content = response.choices[0].message.content.strip()
        #         match = re.search(r"\[.*\]", content, re.DOTALL)
        #         if match:
        #             json_str = match.group().replace("'", '"')
        #             keywords = json.loads(json_str)
        #         else:
        #             keywords = []
        #         all_keywords.append(keywords)
        #     except Exception as e:
        #         print(f"페이지 {i+1} GPT 에러: {e}")
        #         all_keywords.append([])
        # gpt_duration = time.time() - gpt_start
        # print(f"⏱️ [GPT 키워드 추출 소요 시간]: {gpt_duration:.2f}초")

        # 2. 각 페이지별 형태소 어댑터 기반 키워드 추출 (외부 LLM 호출 없음)
        kw_start = time.time()
        all_keywords: list[list[str]] = []
        for page_text in all_pages_text:
            all_keywords.append(extract_keywords_from_text(page_text))
        kw_duration = time.time() - kw_start
        logger.info(
            "[OCR] keywords_done pid=%s file=%r kw_elapsed_s=%.2f pages=%s",
            os.getpid(),
            filename,
            kw_duration,
            len(all_pages_text),
        )

        total_duration = time.time() - total_start
        page_count = len(all_pages_text)
        logger.info(
            "[OCR] process_file_done pid=%s file=%r page_count=%s clova_plus_kw_elapsed_s=%.2f total_s=%.2f",
            os.getpid(),
            filename,
            page_count,
            clova_elapsed + kw_duration,
            total_duration,
        )
        # 3. 최종 결과 반환
        # 프론트(`front/src/api/ocr.ts`)는 다음 우선순위로 데이터를 사용:
        # 1) inner.pages가 배열이면 각 페이지의 original_text/keywords를 합쳐 사용
        # 2) 그렇지 않으면 original_text, keywords 단일 필드를 사용 (하위 호환)
        #
        # 여기서는 멀티 페이지를 정식 지원하기 위해 pages 배열을 내려준다.
        # keywords: 형태소/휴리스틱 기반 키워드 / blank_candidates: layout_blocks 기반 빈칸 후보(별도 목적)
        return {
            "status": "success",
            "pages": [
                {
                    "original_text": text,
                    "keywords": keywords,
                    "tables": tables,
                    "layout_blocks": layout,
                    "blank_candidates": build_blank_candidates_from_layout(layout, i),
                    "keyword_positions": build_keyword_positions_from_layout(keywords, layout, i),
                }
                for i, (text, keywords, tables, layout) in enumerate(
                    zip(
                        all_pages_text,
                        all_keywords,
                        all_pages_tables,
                        all_pages_layout,
                    )
                )
            ],
            "page_count": page_count,
            "total_duration": total_duration,
        }
