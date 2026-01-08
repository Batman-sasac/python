import os
import json
import re
from google.cloud import vision
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class GPTService:
    def __init__(self, api_key):
        # 환경 변수에 이미 설정된 GOOGLE_APPLICATION_CREDENTIALS 사용
        self.vision_client = vision.ImageAnnotatorClient()
        self.gpt_client = OpenAI(api_key=api_key)
        self.model = "gpt-4o"

    def extract_text_with_google(self, image_bytes):
        """Google OCR 텍스트 추출 (원본 보존용)"""
        try:
            image = vision.Image(content=image_bytes)
            response = self.vision_client.text_detection(image=image)
            
            if response.error.message:
                print(f"Google API Error: {response.error.message}")
                return ""
            
            texts = response.text_annotations
            # texts[0].description이 이미지 전체 텍스트 원본입니다.
            return texts[0].description if texts else ""
        except Exception as e:
            print(f"OCR Error: {e}")
            return ""

    def process_file(self, file_bytes, filename):
        """본문은 Google OCR 원본 그대로, 키워드는 GPT가 명사만 추출"""
        # 1. Google OCR로 전체 텍스트 추출 (프론트에 그대로 보여줄 용도)
        raw_text = self.extract_text_with_google(file_bytes)
        
        if not raw_text:
            return {"status": "error", "message": "텍스트를 추출하지 못했습니다."}

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
                temperature=0 # 일관성을 위해 0으로 설정
            )
            
            content = response.choices[0].message.content.strip()
            
            # JSON 파싱 보정
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                keywords = json.loads(match.group().replace("'", '"'))
            else:
                keywords = []

            # [핵심] raw_text는 Google 추출본 그대로, keywords는 GPT 추출본을 반환
            return {
                "status": "success",
                "original_text": raw_text, 
                "keywords": keywords
            }
        except Exception as e:
            print(f"GPT Error: {e}")
            return {"status": "error", "message": "키워드 추출 중 오류 발생"}