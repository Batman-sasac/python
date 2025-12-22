import easyocr
import numpy as np
from PIL import Image
import io
from pdf2image import convert_from_bytes

# Reader 초기화 (한 번만 로드)
reader = easyocr.Reader(['ko', 'en'])

def detect_text_from_image(file_content):
    """이미지 처리 함수 (main.py의 이름에 맞춤)"""
    try:
        print("-> 이미지 처리 중...")
        image = Image.open(io.BytesIO(file_content))
        image_np = np.array(image)
        result = reader.readtext(image_np, detail=0)
        return "\n".join(result)
    except Exception as e:
        return f"이미지 추출 오류: {str(e)}"

def async_detect_document_text(file_object):
    """PDF 처리 함수 (main.py의 이름에 맞춤)"""
    try:
        print("-> PDF를 이미지로 변환하여 처리 중...")
        # file_object.read()를 통해 바이트 데이터를 가져옵니다.
        # Windows의 경우 poppler_path가 필요할 수 있습니다.
        pages = convert_from_bytes(file_object.read())
        
        full_text = []
        for i, page in enumerate(pages):
            image_np = np.array(page)
            result = reader.readtext(image_np, detail=0)
            full_text.append(f"--- {i+1} 페이지 ---\n" + "\n".join(result))
            
        return "\n\n".join(full_text)
    except Exception as e:
        return f"PDF 추출 중 오류 발생: {str(e)}\n(Poppler 설치 여부를 확인하세요)"