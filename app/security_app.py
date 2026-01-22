import os
import jwt
from datetime import datetime, timedelta

def create_jwt_token(email: str, social_id: str) -> str:
    secret_key = os.getenv("JWT_SECRET_KEY", "default_secret")
    payload = {
        "email": email,
        "social_id": social_id,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")