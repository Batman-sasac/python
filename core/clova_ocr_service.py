import requests
import uuid
import time
import json
import re
import os
from openai import OpenAI

class CLOVAOCRService:
    def __init__(self, api_key):
        self.api_key = api_key
        # OpenAI 클라이언트 초기화
        self.gpt_client = OpenAI(api_key=api_key) 
        self.model = "gpt-4o" 
        
        # 네이버 클로바 설정 (환경변수)
        self.clova_url = os.getenv("CLOVA_OCR_URL")
        self.clova_secret = os.getenv("CLOVA_OCR_SECRET")

    def extract_text_with_clova(self, file_bytes, filename):
        """네이버 클로바 OCR을 사용하여 텍스트 추출"""
        try:
            request_json = {
                'images': [
                    {
                        'format': filename.split('.')[-1] if '.' in filename else 'jpg',
                        'name': 'ocr_request'
                    }
                ],
                'requestId': str(uuid.uuid4()),
                'version': 'V2',
                'timestamp': int(round(time.time() * 1000))
            }

            headers = {
                'X-OCR-SECRET': self.clova_secret
            }
            
            payload = {'message': json.dumps(request_json)}
            files = [('file', (filename, file_bytes, 'application/octet-stream'))]

            response = requests.post(
                self.clova_url, 
                headers=headers, 
                data=payload, 
                files=files,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                ocr_texts = []
                for image in result.get('images', []):
                    for field in image.get('fields', []):
                        ocr_texts.append(field.get('inferText', ''))
                return " ".join(ocr_texts)
            else:
                print(f"Clova API Error: {response.text}")
                return None
        except Exception as e:
            print(f"Clova Connection Error: {e}")
            return None

    def process_file(self, file_bytes, filename):
        """본문은 네이버 클로바 OCR 원본, 키워드는 GPT가 명사만 추출"""
        
        # 1. 네이버 클로바 OCR로 전체 텍스트 추출
        raw_text = self.extract_text_with_clova(file_bytes, filename)
        
        if not raw_text:
            return {"status": "error", "message": "OCR 텍스트를 추출하지 못했습니다."}

        # 2. GPT에게 명사 키워드만 추출 요청
        try:
            response = self.gpt_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": (
                            "제공된 텍스트에서 학습에 필요한 핵심 명사만 추출하세요.\n"
                            "1. 조사, 어미, 형용사, 동사는 제외하고 '명사'만 추출하세요.\n"
                            "2. 숫자나 중요한 고유명사도 포함하세요.\n"
                            "3. 반드시 ['단어1', '단어2'] 형태의 JSON 배열로만 답변하세요."
                        )
                    },
                    {
                        "role": "user", 
                        "content": f"다음 텍스트에서 명사 키워드만 뽑아줘:\n\n{raw_text}"
                    }
                ],
                temperature=0
            )
            
            content = response.choices[0].message.content.strip()
            
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                clean_json = match.group().replace("'", '"')
                keywords = json.loads(clean_json)
            else:
                keywords = []

            return {
                "status": "success",
                "original_text": raw_text, 
                "keywords": keywords
            }
        except Exception as e:
            print(f"GPT 상세 에러: {e}")
            return {"status": "error", "message": f"키워드 추출 중 오류 발생: {str(e)}"}