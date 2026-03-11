## 프로젝트 개요

이 레포지토리는 **학습/복습 관리 앱의 백엔드 서버**입니다.  
이미지 OCR로 학습지를 인식하고, 채점·복습·리워드(포인트)·주간 통계·푸시 알림 등을 제공하는 **FastAPI 기반 REST API**로 구성되어 있습니다.  
클라이언트(모바일/웹)는 이 서버의 API를 호출하여 로그인, 학습 데이터 저장, 통계 조회, 알림 설정 등을 수행합니다.

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
  - 닉네임 설정 및 업데이트 (`/set-nickname`)  
  - 사용자 학습 통계, 홈 대시보드 통계 제공

- **OCR & 학습 데이터**
  - 이미지 업로드 후 클로바 OCR 호출 (`/ocr/ocr`)  
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

## API 엔드포인트 정리

### 공통

- **Base URL**: 예) `https://your-domain.com` (운영 환경 기준)
- **인증 필요**: 별도 표기 없으면 JWT Bearer 토큰 필요 (`Authorization: Bearer <JWT_TOKEN>`)

### 인증/사용자 (`user_app.py`, 소셜 로그인)

| Method | Path                         | 설명                           | 비고 |
|--------|-----------------------------|--------------------------------|------|
| GET    | `/config`                   | 프론트에서 사용하는 OAuth 설정 조회 | 공개 |
| POST   | `/set-nickname`             | 닉네임 설정/변경               | 인증 |
| GET    | `/user/stats`               | 총 학습 횟수/연속 학습일/월 목표 | 인증 |
| GET    | `/home/stats`               | 현재 포인트, 월 목표, 이번 달 학습 횟수 | 인증 |
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
| GET    | `/ocr/quiz/{quiz_id}`            | 복습용 퀴즈 데이터(JSON) 조회          |
| DELETE | `/ocr/ocr-data/delete/{quiz_id}` | 특정 학습(OCR 데이터) 삭제             |
| GET    | `/ocr/list`                      | 사용자의 학습 목록(OCR 데이터 리스트)  |

### 학습/채점/복습 (`study_app.py`, `hint_app.py`)

| Method | Path                          | 설명                                      |
|--------|------------------------------|-------------------------------------------|
| POST   | `/study/grade`               | 최초 학습 채점 및 학습 로그/리워드 적립  |
| GET    | `/review_study/{quiz_id}`    | 복습 HTML 화면 (서버 렌더링)             |
| POST   | `/review-study`              | 복습 채점, 리워드/포인트 갱신            |
| GET    | `/study/hint/{quiz_id}`      | 학습용 힌트 조회                          |

### 리워드/출석 (`reward_app.py`)

| Method | Path                  | 설명                            |
|--------|----------------------|---------------------------------|
| POST   | `/reward/attendance` | 앱 실행 시 자동 출석 체크/리워드 |
| GET    | `/reward/leaderboard`| 포인트 상위 5명 리더보드 조회   |

### 학습 목표/통계 (`weekly_app.py`)

| Method | Path                   | 설명                                         |
|--------|------------------------|----------------------------------------------|
| POST   | `/set-goal`            | 월 학습 목표(횟수) 설정                      |
| GET    | `/stats/weekly-growth` | 최근 5주간 주간 성장 점수(정답률×출석률) 조회 |
| GET    | `/learning-stats`      | 이번 달 학습 횟수 vs 목표 횟수 비교          |

### 알림/FCM (`notification_app.py`, `firebase_app.py`)

| Method | Path                          | 설명                             |
|--------|------------------------------|----------------------------------|
| POST   | `/user/update-fcm-token`     | 사용자 FCM/Expo 토큰 업데이트    |
| POST   | `/notification-push/update`  | 알림 설정 및 리마인드 시간 업데이트 |
| GET    | `/notification-push/me`      | 내 알림 설정/리마인드 시간 조회  |

### 리포트 (`reports_app.py`)

| Method | Path               | 설명                     |
|--------|--------------------|--------------------------|
| POST   | `/submitted-report`| 학습 리포트/피드백 제출  |

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

본 프로젝트는 **Naver Clova OCR**과 **OpenAI GPT-4**를 결합하여 학습자의 교재를 디지털 데이터로 변환하고, 자기주도 학습을 돕는 다양한 기능을 제공하는 고성능 백엔드 시스템입니다.

---

### 🛠 기술 스택 (Technical Specifications)

| Category | Tech Stack | Details |
| :--- | :--- | :--- |
| **Language** | **Python 3.14+** | 최신 문법 및 고성능 비동기 처리 활용 |
| **Framework** | **FastAPI** | 비동기 기반의 빠르고 현대적인 API 프레임워크 |
| **AI/ML** | **Naver Clova OCR, OpenAI GPT API** | 문서 텍스트 추출 및 지능형 단어 선별/문제 생성 |
| **Database** | **PostgreSQL, Supabase** | 강력한 관계형 DB 및 효율적인 ORM 관리 |
| **Auth** | **Kakao OAuth 2.0** | 카카오 소셜 로그인을 통한 간편한 인증 체계 |
| **Testing** | **Pytest** | 견고한 로직 검증을 위한 자동화 테스트 프레임워크 |

---

## 🌟 핵심 기능 (Key Features)

### 1. 지능형 문서 분석 (AI OCR & NLP)
* **Smart Scan**: `Naver Clova OCR`을 통해 고해상도 이미지 및 PDF에서 텍스트를 정교하게 추출합니다.
* **Keyword Extraction**: GPT API를 활용해 전체 텍스트 중 학습에 필요한 **핵심 단어**만 선별적으로 추출합니다.
* **Wait Time Estimation**: 대용량 파일 분석 시, PDF 페이지 수와 이미지 개수를 계산하여 사용자에게 **실시간 예상 소요 시간**을 안내합니다.

### 2. 맞춤형 학습 도구 (Study System)
* **Blank Quiz**: 추출된 단어를 기반으로 빈칸 채우기 문제를 자동 생성합니다.
* **Multi-Level Hints**: 학습 수준에 따른 3단계 힌트 시스템을 제공합니다.
  * **초성 힌트**: 단어의 자음만 노출 (예: `ㄱㅁㄴ`)
  * **앞글자 힌트**: 단어의 앞부분 노출 (예: `제미...`)
  * **뒷글자 힌트**: 단어의 뒷부분 노출 (예: `...미니`)

### 3. 게임화 리워드 시스템 (Gamification)
* **Point Rewards**: 학습 동기 부여를 위해 다양한 활동에 리워드를 지급합니다.
  * **출석 체크**: 매일 접속 시 리워드 제공.
  * **학습 달성**: 문제 풀이 세션 완료 시 리워드 제공.
  * **복습 보너스**: 복습 시 맞춘 단어 개수에 따라 추가 리워드 제공.

### 4. 학습 통계 및 분석 (Analytics)
* **Weekly Report**: 주간 **출석률**과 **정답률**을 결합한 성취도 데이터 반환.
* **Monthly Data**: 월간 복습 횟수 및 누적 학습 데이터를 분석하여 반환.

---

## 📂 프로젝트 구조 (Project Structure)

```text
C:\bat_python
├── app/
│   ├── ocr_app.py           # Clova OCR & GPT 분석 엔드포인트
│   ├── study_app.py         # 빈칸 문제 생성 및 힌트 로직
│   ├── reward_app.py        # 출석 및 학습 리워드 관리
│   ├── weekly_app.py        # 주간/월간 통계 데이터 가공
│   └── user_app.py          # 카카오 로그인 및 사용자 관리
├── core/
│   ├── clova_ocr_service.py # OCR 엔진 통신 및 대기 시간 계산 로직
│   ├── vision_service.py    # 이미지 전처리 및 비전 서비스
│   └── notification_service.py # 알림 시스템 서비스
├── database.py              # PostgreSQL Connection 설정
└── models.py                # 유저, 리워드, 학습 데이터 DB 스키마
