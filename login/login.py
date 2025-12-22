import os
from flask import Flask, url_for, session, redirect
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

app = Flask(__name__)
# 세션 유지를 위한 암호화 키 (보안 중요)
app.secret_key = os.getenv('SECRET_KEY', 'your-fallback-secret-key')

# OAuth 설정
oauth = OAuth(app)

# 카카오 등록
oauth.register(
    name='kakao',
    client_id=os.getenv('KAKAO_CLIENT_ID'),
    client_secret=os.getenv('KAKAO_CLIENT_SECRET'),
    access_token_url='https://kauth.kakao.com/oauth/token',
    authorize_url='https://kauth.kakao.com/oauth/authorize',
    api_base_url='https://kapi.kakao.com/v2/',
    client_kwargs={'scope': 'profile_nickname account_email'},
)

# 네이버 등록
oauth.register(
    name='naver',
    client_id=os.getenv('NAVER_CLIENT_ID'),
    client_secret=os.getenv('NAVER_CLIENT_SECRET'),
    access_token_url='https://nid.naver.com/oauth2.0/token',
    authorize_url='https://nid.naver.com/oauth2.0/authorize',
    api_base_url='https://openapi.naver.com/v1/',
)

@app.route('/')
def index():
    user = session.get('user')
    if user:
        return f'안녕하세요, {user["nickname"]}님! <a href="/logout">로그아웃</a>'
    return '<a href="/login/kakao">카카오 로그인</a> | <a href="/login/naver">네이버 로그인</a>'

@app.route('/login/<name>')
def login(name):
    client = oauth.create_client(name)
    # 실제 배포 시에는 _external=True가 필수입니다.
    redirect_uri = url_for('auth', name=name, _external=True)
    return client.authorize_redirect(redirect_uri)

@app.route('/auth/<name>')
def auth(name):
    client = oauth.create_client(name)
    token = client.authorize_access_token()
    
    if name == 'kakao':
        resp = client.get('user/me')
        profile = resp.json()
        session['user'] = {'nickname': profile['properties']['nickname']}
    
    elif name == 'naver':
        resp = client.get('nid/me')
        profile = resp.json()
        session['user'] = {'nickname': profile['response']['nickname']}
        
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)