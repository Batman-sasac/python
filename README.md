## 프로젝트 개요

이 레포지토리는 **학습/복습 관리 앱의 백엔드 서버**입니다.  
이미지 OCR로 학습지를 인식하고, 채점·복습·리워드(포인트)·주간 통계·푸시 알림 등을 제공하는 **FastAPI 기반 REST API**로 구성되어 있습니다.  
클라이언트(모바일/웹)는 이 서버의 API를 호출하여 로그인, 학습 데이터 저장, 통계 조회, 알림 설정 등을 수행합니다.

**OCR 엔진 선정**: 여러 OCR 서비스·모델을 실제 학습지 이미지로 비교해 본 결과, **표와 체크박스**가 함께 있는 영역에서 **네이버 클로바 OCR**이 상대적으로 인식이 가장 안정적이어서, 백엔드 OCR 연동으로 채택했습니다.

## 기술 스택

- **Framework**: FastAPI, APIRouter 기반 모듈화
- **Scheduler**: APScheduler (복습 알림 스케줄링)
- **Database**: Supabase(PostgreSQL) SDK
- **Auth**: JWT 기반 인증 (`Authorization: Bearer <token>`)
- **OAuth**: 카카오 / 네이버 / 애플 소셜 로그인
- **Push 알림**: Expo Push API (iOS, `ExponentPushToken[...]`)
- **OCR**: 클로바 OCR 연동 (`service/clova_ocr_service.py`)
- **ETC**: Pillow(이미지 처리), requests, python-dotenv 등

## 디렉토리 구조 (백엔드)

- `main.py`  
  - FastAPI 앱 생성 및 라우터 등록  
  - CORS 설정, 정적 파일(`static`) 마운트  
  - APScheduler 시작 및 복습 알림 스케줄러 등록

- `core/database.py`  
  - Supabase 클라이언트 초기화 (`SUPABASE_URL`, `SUPABASE_ANON_KEY`)  
  - DB 연결 테스트 로그 출력

- `app/`  
  - `security_app.py` : JWT 발급/검증, `get_current_user` 인증 의존성  
  - `user_app.py` : 닉네임 설정, 사용자 통계, 홈 통계 API (`/auth/...`)  
  - `study_app.py` : 학습 채점, 학습 로그, 복습 채점 및 포인트 적립 (`/study/...`)  
  - `weekly_app.py` : 학습 목표 설정, 주간 성장 그래프, 이번 달 학습 통계 (`/cycle/...`)  
  - `reward_app.py` : 출석 보상, 리워드 랭킹 (`/reward/...`)  
  - `ocr_app.py` : OCR 사용량, OCR 실행, 학습 목록/조회/삭제 (`/ocr/...`)  
  - `ocr_ws.py` : OCR 진행률 WebSocket 연결 관리 (`/ws/ocr/{job_id}`)  
  - `notification_app.py` : 알림 관련 API  
  - `reports_app.py` : 리포트/통계 관련 API  
  - `firebase_app.py` : Firebase 관련 라우터  
  - `auth/` : 카카오/네이버/애플 로그인 콜백 및 토큰 처리  
  - `hint/` : 힌트/부가 학습 기능

- `service/`  
  - `notification_service.py` : 알림 대상 조회 및 Expo Push 발송 로직, 시뮬레이션 모드 지원  
  - `clova_ocr_service.py` : 클로바 OCR 연동  
  - `ocr_usage_service.py` : OCR 사용량 한도 관리

- `templates/`  
  - Jinja2 템플릿 (복습 화면 등 `study_app`에서 사용)

- `static/`  
  - 정적 리소스 (CSS/JS/이미지 등, 있을 경우)

## 주요 기능 요약

- **인증/사용자**
  - JWT 기반 인증 (`app/security_app.py`)  
  - 소셜 로그인(카카오/네이버/애플) 후 이메일/닉네임 저장  
  - 닉네임 설정 및 업데이트 (`POST /auth/set-nickname`)  
  - 사용자 학습 통계, 홈 대시보드 통계 제공

- **OCR & 학습 데이터**
  - 이미지 업로드 후 클로바 OCR 호출 (`POST /ocr`)  
  - 선택 영역(crop) OCR 지원  
  - OCR 결과(원문, 키워드, 빈칸, 퀴즈 HTML)와 정답/사용자 답안을 `ocr_data` 테이블에 저장  
  - OCR 사용량(페이지 수) 한도 관리 및 남은 횟수 안내

- **채점 & 복습**
  - 처음 학습 시 채점 및 `study_logs` / `reward_history` / `users.points` 갱신  
  - 복습 시 정답 비교, 리워드 적립, 포인트 합산  
  - 복습용 퀴즈 데이터(JSON) 조회, 복습 HTML 화면(render)

- **리워드/출석**
  - 앱 실행 시 출석체크 자동 처리 (`/reward/attendance`)  
  - 당일 이미 보상 지급 시 중복 방지  
  - 리워드 랭킹(상위 5명) 조회

- **통계/지표**
  - 주간 성장 그래프 (정답률 × 출석률, 최근 5주)  
  - 이번 달 학습 횟수 vs 목표 횟수 비교  
  - 홈 화면용 포인트/목표/당월 학습 횟수

- **알림(푸시)**
  - APScheduler로 5분마다 `check_and_send_reminders` 실행  
  - `is_notify`, `remind_time`, `remind_sent_at` 기준으로 발송 대상 필터링  
  - Expo Push API를 사용해 iOS 기기에 복습 알림 전송  
  - `NOTIFICATION_SIMULATE` 환경 변수로 시뮬레이션 모드 지원(실제 DB 갱신/발송 없이 로직만 검증)

## 추가·보강된 기능

- **연속 학습 보너스(10포인트)**: 어제·오늘처럼 **연속 2일 이상(STREAK_MIN_DAYS=2)** 학습 기록이 이어지면, 채점(`POST /study/grade`) 직후 연속학습 보너스로 **10포인트(STREAK_REWARD_AMOUNT=10)** 를 추가 지급합니다.  
  - **중복 방지**: 같은 날(KST 기준)에는 1회만 지급됩니다.  
  - **응답 필드**: `streak_bonus`(이번 요청에서 지급된 보너스), `consecutive_streak_days`(오늘 기준 연속 학습일 수)
- **페이지 단위 채점 통계**: 초기 채점 요청에서 페이지별 정답 수·문항 수를 함께 보내 기록할 수 있습니다(`page_correct_counts`, `page_question_counts`).
- **OCR 예상 소요 시간**: `POST /ocr/estimate`로 업로드 파일 기준 예상 페이지·처리 시간을 안내합니다.
- **OCR 진행률 WebSocket(페이지 단위)**: PDF/다중 이미지 OCR 처리 중, 페이지 완료(1페이지/2페이지/...) 이벤트를 WebSocket으로 push할 수 있습니다.  
  - WS: `GET /ws/ocr/{job_id}`  
  - HTTP 업로드: `POST /ocr`의 FormData에 `job_id`를 함께 전송  
  - 자세한 연동 방법: `docs/OCR_PROGRESS_WS.md`
- **학습 신고**: `POST /reports/submitted-report`로 신고·피드백을 접수합니다.
- **Expo 푸시 토큰**: `POST /firebase/user/update-fcm-token`에 `ExponentPushToken[...]` 형식 토큰을 등록합니다.

## API 엔드포인트 정리

### 공통

- **Base URL**: 예) `https://your-domain.com` (운영 환경 기준)
- **인증 필요**: 별도 표기 없으면 JWT Bearer 토큰 필요 (`Authorization: Bearer <JWT_TOKEN>`)

### 인증/사용자 (`user_app.py`, 소셜 로그인)

| Method | Path                         | 설명                           | 비고 |
|--------|-----------------------------|--------------------------------|------|
| GET    | `/config`                   | 프론트에서 사용하는 OAuth 설정 조회 | 공개 |
| POST   | `/auth/set-nickname`        | 닉네임 설정/변경               | 인증 |
| GET    | `/auth/user/stats`          | 총 학습 횟수/연속 학습일/월 목표 | 인증 |
| GET    | `/auth/home/stats`          | 현재 포인트, 월 목표, 이번 달 학습 횟수 | 인증 |
| GET    | `/auth/kakao/mobile`        | 카카오 로그인 콜백 (모바일용)  | 공개 |
| POST   | `/auth/kakao/mobile`        | 카카오 토큰 → 앱용 JWT 발급    | 공개 |
| GET    | `/auth/naver/mobile`        | 네이버 로그인 콜백 (모바일용)  | 공개 |
| POST   | `/auth/naver/mobile`        | 네이버 토큰 → 앱용 JWT 발급    | 공개 |
| POST   | `/auth/apple/mobile`        | 애플 로그인 처리 및 JWT 발급   | 공개 |

### OCR 및 학습 데이터 (`ocr_app.py`)

| Method | Path                              | 설명                                   |
|--------|-----------------------------------|----------------------------------------|
| GET    | `/ocr/usage`                     | OCR 사용량 및 남은 무료 페이지 수 조회 |
| POST   | `/ocr/estimate`                  | 업로드 파일 기준 예상 페이지/시간 계산 |
| POST   | `/ocr`                           | 이미지(선택 영역 포함) OCR 수행        |
| WS     | `/ws/ocr/{job_id}`               | OCR 진행률(페이지 완료) WebSocket 구독 |
| GET    | `/ocr/quiz/{quiz_id}`            | 복습용 퀴즈 데이터(JSON) 조회          |
| DELETE | `/ocr/ocr-data/delete/{quiz_id}` | 특정 학습(OCR 데이터) 삭제             |
| GET    | `/ocr/list`                      | 사용자의 학습 목록(OCR 데이터 리스트)  |

### 학습/채점/복습 (`study_app.py`, `hint_app.py`)

| Method | Path                          | 설명                                      |
|--------|------------------------------|-------------------------------------------|
| POST   | `/study/grade`               | 최초 학습 채점 및 학습 로그/리워드 적립  |
| GET    | `/study/review_study/{quiz_id}` | 복습 HTML 화면 (서버 렌더링)          |
| POST   | `/study/review-study`        | 복습 채점, 리워드/포인트 갱신            |
| GET    | `/study/hint/{quiz_id}`      | 학습용 힌트 조회                          |

### 리워드/출석 (`reward_app.py`)

| Method | Path                  | 설명                            |
|--------|----------------------|---------------------------------|
| POST   | `/reward/attendance` | 앱 실행 시 자동 출석 체크/리워드 |
| GET    | `/reward/leaderboard`| 포인트 상위 5명 리더보드 조회   |

### 학습 목표/통계 (`weekly_app.py`)

| Method | Path                   | 설명                                         |
|--------|------------------------|----------------------------------------------|
| POST   | `/cycle/set-goal`            | 월 학습 목표(횟수) 설정                      |
| GET    | `/cycle/stats/weekly-growth` | 최근 5주간 주간 성장 점수(정답률×출석률) 조회 |
| GET    | `/cycle/learning-stats`      | 이번 달 학습 횟수 vs 목표 횟수 비교          |

### 알림/FCM (`notification_app.py`, `firebase_app.py`)

| Method | Path                          | 설명                             |
|--------|------------------------------|----------------------------------|
| POST   | `/firebase/user/update-fcm-token` | Expo 푸시 토큰 등록 (`ExponentPushToken[...]`) |
| POST   | `/notification-push/update`  | 알림 설정 및 리마인드 시간 업데이트 |
| GET    | `/notification-push/me`      | 내 알림 설정/리마인드 시간 조회  |

### 리포트 (`reports_app.py`)

| Method | Path               | 설명                     |
|--------|--------------------|--------------------------|
| POST   | `/reports/submitted-report` | 학습 리포트/피드백·신고 제출  |

## 실행 방법

1. **환경 변수 / 시크릿**

- 운영/스테이징 환경에서는 **Git Secrets / CI/CD 시크릿 설정**을 통해 다음 값을 주입합니다.
  - `SUPABASE_URL`, `SUPABASE_ANON_KEY`
  - `JWT_SECRET_KEY`
  - `API_BASE_URL`
  - 소셜 로그인 키: `KAKAO_REST_API_KEY`, `KAKAO_REDIRECT_URI`, `NAVER_CLIENT_ID`, `NAVER_REDIRECT_URI`, (애플 관련 키 등)
  - 알림 시뮬레이션 플래그: `NOTIFICATION_SIMULATE`
- 로컬 개발 환경에서는 동일한 키 이름으로 `.env`를 만들어 사용해도 됩니다.

2. **가상환경 & 패키지 설치**

   ```bash
   # (선택) 가상환경 생성
   python -m venv .venv
   source .venv/bin/activate  # Windows는 .venv\Scripts\activate

   pip install -r requirements.txt  # 또는 프로젝트에서 사용하는 패키지 설치
   ```

3. **개발 서버 실행**

   ```bash
   uvicorn main:app --reload
   # 또는
   python main.py
   ```

4. **API 테스트**

   - 기본 상태 체크: `GET /` → `{ "status": "running" }`  
   - 설정 조회: `GET /config`  
   - 위의 **API 엔드포인트 표**를 참고하여 클라이언트/문서화에 사용합니다.

## 인증 방식

- 모든 보호된 API는 **JWT Bearer 토큰**을 사용합니다.
- 클라이언트는 로그인/회원가입 후 발급받은 토큰을 다음과 같이 헤더에 포함해서 요청합니다.

```http
Authorization: Bearer <JWT_TOKEN>
```

- 서버에서는 `app/security_app.py`의 `get_current_user` 의존성을 통해 토큰을 검증하고, 이메일을 추출하여 각 비즈니스 로직에 사용합니다.

## 배포 시 참고 사항

- `CORS` 설정은 현재 `allow_origins=["*"]`로 열려 있으므로, 실제 운영에서는 **허용 도메인만 명시적으로 지정**하는 것을 권장합니다.
- Supabase RLS 정책과 서비스 키 사용 여부를 환경에 맞게 조정해야 합니다.
- APScheduler는 프로세스 내에서 동작하므로, **다중 프로세스/다중 인스턴스 환경**에서는 스케줄러 중복 실행 방지 전략(전용 워커, 락 등)을 고려해야 합니다.

# 📚 AI Smart Study Assistant: Scan & Learn
> **문서 스캔부터 핵심 단어 추출, 맞춤형 퀴즈와 리워드까지 하나로 연결되는 지능형 학습 플랫폼**

본 프로젝트는 **네이버 클로바 OCR**과 **OpenAI GPT API**를 결합하여 학습자의 교재를 디지털 데이터로 변환하고, 자기주도 학습을 돕는 기능을 제공하는 백엔드 시스템입니다.  
**OCR**은 여러 서비스·모델을 학습지 이미지로 비교한 뒤, **표·체크박스**가 포함된 영역에서 인식이 상대적으로 가장 안정적인 **네이버 클로바 OCR**을 사용합니다.

---

### 🛠 기술 스택 (Technical Specifications)

| Category | Tech Stack | Details |
| :--- | :--- | :--- |
| **Language** | **Python 3** | FastAPI 기반 REST API |
| **Framework** | **FastAPI** | APIRouter 모듈 구성, JWT 인증 |
| **AI/ML** | **Naver Clova OCR, OpenAI API** | 문서 텍스트 추출, 키워드·퀴즈 생성 |
| **Database** | **PostgreSQL (Supabase)** | 사용자·학습·리워드 데이터 |
| **Auth** | **OAuth 2.0 (Kakao / Naver / Apple)** | 모바일 소셜 로그인 및 JWT 발급 |
| **Push** | **Expo Push API** | 복습 알림 (iOS `ExponentPushToken`) |
| **Scheduler** | **APScheduler** | 복습 알림 발송 스케줄 |
| **Testing** | **Pytest** | (선택) 자동화 테스트 |

---

## 🌟 핵심 기능 (Key Features)

### 1. 지능형 문서 분석 (AI OCR & NLP)
* **Smart Scan**: 네이버 클로바 OCR로 이미지·PDF에서 텍스트를 추출합니다. (표·체크박스 인식 품질을 기준으로 엔진을 선정했습니다.)
* **Keyword Extraction**: GPT API로 학습에 필요한 **핵심 단어**를 선별합니다.
* **Wait Time Estimation**: `POST /ocr/estimate`로 업로드 파일 기준 **예상 소요 시간**을 안내합니다.
* **Crop OCR**: 선택 영역만 잘라 OCR할 수 있습니다.

### 2. 맞춤형 학습 도구 (Study System)
* **Blank Quiz**: 추출된 단어 기반 빈칸 문제·퀴즈 HTML 생성.
* **Multi-Level Hints**: 3단계 힌트 (`app/hint/`, `GET /study/hint/{quiz_id}`).
  * **초성 힌트** · **앞글자 힌트** · **뒷글자 힌트**
* **페이지 단위 통계**: 초기 채점 시 페이지별 정답·문항 수를 기록할 수 있습니다.

### 3. 게임화 리워드 시스템 (Gamification)
* **출석·학습·복습 리워드**: 출석 체크, 채점 완료, 복습 시 포인트 지급.
* **연속 학습 보너스**: 연속 학습일 조건 충족 시 추가 포인트 자동 지급.
* **리더보드**: 포인트 상위 사용자 조회.

### 4. 학습 통계 및 분석 (Analytics)
* **Weekly Growth**: 최근 5주간 정답률·출석률 기반 성장 지표 (`/cycle/stats/weekly-growth`).
* **Monthly Goal**: 이번 달 학습 횟수 vs 목표 (`/cycle/learning-stats`).

### 5. 알림·신고·연동 (Notifications & Reports)
* **복습 알림**: 알림 on/off·시간 설정, Expo 푸시 토큰 등록 (`/firebase/user/update-fcm-token`).
* **신고 접수**: `POST /reports/submitted-report`로 피드백·신고 제출.

---

## 📂 프로젝트 구조 (Project Structure)

```text
.
├── main.py                 # FastAPI 앱, 라우터 등록, APScheduler
├── app/
│   ├── ocr_app.py          # OCR, 사용량, 학습 목록
│   ├── study_app.py        # 채점, 복습 HTML, 학습 로그
│   ├── user_app.py         # /auth 닉네임·통계
│   ├── auth/               # 카카오·네이버·애플 로그인
│   ├── hint/               # 힌트 API
│   ├── reward_app.py       # 출석·리더보드
│   ├── weekly_app.py       # /cycle 목표·통계
│   ├── notification_app.py # 복습 알림 설정
│   ├── firebase_app.py     # Expo 푸시 토큰
│   └── reports_app.py      # 신고 접수
├── core/
│   └── database.py         # Supabase 클라이언트
└── service/
    ├── clova_ocr_service.py    # 클로바 OCR 연동
    ├── ocr_usage_service.py    # OCR 사용량
    ├── notification_service.py # Expo Push 발송
    └── reward_service.py       # 연속 학습 보너스 등
```
