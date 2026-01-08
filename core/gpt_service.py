"""


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
        self.model = "gpt-4o" 

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
            base64_image = f"data:image/jpeg;base64,{base64_image}"
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 전문 문서 전사 전문가입니다. 모든 텍스트를 누락 없이 디지털화하여 가독성을 높이는 것이 목적입니다. 윤리 가이드라인을 준수하며, 이미지 내의 텍스트 정보만을 충실히 추출합니다."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": """ """이 학습지 이미지를 텍스트로 변환해 주세요.
                            
1. [전사 우선]: 이미지의 모든 텍스트를 한 줄도 빠짐없이 그대로 적어라.
2. [선택적 강조]: 전사한 텍스트 중 아래 조건에 맞는 단어만 **단어** 형식을 적용하라.
   - 대상: 학술 용어, 고유 명사, 핵심 숫자, 개념어 (예: **광합성**, **조선시대**, **100도**)
   - 제외: '-하기', '-기', '-는 것'으로 끝나는 동사형 단어, 조사, 어미
3. [누락 방지]: 텍스트가 많더라도 절대 '요약'하거나 '생략'하지 마라. 끝까지 출력하는 것이 가장 중요하다.""" """
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": base64_image,
                                "detail": "high"
                            }
                            }
                        ],
                    }
                ],
                temperature=0, # 정확도를 위해 0으로 고정
                max_tokens=8129
            )
            # finish_reason 추출
            finish_reason = response.choices[0].finish_reason
            print(f"--- 분석 종료 사유: {finish_reason} ---")

            # 사유에 따른 분기 처리
            if finish_reason == "length":
                print("경고: 토큰 제한 때문에 텍스트가 잘렸습니다. max_tokens를 늘리거나 내용을 분할하세요.")
            elif finish_reason == "content_filter":
                print("경고: 안전 정책(민감 콘텐츠)으로 인해 내용이 차단되었습니다.")
            elif finish_reason == "stop":
                print("정상적으로 모든 내용을 추출했습니다.")

            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI API 상세 에러: {e}")
            return f"오류 발생: {str(e)}"

            """



import os
import io
from google.cloud import vision
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class GPTService:
    def __init__(self, api_key):
        # .env에서 파일 경로를 읽어 시스템 환경 변수에 설정
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if key_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

        # 이제 인자 없이 생성해도 라이브러리가 환경 변수의 경로를 스스로 읽습니다.
        self.vision_client = vision.ImageAnnotatorClient()
        
        self.gpt_client = OpenAI(api_key=api_key)
        self.api_key = api_key
        self.model = "gpt-4o"

    def extract_text_with_google(self, image_bytes):
        """이미지에서 텍스트 추출"""
        try:
            image = vision.Image(content=image_bytes)
            response = self.vision_client.text_detection(image=image)
            
            if response.error.message:
                print(f"Google API 에러: {response.error.message}")
                return ""
                
            texts = response.text_annotations
            return texts[0].description if texts else ""
        except Exception as e:
            print(f"OCR 분석 중 오류: {e}")
            return ""



    def format_with_gpt(self, raw_text):
        """2단계: 추출된 텍스트를 GPT에게 전달하여 볼드체 및 줄맞춤 처리"""
        try:
            response = self.gpt_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 텍스트 정돈 전문가입니다. 입력받은 텍스트의 내용을 바꾸지 말고 가독성 좋게 정리하세요."
                    },
                    {
                        "role": "user",
                        "content": f"""아래 텍스트는 학습지에서 추출된 내용입니다. 다음 지침을 따르세요:

1. 오타가 있다면 문맥에 맞게 수정하고 줄바꿈을 정돈하세요.
2. 학습에 중요한 '핵심 명사, 용어, 숫자'에만 **단어**와 같이 볼드 처리를 하세요.
3. '-하기', '-읽기' 등 동사형 단어와 조사는 강조하지 마세요.
4. 모든 내용을 빠짐없이 출력하세요.

텍스트:
{raw_text}"""
                    }
                ],
                temperature=0
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"GPT 처리 중 오류: {e}\n내용:\n{raw_text}"

    def process_file(self, file_bytes, filename):
        """서버(ocr_app.py)에서 호출하는 진입점 함수"""
        ext = filename.split('.')[-1].lower()
        
        # 1. 이미지 파일 처리
        if ext in ['png', 'jpg', 'jpeg', 'webp']:
            print(f"--- 이미지 분석 시작 ({filename}) ---")
            # extract_text_with_google 함수를 호출 (image_bytes 전달)
            raw_text = self.extract_text_with_google(file_bytes)
            
            if not raw_text:
                return "텍스트를 추출하지 못했습니다."
            
            # GPT로 다듬기
            return self.format_with_gpt(raw_text)
            
        # 2. PDF 파일 처리 (선택 사항: 필요 없다면 에러 메시지 반환)
        elif ext == 'pdf':
            return "현재 이미지 분석만 지원합니다. (PDF는 추후 업데이트 예정)"
            
        return "지원하지 않는 파일 형식입니다."