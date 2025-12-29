from datetime import datetime

# DB 연동 대신 클래스로 대체
class User:
    def __init__(self, id, social_id, nickname, email, points=0):
        self.id = id
        self.social_id = social_id
        self.nickname = nickname
        self.email = email
        self.points = points
        self.created_at = datetime.utcnow()

    def __repr__(self):
        return f'<User {self.nickname}>'

class RewardHistory:
    def __init__(self, id, user_id, change_amount, reason):
        self.id = id
        self.user_id = user_id
        self.change_amount = change_amount
        self.reason = reason
        self.created_at = datetime.utcnow()

# --- 더미 데이터 리스트 (이게 실제 DB 역할을 합니다) ---

dummy_users = [
    User(1, "naver_12345", "김철수", "chulsoo@naver.com", 1500),
    User(2, "kakao_67890", "이영희", "younghee@kakao.com", 500)
]

dummy_rewards = [
    RewardHistory(1, 1, 1000, "신규 가입 축하 포인트"),
    RewardHistory(2, 1, 500, "OCR 학습 완료 리워드"),
    RewardHistory(3, 2, 500, "신규 가입 축하 포인트")
]