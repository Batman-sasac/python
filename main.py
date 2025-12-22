from flask import Flask, request, render_template
import os
import uuid
from dotenv import load_dotenv
from core.vision_service import detect_text_from_image, async_detect_document_text
from service.study_service import study_service

load_dotenv()
app = Flask(__name__)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'tiff'}
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')


current_extracted_text = ""

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    global current_extracted_text
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

                    # 3. 추출된 값을 전역 변수에 저장
                current_extracted_text = extracted_text
                return render_template('index.html', extracted_text=extracted_text)

            except Exception as e:
                extracted_text = f"오류 발생: {e}"
        
    return render_template('index.html')
    

@app.route('/save_blank', methods=['POST'])
def save_blank():
    data = request.get_json()
    blank_word = data.get('blank_word')
    
    # [중요] 'default'라는 ID로 단어를 저장합니다.
    study_service.save_blank_word('default', blank_word)
    return {"status": "success"}

@app.route('/study')
def study_page():
    global current_extracted_text
    
    if not current_extracted_text:
        return "추출된 텍스트가 없습니다. 먼저 텍스트를 추출하세요."

    # [중요] 저장할 때 썼던 'default' ID를 똑같이 사용하여 빈칸을 만듭니다.
    processed_text = study_service.make_blank_text(current_extracted_text, 'default')
    
    # 렌더링 시 처리된 텍스트를 보냅니다.
    return render_template('study.html', processed_text=processed_text)

@app.route('/check_answer', methods=['POST'])
def check_answer():
    user_answers = request.form.getlist('answers') # 사용자가 입력한 정답들
    results = []
    
    for i, user_ans in enumerate(user_answers):
        correct_ans = db_blanks[i]
        if user_ans.strip() == correct_ans.strip():
            results.append({"correct": True, "answer": correct_ans})
            print("정답:{}", results)
        else:
            results.append({"correct": False, "answer": correct_ans})
            

    return render_template('result.html', results=results)

if __name__ == '__main__':
    # Flask 앱 실행
    # (실제 환경에서는 gunicorn 등 WSGI 서버 사용 권장)
    app.run(debug=True, use_reloader=False)