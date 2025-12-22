# 파일 업로드 및 GCS 연동 관련 작업처리

from google.cloud import storage
import os
import uuid
from dotenv import load_dotenv

load_dotenv()
storage_client = storage.Client()
BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')

def upload_file_to_gcs(file_object, destination_path):
    """
    업로드된 파일 객체를 GCS에 저장
    :param file_object: Flask의 request.files['file'] 객체
    :param destination_path: GCS에 저장될 경로 (예: pdf_uploads/uuid.pdf)
    :return: GCS URI (gs://bucket/path/file.pdf)
    """
    if not BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME 환경 변수가 설정되지 않았습니다.")
    
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(destination_path)
    
    # 파일 객체의 커서를 처음으로 되돌려 blob에 업로드
    file_object.seek(0)
    blob.upload_from_file(file_object)
    
    return f"gs://{BUCKET_NAME}/{destination_path}"