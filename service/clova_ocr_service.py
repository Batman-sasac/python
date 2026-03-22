import requests
import uuid
import time
import json
import re
import os
from openai import OpenAI
import io  
from pdf2image import convert_from_bytes 
from pypdf import PdfReader

class CLOVAOCRService:
    def __init__(self, api_key):
        self.api_key = api_key
        # OpenAI 클라이언트 초기화
        self.gpt_client = OpenAI(api_key=api_key) 
        self.model = "gpt-4o" 
        
        # 네이버 클로바 설정 (환경변수)
        self.clova_url = os.getenv("CLOVA_OCR_URL")
        self.clova_secret = os.getenv("CLOVA_OCR_SECRET")

    
    def get_estimation_message(self, files_data, secret_key):
        """
        [Service]
        - 입력: [{'filename': '...', 'bytes': b'...'}, ...]
        - 로직: PDF(40초/장), 이미지(30초/장) 합산
        """

        print(f"사용 중인 키: {self.clova_secret}")
        total_seconds = 0

        for file in files_data:
            filename = file.get('filename', '')
            file_bytes = file.get('bytes', b'')
            file_ext = filename.split('.')[-1].lower()

            if file_ext == 'pdf':
                try:
                    reader = PdfReader(io.BytesIO(file_bytes), strict=False)
                    pages = len(reader.pages)
                    # PDF: 페이지당 40초
                    total_seconds += (max(pages, 1) * 40)
                except Exception:
                    total_seconds += 40
            else:
                # 이미지(jpg, png 등): 장당 30초
                total_seconds += 30

        minutes = total_seconds // 60
        seconds = total_seconds % 60
        
        if minutes > 0:
            return f"약 {minutes}분 {seconds}초 소요 예정"
        return f"약 {seconds}초 소요 예정"
    
    
    
    def extract_text_with_clova(self, file_bytes, filename):
        """네이버 클로바 OCR을 사용하여 페이지별로 텍스트 추출.
        file_bytes: 원본 또는 ocr_app에서 crop된 잘린 이미지 bytes (좌표 적용 후 넘어옴).
        """
        pages_text = []
        
        try:
            # 파일 확장자 확인
            raw_ext = filename.split('.')[-1].lower() if '.' in filename else 'jpg'
            

                # 2. 클로바가 선호하는 포맷으로 매핑 (jpeg -> jpg)
            if raw_ext in ['jpg', 'jpeg', 'jpe']:
                file_ext = 'jpg'
            elif raw_ext == 'png':
                file_ext = 'png'
            elif raw_ext == 'pdf':
                file_ext = 'pdf'
            elif raw_ext in ['tiff', 'tif']:
                file_ext = 'tiff'
            else:
                file_ext = 'jpg'  # 알 수 없는 경우 기본값 jpg


            # 클로바 OCR 요청 데이터 구성 (lang은 message 최상위, 공식값: ko/ja/zh-TW)
            request_json = {
                'version': 'V2',
                'requestId': str(uuid.uuid4()),
                'timestamp': int(round(time.time() * 1000)),
                'lang': 'ko',
                'images': [{'format': file_ext, 'name': 'ocr_request'}],
                'enableTableDetection': True,
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
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # [핵심] 클로바는 PDF의 각 페이지를 'images' 리스트의 개별 요소로 반환합니다.
                for image in result.get('images', []):
                    fields = image.get('fields', [])
                    if not fields:
                        pages_text.append("")
                        continue

                    # --- [정렬 로직 시작] ---
                    # 1. 모든 필드를 Y좌표 기준으로 먼저 정렬 (위 -> 아래)
                    fields.sort(key=lambda x: x['boundingPoly']['vertices'][0]['y'])

                    lines = []
                    current_line = []
                    # 첫 줄의 기준 Y좌표 설정
                    last_y = fields[0]['boundingPoly']['vertices'][0]['y']

                    for field in fields:
                        current_y = field['boundingPoly']['vertices'][0]['y']
                        
                        # Y좌표 차이가 15보다 크면 새로운 줄로 간주
                        if abs(current_y - last_y) > 15:
                            # 이전 줄이 완성되었으므로 X좌표로 정렬 (왼쪽 -> 오른쪽)
                            current_line.sort(key=lambda x: x['boundingPoly']['vertices'][0]['x'])
                            lines.append(current_line)
                            
                            current_line = [field]
                            last_y = current_y
                        else:
                            current_line.append(field)
                    
                    # 마지막 줄 처리
                    current_line.sort(key=lambda x: x['boundingPoly']['vertices'][0]['x'])
                    lines.append(current_line)

                    # 2. 정렬된 줄들을 하나의 텍스트로 합치기
                    full_page_text = ""
                    for line in lines:
                        line_text = " ".join([f.get('inferText', '') for f in line])
                        full_page_text += line_text + "\n"

                    pages_text.append(full_page_text.strip())
                    print(f"✅ {len(pages_text)}페이지 추출 및 정렬 완료")
                    # --- [정렬 로직 끝] ---

                return pages_text
            else:
                print(f"❌ Clova API 에러: {response.status_code}, {response.text}")
                return None
        except Exception as e:
            print(f"❌ OCR 처리 중 예외 발생: {e}")
            return None


    
    def process_file(self, file_bytes, filename):
        """텍스트 추출 및 페이지별 GPT 키워드 추출 실행.
        file_bytes: ocr_app에서 전달 — crop 적용 시 잘린 이미지 bytes만 넘어옴.
        """
        total_start = time.time()
        # 1. OCR 텍스트 추출 (전달받은 이미지 = 원본 또는 잘린 영역만)
        all_pages_text = self.extract_text_with_clova(file_bytes, filename)
        

        gpt_start = time.time()

        if not all_pages_text:
            return {"status": "error", "message": "OCR 텍스트를 추출하지 못했습니다."}

        all_keywords = []

        # 2. 각 페이지별로 루프를 돌며 키워드 추출
        for i, page_text in enumerate(all_pages_text):
            try:
                response = self.gpt_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system", 
                            "content": (
                                "제공된 텍스트에서 학습에 필요한 핵심 단어(명사)만 추출하세요.\n"
                                "1. 한글 명사와 영어 단어(명사) 모두 추출하세요. 텍스트에 영어가 있으면 영어 단어도 반드시 포함하세요.\n"
                                "2. 숫자나 중요한 고유명사도 포함하세요.\n"
                                "3. 반드시 ['단어1', '단어2'] 형태의 JSON 배열로만 답변하세요.\n"
                                "4. 조사, 형용사는 제외하고 명사만 포함하세요."
                            )
                        },
                        {
                            "role": "user", 
                            "content": f"다음 텍스트에서 한글 명사와 영어 단어를 모두 포함해 키워드만 뽑아줘:\n\n{page_text}"
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

                all_keywords.append(keywords)

            except Exception as e:
                print(f"페이지 {i+1} GPT 에러: {e}")
                all_keywords.append([]) 

        gpt_duration = time.time() - gpt_start
        print(f"⏱️ [GPT 키워드 추출 소요 시간]: {gpt_duration:.2f}초")
        
        total_duration = time.time() - total_start
        page_count = len(all_pages_text)
        print(f"🚀 [전체 프로세스 총 소요 시간]: {total_duration:.2f}초, 페이지 수: {page_count}")
        # 3. 최종 결과 반환
        # 프론트(`front/src/api/ocr.ts`)는 다음 우선순위로 데이터를 사용:
        # 1) inner.pages가 배열이면 각 페이지의 original_text/keywords를 합쳐 사용
        # 2) 그렇지 않으면 original_text, keywords 단일 필드를 사용 (하위 호환)
        #
        # 여기서는 멀티 페이지를 정식 지원하기 위해 pages 배열을 내려준다.
        return {
            "status": "success",
            "pages": [
                {
                    "original_text": text,
                    "keywords": keywords,
                }
                for text, keywords in zip(all_pages_text, all_keywords)
            ],
            "page_count": page_count,
            "total_duration": total_duration,
        }
