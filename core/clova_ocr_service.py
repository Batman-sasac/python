import requests
import uuid
import time
import json
import re
import os
from openai import OpenAI
import io  
from pdf2image import convert_from_bytes 

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
        """네이버 클로바 OCR을 사용하여 페이지별로 텍스트 추출"""
        pages_text = []
        
        try:
            # 파일 확장자 확인
            file_ext = filename.split('.')[-1].lower() if '.' in filename else 'jpg'
            
            # 클로바 OCR 요청 데이터 구성
            request_json = {
                'images': [{'format': file_ext, 'name': 'ocr_request'}],
                'requestId': str(uuid.uuid4()),
                'version': 'V2',
                'timestamp': int(round(time.time() * 1000))
            }

            headers = {'X-OCR-SECRET': self.clova_secret}
            payload = {'message': json.dumps(request_json)}
            files = [('file', (filename, file_bytes, 'application/octet-stream'))]

            # 클로바 API 호출
            response = requests.post(
                self.clova_url, 
                headers=headers, 
                data=payload, 
                files=files,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # [핵심] 클로바는 PDF의 각 페이지를 'images' 리스트의 개별 요소로 반환합니다.
                for image in result.get('images', []):
                    fields = image.get('fields', [])
                    if not fields:
                        pages_text.append("") # 텍스트 없는 페이지 처리
                        continue

                    # 한 페이지 내의 단어들을 줄바꿈을 살려 합치기
                    full_text = ""
                    # 첫 번째 필드의 y좌표를 기준으로 첫 줄 시작
                    last_y = fields[0]['boundingPoly']['vertices'][0]['y']
                    line_text = []

                    for field in fields:
                        current_y = field['boundingPoly']['vertices'][0]['y']
                        text = field.get('inferText', '')
                        
                        # y좌표 차이가 15보다 크면 줄바꿈(엔터) 처리
                        if abs(current_y - last_y) > 15:
                            full_text += " ".join(line_text) + "\n"
                            line_text = [text]
                            last_y = current_y
                        else:
                            # 같은 줄이면 공백으로 연결
                            line_text.append(text)
                    
                    # 마지막 줄까지 합쳐서 텍스트 완성
                    full_text += " ".join(line_text)
                    
                    # 완성된 한 페이지의 텍스트를 리스트에 담기
                    pages_text.append(full_text)
                    print(f"✅ {len(pages_text)}페이지 추출 완료")

                # 모든 페이지가 담긴 리스트 반환: ["1쪽 내용", "2쪽 내용", ...]
                return pages_text
            else:
                print(f"❌ Clova API 에러: {response.status_code}, {response.text}")
                return None

        except Exception as e:
            print(f"❌ OCR 처리 중 예외 발생: {e}")
            return None
    
    def process_file(self, file_bytes, filename):
        """텍스트 추출 및 페이지별 GPT 키워드 추출 실행"""
        
        # 1. OCR 텍스트 추출 (리스트 형태로 받음)
        all_pages_text = self.extract_text_with_clova(file_bytes, filename)
        
        if not all_pages_text:
            return {"status": "error", "message": "OCR 텍스트를 추출하지 못했습니다."}

        pages_keywords = []

        # 2. 각 페이지별로 루프를 돌며 키워드 추출
        for i, page_text in enumerate(all_pages_text):
            try:
                response = self.gpt_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system", 
                            "content": (
                                "제공된 텍스트에서 학습에 필요한 핵심 명사만 추출하세요.\n"
                                "1. '명사'만 추출하세요.\n"
                                "2. 숫자나 중요한 고유명사도 포함하세요.\n"
                                "3. 반드시 ['단어1', '단어2'] 형태의 JSON 배열로만 답변하세요."
                            )
                        },
                        {
                            "role": "user", 
                            "content": f"다음 텍스트에서 명사 키워드만 뽑아줘:\n\n{page_text}"
                        }
                    ],
                    temperature=0
                )
                
                content = response.choices[0].message.content.strip()
                match = re.search(r'\[.*\]', content, re.DOTALL)
                
                if match:
                    json_str = match.group().replace("'", '"')
                    keywords = json.loads(json_str)
                else:
                    keywords = []

                pages_keywords.append(keywords)

            except Exception as e:
                print(f"페이지 {i+1} GPT 에러: {e}")
                pages_keywords.append([]) 

        # 3. 최종 결과 반환
        return {
            "status": "success",
            "pages": all_pages_text,
            "pages_keywords": pages_keywords,
            "original_text": all_pages_text[0] if all_pages_text else "",
            "keywords": pages_keywords[0] if pages_keywords else []
        }