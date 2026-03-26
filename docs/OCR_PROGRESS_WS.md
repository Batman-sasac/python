# OCR 진행률 WebSocket (페이지 단위) 문서

이 문서는 OCR 처리 중 **페이지 단위 진행 상황(1페이지/2페이지/...)** 을 프론트로 실시간 전달하기 위한 WebSocket 연동 방법을 설명합니다.

## 목표

- 사용자가 PDF/다중 이미지 OCR을 업로드했을 때, 서버 처리 동안 “n / total 페이지 처리 완료” 같은 진행 UI를 표시
- HTTP `POST /ocr` 응답을 기다리는 동안에도 진행률을 수신 가능

## 구성 요소

- **WebSocket 구독 채널**
  - 서버: `python/app/ocr_app.py`
  - 엔드포인트: `GET /ws/ocr/{job_id}`
- **진행률 전송 매니저**
  - 서버: `python/app/ocr_ws.py`
  - 클래스: `OcrWsManager` (job_id → WebSocket 매핑)
- **OCR 처리 콜백**
  - 서버: `python/service/clova_ocr_service.py`
  - `process_file(..., progress_cb=...)` / `extract_text_with_clova(..., progress_cb=...)`

## 핵심 아이디어: job_id로 HTTP ↔ WS를 연결한다

서버가 별도의 “작업 생성 API”를 통해 job_id를 발급하지 않고, **클라이언트(프론트)가 job_id를 생성**합니다.

프론트는 같은 job_id를 다음 두 곳에 사용합니다.

- **(1) WebSocket 연결 경로**: `/ws/ocr/{job_id}`
- **(2) OCR 업로드 요청 FormData**: `job_id=<same job_id>`

서버는 `/ocr` 처리 중 progress 이벤트를 만들 때, **FormData로 받은 job_id**를 사용해 해당 WebSocket으로 push 합니다.

## API 스펙

### 1) WebSocket: 진행률 구독

- **경로**: `/ws/ocr/{job_id}`
- **역할**: 서버가 OCR 진행률 이벤트를 push
- **클라이언트 → 서버 메시지**: 내용은 사용하지 않음
  - 단, 연결 유지/종료 감지를 위해 서버는 `receive_text()` 루프를 수행함

### 2) HTTP: OCR 업로드

- **메서드/경로**: `POST /ocr`
- **Content-Type**: `multipart/form-data`
- **필수 필드**
  - `file`: 업로드 파일
- **선택 필드**
  - `job_id`: 진행률을 받을 때만 사용
  - `crop_x`, `crop_y`, `crop_width`, `crop_height`: 서버 crop을 사용하는 경우에만 사용

## WebSocket 메시지 스펙

서버는 페이지 처리 완료 시 아래 형태로 메시지를 보냅니다.

```json
{
  "type": "ocr_progress",
  "status": "page_done",
  "page": 2,
  "total_pages": 5,
  "filename": "sample.pdf"
}
```

- **type**: `"ocr_progress"` 고정
- **status**
  - `"page_done"`: 페이지 처리 완료
  - `"page_error"`: 페이지 처리 실패(현재는 확장 여지용; 기본 구현은 `ok=True`만 발행)
- **page**: 1부터 시작하는 페이지 번호 (1-based)
- **total_pages**: 전체 페이지 수 (PDF의 `images[]` 길이)
- **filename**: 업로드 파일명

## 프론트 연동 예시

아래 예시는 “WS 연결 → /ocr 업로드 → 진행률 수신”의 최소 흐름입니다.

### 웹(브라우저) 예시

```ts
const API_BASE = "https://api.example.com";
const token = "<BEARER_TOKEN>";

// 1) job_id 생성
const jobId = crypto.randomUUID();

// 2) WS base URL 만들기
const wsBase = API_BASE
  .replace("https://", "wss://")
  .replace("http://", "ws://");

// 3) WS 연결
const ws = new WebSocket(`${wsBase}/ws/ocr/${jobId}`);
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "ocr_progress" && msg.status === "page_done") {
    console.log(`OCR 진행: ${msg.page}/${msg.total_pages}`);
  }
};

// 4) 업로드 요청 (FormData에 job_id 포함)
const form = new FormData();
form.append("job_id", jobId);
form.append("file", fileInput.files[0]);

await fetch(`${API_BASE}/ocr`, {
  method: "POST",
  headers: {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  },
  body: form,
});
```

### Expo/RN에서의 job_id 생성 팁

- `crypto.randomUUID()`가 환경에 따라 없을 수 있으므로, 간단한 유니크 문자열로도 충분합니다.

```ts
const jobId = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
```

## 서버 구현 메모

### `/ocr`에서 progress_cb를 쓰는 이유

- 클로바 OCR 응답은 PDF의 경우 `images[]` 배열에 “페이지 결과”가 들어옵니다.
- `service/clova_ocr_service.py`에서 `images[]`를 순회하며 페이지 텍스트/테이블/레이아웃을 구성합니다.
- 이 루프의 각 iteration이 끝날 때 progress_cb를 호출하면, 프론트에 “페이지 완료” 이벤트를 push 할 수 있습니다.

### 동기 OCR 코드에서 WS 전송을 처리하는 방식

- `clova_service.process_file(...)` 호출이 동기 흐름이므로, `ocr_app.py`에서 `asyncio.get_running_loop().create_task(...)`로 WS 전송을 예약합니다.
- job_id가 없으면 콜백은 noop이며, 기존 HTTP `/ocr` 사용 방식에 영향을 주지 않습니다.

## 주의사항 / 운영 팁

- **스케일링(멀티 프로세스/멀티 인스턴스)**
  - 현재 구현은 메모리에서 `job_id → WebSocket`을 들고 있습니다.
  - 서버를 여러 프로세스/인스턴스로 띄우면, HTTP 요청이 처리되는 인스턴스와 WS가 붙은 인스턴스가 달라질 수 있어 이벤트가 누락될 수 있습니다.
  - 이 경우 Redis pub/sub 등 외부 브로커로 확장하는 것이 안전합니다.

- **보안**
  - WS는 job_id만으로 구독되므로, job_id가 노출되면 타인이 구독할 여지가 있습니다.
  - 필요하면 job_id를 충분히 랜덤(UUID)하게 하고, 추후에는 WS에도 인증(토큰 query/header 등)을 추가하세요.

