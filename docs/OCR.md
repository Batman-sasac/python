# OCR — 저장 흐름·환경 변수·응답 스키마·프론트 UI

엔드포인트 경로·메서드 요약은 [`API.md`](./API.md) 의 **OCR** 절을 보면 됩니다. 이 문서는 **백엔드가 어디에 무엇을 저장하는지**, **2열 보정**, **`POST /ocr` 응답 JSON**, **프론트 UI**를 한곳에 모은 것입니다.

---

## 저장 흐름

| 단계 | API | DB |
|------|-----|-----|
| OCR만 실행 | `POST /ocr` | **`ocr_data` 행을 만들지 않음.** 클로바+GPT 결과는 HTTP 응답으로만 반환. 사용량은 `add_ocr_usage`로 페이지 수만 누적 (`app/ocr_app.py`). |
| 학습으로 확정 | `POST /study/grade` | **`ocr_data` insert** — `ocr_text`, `answers`, `user_answers`, `quiz_html` 등 (`app/study_app.py`). |

### `ocr_text`가 채워지는 방식 (`app/study_app.py`)

- 프론트가 **`ocr_text`를 JSON으로 보내면 그대로 저장**하는 것이 가장 풍부합니다. `POST /ocr` 응답의 `data` 객체(또는 그걸 `pages`/`blanks`/`quiz` 형태에 맞게 감싼 것)를 넣으면, **2열로 합쳐진 `original_text`**·`tables`·`layout_blocks`까지 DB에 보존됩니다.
- **`ocr_text`를 안 보내면** 서버가 `original_text` / `keywords` / `quiz_html`만으로 최소 구조(`pages` 한 덩어리, `blanks`, `quiz`)를 생성합니다. 이 경우 OCR 상세(표·레이아웃)는 없을 수 있습니다.
- 채점 시 `page_correct_counts` 등이 있으면 같은 `ocr_text` JSON 안에 **`page_stats`**로 붙습니다.

### Supabase `ocr_data` (요약)

| 컬럼 | 설명 |
|------|------|
| `ocr_text` (jsonb) | 보통 `{ "pages": [...], "blanks": [...], "quiz": {...}, "page_stats"? }` — `app/ocr_app.py` 주석과 동일. |
| `answers`, `user_answers`, `quiz_html` | jsonb |

복습·목록 조회는 `GET /ocr/quiz/{quiz_id}`, `GET /ocr/list` 등에서 `ocr_text`를 읽습니다.

---

## 환경 변수 — 2열 `original_text` 보정

- **`.env` 예시**

  ```env
  OCR_TWO_COLUMN_LAYOUT=1
  ```

  `true` / `yes` 도 동일하게 인식합니다 (`service/clova_ocr_service.py`).

- **동작**: `OCR_TWO_COLUMN_LAYOUT`가 켜져 있고, 페이지 필드에 대해 `_should_use_two_columns` 휴리스틱을 통과하면, `original_text`를 **왼쪽 열 줄 | 오른쪽 열 줄** 형태로 합칩니다.
- **3열**: 현재 코드에는 **없음**. 확장 시 같은 파일의 `_fields_to_page_text` 분기와 별도 env(예: `OCR_THREE_COLUMN_LAYOUT`)를 추가하는 식이 자연스럽습니다.

### 관련 코드 위치

| 파일 | 역할 |
|------|------|
| `service/clova_ocr_service.py` | 클로바 호출, GPT 키워드, `_fields_to_page_text` 2열 보정, `pages` 배열 조립 |
| `app/ocr_app.py` | `POST /ocr`, 사용량, (선택) `job_id` WebSocket 진행률 |
| `app/study_app.py` | `POST /study/grade` → `ocr_data` 저장 |

---

## POST `/ocr` 응답 상세 (프론트 연동)

#### 성공 (`HTTP 200`, `status`: `"success"`)

최상위는 OCR 엔진 결과를 `data`에 그대로 감싼 형태입니다.

```json
{
  "status": "success",
  "data": {
    "status": "success",
    "pages": [ /* 아래 PageItem 배열 */ ],
    "page_count": 1,
    "total_duration": 12.34
  },
  "is_unlimited": false
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `data.pages` | `PageItem[]` | 페이지별 OCR·키워드·표·레이아웃. **멀티 페이지의 정식 소스.** |
| `data.page_count` | `number` | 페이지 수 (`pages.length`와 동일하게 쓰면 됨). |
| `data.total_duration` | `number` | 서버에서 OCR+GPT까지 걸린 시간(초). UI에는 짧은 부가 정보·디버그용 권장. |
| `data.status` | `string` | 엔진 내부 성공 플래그 (`"success"`). |
| `is_unlimited` | `boolean` | 특정 계정 무제한 여부(화이트리스트). |

#### `PageItem` (각 `data.pages[i]`)

한 페이지를 나타내는 객체입니다. **표가 없거나 텍스트 필드만 있으면** `tables`·`layout_blocks`는 빈 배열 `[]`이거나 필드 자체가 생략될 수 있습니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `original_text` | `string` | 해당 페이지에서 인식한 **전체 텍스트** (줄바꿈 포함 가능). 화면에는 “원문” 영역에 그대로 넣으면 됨. |
| `keywords` | `string[]` | GPT가 뽑은 **핵심 단어** 배열. 순서는 중요하지 않을 수 있음. 빈칸 후보·칩 UI에 사용. |
| `tables` | `OcrTableBlock[]` | 이 페이지에서 인식한 **표 개수만큼** 요소가 있음. 표가 없으면 `[]`. |
| `layout_blocks` | `LayoutBlock[]` | **문단/단어 단위 박스**. 읽기 순서대로 정렬됨. 좌표는 아래 참고. 없으면 `[]`. |

**한 페이지 전체 예시** (표 1개 + 레이아웃 블록 2개가 있는 경우):

```json
{
  "original_text": "1. 다음 표를 보고 답하시오.\n\n오늘의 학습 목표는 복습입니다.",
  "keywords": ["표", "학습", "복습", "목표"],
  "tables": [
    {
      "rows": [
        ["항목", "내용"],
        ["날짜", "2025-03-28"],
        ["체크", "☑ 완료"]
      ]
    }
  ],
  "layout_blocks": [
    { "text": "1. 다음 표를 보고", "x": 0.08, "y": 0.05, "width": 0.35, "height": 0.03 },
    { "text": "답하시오.", "x": 0.44, "y": 0.05, "width": 0.12, "height": 0.03 }
  ]
}
```

- **프론트에서의 최소 처리**: `pages.map((p, i) => …)` 로 페이지마다 카드/섹션을 나누고, 각 카드 안에 순서대로 **① 원문** → **② 키워드 칩** → **③ 표 목록** → **④ (선택) 레이아웃** 을 두면 됨.

#### `OcrTableBlock` (`tables` 배열의 각 요소)

클로바가 인식한 **표 하나**입니다. 한 페이지에 표가 여러 개면 `tables` 배열 길이가 2 이상이 됩니다.

**형태**

```json
{ "rows": [ ["열0행0", "열1행0", "열2행0"], ["열0행1", "열1행1", "열2행1"] ] }
```

| 항목 | 설명 |
|------|------|
| `rows` | 2차원 배열. **`rows[rowIndex][colIndex]`** = 그 칸에 들어갈 문자열. |
| 행·열 수 | 각 행의 길이(`cols`)가 같지 않을 수 있음(병합 셀 등). UI에서는 **가장 긴 열 개수**에 맞춰 빈 문자열로 패딩하거나, `<table>` 에서 `colspan` 은 서버에서 주지 않으므로 **그대로 셀 나열**만 하면 됨. |

**표가 2개인 페이지 예시**

```json
"tables": [
  {
    "rows": [
      ["문제 번호", "정답"],
      ["1", "가"],
      ["2", "나"]
    ]
  },
  {
    "rows": [
      ["요약", "메모"],
      ["오늘", "잘함"]
    ]
  }
]
```

- 렌더링: `tables.forEach((tbl, ti) => …)` 로 **표 제목**을 `표 ${ti + 1}` 같은 식으로 붙이고, `tbl.rows.map(row => <tr>{row.map(cell => <td>…)}</tr>)` 형태가 가장 단순함.
- 가로 스크롤: 열이 많으면 `<table>` 을 `overflow-x: auto` 래퍼로 감쌀 것.

#### `LayoutBlock` (`layout_blocks` 배열의 각 요소)

OCR 필드 단위 박스입니다. **좌표는 해당 페이지 이미지의 픽셀이 아니라, 페이지 너비·높이에 대한 비율(0~1)** 입니다. 예: 페이지가 1000×2000px이면 `x: 0.1` 은 왼쪽에서 100px 지점에 해당합니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `text` | `string` | 그 영역에서 인식된 문자열. |
| `x` | `number` | 박스 **왼쪽** 위치 = `(왼쪽 가장자리까지의 거리) / (페이지 전체 너비)` |
| `y` | `number` | 박스 **위쪽** 위치 = `(위쪽 가장자리까지의 거리) / (페이지 전체 높이)` |
| `width` | `number` | 박스 너비 / 페이지 너비 |
| `height` | `number` | 박스 높이 / 페이지 높이 |

**좌표 예시** (숫자로 감 잡기)

```json
[
  { "text": "제목", "x": 0.1, "y": 0.02, "width": 0.8, "height": 0.04 },
  { "text": "본문 첫 줄", "x": 0.1, "y": 0.08, "width": 0.85, "height": 0.05 }
]
```

- **배열 순서**: 문서를 사람이 읽는 순서(위→아래, 같은 줄에서는 왼→오)와 맞춰 서버에서 정렬되어 있음. 리스트 UI로 보여줄 때는 **이 순서대로** `map` 하면 됨.
- **이미지 위 오버레이 (웹 CSS 예시)**  
  - 부모: 스캔 이미지와 **같은 크기**를 가지는 래퍼에 `position: relative`.  
  - 각 블록: `position: absolute; left: ${x * 100}%; top: ${y * 100}%; width: ${width * 100}%; height: ${height * 100}%;`  
  - (React Native 등은 동일 비율을 `width` 기준 퍼센트 또는 `Dimensions`로 곱해 적용.)
- **이미지가 없을 때**: `layout_blocks`만 순서대로 세로 리스트(`text`만 표시)로 써도 되고, 접어 두어도 됨.

#### 데이터 사용 우선순위 (파싱)

1. `response.data.pages`가 **배열이면** 각 페이지의 `original_text` / `keywords`를 사용 (여러 페이지면 `original_text`는 `\n\n`으로 이어붙이기 등 앱 정책에 따름).
2. 구형 응답만 있는 경우 등 예외적으로 단일 필드(`original_text`, `keywords`만 있는 형태)는 하위 호환용 — 현재 엔진은 **`pages` 배열**을 기준으로 맞추면 됨.

#### 한도 초과

`status`: `"limit_reached"` 등 — `{ "message", "pages_used", "pages_limit" }` 형태. 프론트는 업로드 전에 `GET /ocr/usage`로 안내 가능.

#### (선택) 페이지 진행률 — WebSocket

- multipart에 `job_id`(클라이언트 생성 UUID 등)를 넣고, 동일 `job_id`로 **`/ws/ocr/{job_id}`** 에 먼저 연결하면, PDF 등 **페이지 단위 처리 완료** 시 이벤트를 받을 수 있음 (`app/ocr_ws.py`).
- 페이로드 예: `{ "type": "ocr_progress", "status": "page_done" \| "page_error", "page": 1, "total_pages": 5, "filename": "..." }`.
- `job_id` 없이 `POST /ocr` 만 호출해도 동작에는 문제 없음.

### 프론트 UI 권장 (구체)

| 영역 | 데이터 경로 | UI 구현 팁 |
|------|-------------|------------|
| **멀티 페이지** | `data.page_count`, `data.pages.length` | `page_count > 1`이면 상단에 `페이지 2 / 5` 또는 `SegmentedControl` / `TabView`. `pages[activeIndex]` 만 본문에 렌더하면 메모리에 유리. |
| **원문** | `pages[i].original_text` | `<ScrollView>` 또는 긴 텍스트 컴포넌트. `SelectableText`(Flutter)·복사 버튼 등으로 복사 지원. |
| **키워드** | `pages[i].keywords` | `keywords.map(w => <Chip label={w} onPress={() => 빈칸에 삽입} />)`. 배열이 비어 있으면 섹션 숨김. |
| **표** | `pages[i].tables` | `tables.length === 0` 이면 섹션 없음. `tables.map((t, i) => <section key={i}><h3>표 {i+1}</h3><table>…t.rows…</table></section>)`. 열 많으면 가로 스크롤 `View`. |
| **레이아웃** | `pages[i].layout_blocks` | (1) 스캔 이미지 URL이 있을 때: 이미지와 동일 비율 컨테이너 + 위 `LayoutBlock` CSS 절대좌표. (2) 이미지 없음: `layout_blocks.map(b => <Text>{b.text}</Text>)` 세로 나열. |
| **부가** | `data.total_duration` | `"약 12초"`처럼 한 줄 또는 설정 화면·로그만. |

**한 화면에서의 섹션 순서 예**

1. 페이지 인디케이터 (멀티일 때만)  
2. **원문** — `original_text`  
3. **키워드** — `keywords` 칩  
4. **인식된 표** — `tables[]` 각각 `rows` 렌더  
5. **텍스트 영역(선택)** — `layout_blocks` — 이미지 있으면 오버레이, 없으면 리스트  

복습 화면에서 동일 구조가 필요하면 `GET /ocr/quiz/{quiz_id}` 의 `data.pages`, `data.layout_meta` 등을 사용 (저장된 `ocr_text` JSON 구조와 일치).
