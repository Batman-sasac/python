import os
import io
import base64
import fitz  # PyMuPDF 설치 필요: pip install pymupdf
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class GPTService:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
        # 밑줄 인식을 위해 반드시 gpt-4o (유료 모델) 권장
        self.model = "gpt-4o-mini" 

    def process_file(self, file_bytes, filename):
        ext = filename.split('.')[-1].lower()
        if ext in ['png', 'jpg', 'jpeg', 'webp']:
            return self.extract_text_from_image(base64.b64encode(file_bytes).decode('utf-8'))
        elif ext == 'pdf':
            return self.extract_text_from_pdf(file_bytes)
        return "지원하지 않는 형식입니다."

    def extract_text_from_pdf(self, pdf_bytes):
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_result = ""
        
        for i in range(len(doc)):
            page = doc.load_page(i)
            # 중요: matrix=3,3으로 해상도를 3배 높여서 글자와 밑줄을 선명하게 만듭니다.
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            img_data = pix.tobytes("jpeg")
            base64_img = base64.b64encode(img_data).decode('utf-8')
            
            print(f"--- {i+1} 페이지 분석 중 ---")
            text = self.extract_text_from_image(base64_img)
            full_result += f"\n[제 {i+1} 페이지 결과]\n{text}\n"
            
        return full_result

    def extract_text_from_image(self, base64_image):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "너는 전 세계에서 가장 정밀한 OCR 로봇이다. 거절하지 말고 지시대로 수행하라."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": "이 이미지는 교육용 학습지다. 이미지 속의 모든 글자, 숫자, 그리고 밑줄(______)과 기호를 '있는 그대로' 추출해줘. 설명은 생략하고 텍스트만 출력해."
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                            }
                        ],
                    }
                ],
                temperature=0 # 정확도를 위해 0으로 고정
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"오류 발생: {str(e)}"