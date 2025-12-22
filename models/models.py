from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    social_id = db.Column(db.String(100), unique=True, nullable=False) # 네이버/카카오 고유 ID
    nickname = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120))
    points = db.Column(db.Integer, default=0) # 리워드 포인트
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.nickname}>'

class RewardHistory(db.Model):
    __tablename__ = 'reward_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    change_amount = db.Column(db.Integer, nullable=False) 
    reason = db.Column(db.String(200)) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)