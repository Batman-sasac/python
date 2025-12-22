from flask import Flask, request, render_template
import os
import uuid
from dotenv import load_dotenv
from core.vision_service import detect_text_from_image, async_detect_document_text


load_dotenv()
app = Flask(__name__)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'tiff'}
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/extrackted_text', methods=['GET', 'POST'])
def upload_file():
    extracted_text = None
    
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            file_ext = file.filename.rsplit('.', 1)[1].lower()
            
            try:
                if file_ext in ['pdf']:
                    # PDF 처리 (GCS 업로드 없이 바로 함수 호출)
                    extracted_text = async_detect_document_text(file)
                else:
                    # 이미지 처리
                    file_content = file.read()
                    extracted_text = detect_text_from_image(file_content)
            except Exception as e:
                extracted_text = f"오류 발생: {e}"
        
    return render_template('index.html', extracted_text=extracted_text)
    

if __name__ == '__main__':
    # Flask 앱 실행
    # (실제 환경에서는 gunicorn 등 WSGI 서버 사용 권장)
    app.run(debug=True, use_reloader=False)