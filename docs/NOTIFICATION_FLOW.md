# 알림 기능 정리 — 플로우 & 세팅

현재 알림은 **iOS 전용**이며 **Expo Push API**(ExponentPushToken)만 사용합니다. Android는 미지원(스킵)입니다.

---

## 1. 전체 플로우 요약

```
[iOS 앱]                          [백엔드]                         [Expo Push]
   │                                  │                                  │
   │ 1. 토큰 등록                      │                                  │
   │    getExpoPushTokenAsync()       │                                  │
   │    → ExponentPushToken           │                                  │
   │ ── POST /firebase/user/update-fcm-token ──► users.fcm_token 저장     │
   │                                  │                                  │
   │ 2. 알림 설정 저장                 │                                  │
   │ ── POST /notification-push/update ──────► users.is_notify,         │
   │    (is_notify, remind_time)      │         remind_time 저장          │
   │                                  │                                  │
   │ 3. 테스트 푸시 (수동)              │                                  │
   │ ── POST /notification-push/test ────────► DB에서 fcm_token 조회     │
   │                                  │         send_push_notification() │
   │                                  │ ──────────────────────────────────► Expo Push API
   │                                  │                                  │
   │ 4. 스케줄 복습 알림 (자동)         │                                  │
   │    (앱 호출 없음)                 │  APScheduler 5분마다              │
   │                                  │  check_and_send_reminders()      │
   │                                  │  → is_notify=True & remind_time=now
   │                                  │  → send_push_notification()      │
   │                                  │ ──────────────────────────────────► Expo Push API
   │ ◄──────────────────────────────────────────────────────────────────── 푸시 수신
```

---

## 2. 프론트엔드 (front/src/api/notification.ts)

### 2.1 역할

| 함수 | 역할 | 호출 시점 |
|------|------|-----------|
| `registerAndSyncPushToken(authToken)` | iOS에서 Expo 푸시 토큰 발급 후 백엔드에 저장 | 홈 진입 시(App.tsx), 알림 설정 화면 진입 시(AlarmSettingScreen) |
| `updateNotificationSettings(token, { is_notify, remind_time })` | 복습 알림 on/off, 알림 시간 저장 | 알림 설정 화면에서 토글/시간 변경 시 |
| `getMyNotificationStatus(authToken)` | 내 알림 설정·토큰 등록 여부 조회 | (필요 시) 알림 설정 화면 등 |
| `sendTestNotification(authToken)` | 테스트 푸시 1통 발송 요청 | 알림 설정 화면 "테스트 알림 받기" 버튼 |
| `updatePushToken(authToken, pushToken)` | 발급한 푸시 토큰을 백엔드에 전송 (내부 사용) | `registerAndSyncPushToken` 내부 |

### 2.2 토큰 플로우 (iOS만)

1. `Platform.OS === 'ios'` 일 때만 진행 (웹/Android는 `false` 반환 후 스킵).
2. `Notifications.requestPermissionsAsync()` → 권한 거부 시 스킵.
3. `Notifications.getExpoPushTokenAsync()` → `ExponentPushToken[xxxx]` 문자열 획득.
4. `POST /firebase/user/update-fcm-token` body `{ fcm_token: pushToken }` 로 전송.

### 2.3 프론트 세팅 (필수)

- **패키지**: `expo-notifications` (이미 있음).
- **app.json (iOS)**  
  - `UIBackgroundModes`에 `"remote-notification"` 포함.  
  - Expo 프로젝트이면 `expo-notifications` 플러그인으로 빌드 시 자동 처리되는 경우 많음.
- **실기기**: 시뮬레이터는 푸시 토큰이 없거나 동작 불안정 → **실기기**에서 테스트 권장.
- **EAS / 개발 빌드**: 푸시용으로 빌드한 iOS 앱에서만 `getExpoPushTokenAsync()`가 정상 동작.

---

## 3. 백엔드 API

### 3.1 엔드포인트 (notification_app.py + firebase_app.py)

| 메서드 | 경로 | 설명 | 요청 | 응답 |
|--------|------|------|------|------|
| POST | `/firebase/user/update-fcm-token` | 푸시 토큰 저장 | JSON: `{ "fcm_token": "ExponentPushToken[...]" }` | `{ "status", "message" }` |
| POST | `/notification-push/update` | 알림 설정 저장 | Form: `is_notify`, `remind_time` (HH:MM) | `{ "status", "message" }` |
| GET | `/notification-push/me` | 내 알림 설정·토큰 등록 여부 | - | `email`, `is_notify`, `remind_time`, `fcm_token_registered`, `message` |
| POST | `/notification-push/test` | 테스트 푸시 1통 발송 | - | `{ "status", "message" }` |

- 모든 API는 **Bearer JWT** 필요 (`get_current_user`).
- 토큰 저장은 **ExponentPushToken 형식만 허용** (그 외는 400/에러 메시지).

### 3.2 토큰 저장 (firebase_app.py)

- `POST /firebase/user/update-fcm-token` 에서 `fcm_token` 수신.
- `_is_expo_push_token(token)` 으로 `ExponentPushToken[` 로 시작하는지 검사.
- 통과 시 `users.fcm_token` 업데이트; 실패 시 `"Expo 푸시 토큰(ExponentPushToken)만 등록 가능합니다."` 반환.

---

## 4. 발송 로직 (notification_service.py)

### 4.1 테스트 푸시

1. `notification_app.send_test_notification`: 로그인 유저의 `fcm_token` 조회.
2. `send_push_notification(token, title, body)` 호출.
3. `send_push_notification`: ExponentPushToken이 아니면 스킵(False). 맞으면 `send_expo_notification()` 호출.
4. `send_expo_notification`: `POST https://exp.host/--/api/v2/push/send` 로 `to`, `title`, `body`, `sound` 전송.

### 4.2 스케줄 복습 알림

- **주기**: APScheduler **5분마다** (`main.py` cron `minute="*/5"`).
- **함수**: `check_and_send_reminders()` (KST 기준).
- **조건**  
  - `users.is_notify == true`  
  - `users.remind_time` 이 현재 시각(KST, 분 단위)과 일치  
- **동작**: 대상 유저마다 `send_push_notification()` 발송. 중복 날짜 제한 없음(같은 날 여러 번 받을 수 있음).

### 4.3 Expo Push API

- **URL**: `https://exp.host/--/api/v2/push/send`
- **인증**: 별도 API 키 없이 요청 가능 (Expo 공개 API).
- **payload**: `{ "to": "<ExponentPushToken>", "title": "...", "body": "...", "sound": "default" }`.

---

## 5. DB (Supabase `users` 테이블)

필요 컬럼:

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `fcm_token` | text | Expo 푸시 토큰 (ExponentPushToken). iOS만 등록됨. |
| `is_notify` | boolean | 복습 알림 on/off. |
| `remind_time` | time / text | 복습 알림 시간 (HH:MM 또는 PostgreSQL time). KST 기준으로 비교. |
| `remind_sent_at` | date | (미사용) 예전에는 같은 날 중복 방지용이었으나, 현재는 사용하지 않음. 하루 두 번 등 여러 번 받을 수 있음. |

---

## 6. 환경 변수 (백엔드)

| 변수 | 설명 |
|------|------|
| `NOTIFICATION_SIMULATE` | `1` 또는 `true` 이면 실제 발송/DB 갱신 없이 스케줄 로직만 실행 (테스트용). |

- Firebase Admin / FCM 설정은 **사용하지 않음** (Expo Push API만 사용).

---

## 7. 세팅 체크리스트

### 프론트 (iOS)

- [ ] `expo-notifications` 설치됨.
- [ ] app.json iOS에 `UIBackgroundModes` 에 `remote-notification` 포함 (또는 expo-notifications 플러그인으로 처리).
- [ ] 실기기에서 빌드·실행 (시뮬레이터 비권장).
- [ ] 로그인 후 홈 또는 알림 설정 화면 진입 시 `registerAndSyncPushToken` 호출됨 (App.tsx, AlarmSettingScreen).

### 백엔드

- [ ] Supabase `users` 에 `fcm_token`, `is_notify`, `remind_time` 존재.
- [ ] `remind_sent_at` 는 사용하지 않음 (중복 제한 없이 설정한 시간마다 발송).
- [ ] `main.py` 에서 APScheduler로 5분마다 `check_and_send_reminders` 등록됨.
- [ ] 테스트 시에는 `NOTIFICATION_SIMULATE=1` 로 스케줄만 검증 가능.

### 동작 확인

1. **토큰 등록**: iOS 앱 로그인 → 홈 진입 → 백엔드 로그에 `[토큰 저장] email=... Expo 푸시 토큰` 확인.
2. **설정 저장**: 알림 설정 화면에서 on/off·시간 변경 → `/notification-push/update` 성공 응답.
3. **테스트 푸시**: "테스트 알림 받기" → 기기에서 알림 수신 여부 확인.
4. **스케줄**: 서버 로그에서 `[알림] ========== 스케줄 실행` 및 대상자·발송 결과 확인.

---

## 8. 트러블슈팅

- **푸시가 안 옴**  
  - DB에 해당 유저 `fcm_token` 이 ExponentPushToken 문자열로 저장돼 있는지 확인.  
  - 백엔드 로그에서 `[Expo] 푸시 실패` / `[Push] ❌ ExponentPushToken이 아님` 여부 확인.  
  - iOS 실기기, 알림 권한 허용, 앱이 Expo 푸시용으로 빌드된 것인지 확인.

- **토큰 저장이 거부됨**  
  - `firebase_app` 에서 ExponentPushToken이 아닌 값은 거부. 프론트가 iOS에서만 `getExpoPushTokenAsync()` 결과를 보내는지 확인.

- **스케줄이 안 돌아감**  
  - `main.py` startup 에서 스케줄러가 시작되는지, 로그에 `알림 스케줄러 시작` 이 나오는지 확인.  
  - `NOTIFICATION_SIMULATE=1` 이면 실제 발송은 하지 않고 로그만 출력.

- **같은 날 여러 번 알림을 받고 싶은 경우**  
  - 현재는 중복 제한 없이, 스케줄이 돌 때마다 `remind_time`이 맞으면 발송됨 (5분마다 체크이므로 설정한 정각에 1회 발송). 다른 시간대에 추가로 받으려면 remind_time을 바꾸거나, 추후 여러 시간대 지원 시 활용 가능.

---

## 9. 파일 매핑

| 구분 | 파일 | 역할 |
|------|------|------|
| 프론트 | `front/src/api/notification.ts` | 토큰 발급·전송, 알림 설정 API 호출, 테스트 푸시 요청 |
| 프론트 | `front/App.tsx` | 홈 진입 시 `registerAndSyncPushToken` 호출 |
| 프론트 | `front/src/screens/alarm/AlarmSettingScreen.tsx` | 알림 설정 UI, 설정 저장, 테스트 푸시, 진입 시 토큰 재등록 |
| 백엔드 | `python/app/notification_app.py` | `/notification-push/*` 라우트, 테스트 푸시 진입점 |
| 백엔드 | `python/app/firebase_app.py` | `/firebase/user/update-fcm-token` 토큰 저장 (Expo 전용 검증) |
| 백엔드 | `python/service/notification_service.py` | Expo Push 발송, remind_time 정규화, 스케줄 대상 조회·발송 |
| 백엔드 | `python/main.py` | APScheduler 등록 (5분마다 `check_and_send_reminders`) |

이 문서는 위 파일들의 현재 구현을 기준으로 정리했습니다. 토큰 형식이나 API가 바뀌면 이 문서도 함께 수정하는 것을 권장합니다.
