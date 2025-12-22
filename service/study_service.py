from models import db, StudyMaterial
import uuid

class StudyService:
    def save_material(self, user_id, original_text, blank_words, filename=None):
        """
        사용자가 추출한 텍스트와 선택한 빈칸 단어 리스트를 DB에 영구 저장합니다.
        """
        new_material = StudyMaterial(
            user_id=user_id,
            original_text=original_text,
            blank_words=blank_words,  # JSON 타입으로 ["단어1", "단어2"] 저장
            filename=filename
        )
        db.session.add(new_material)
        db.session.commit()
        return new_material.id

    def get_material_for_study(self, material_id):
        """
        DB에서 학습 자료를 불러와 저장된 단어들을 <input> 태그(빈칸)로 치환합니다.
        """
        material = StudyMaterial.query.get(material_id)
        if not material:
            return None

        processed_text = material.original_text
        # DB에 저장된 JSON 리스트(blank_words)를 순회하며 치환
        # 인덱스(i)를 사용하여 각 input의 name을 answer_0, answer_1로 구분합니다.
        for i, word in enumerate(material.blank_words):
            # 실제 입력 가능한 HTML input 태그 생성
            # style을 추가하여 이미지와 유사한 '밑줄 형태' 디자인을 적용합니다.
            blank_html = (
                f'<input type="text" name="answer_{i}" class="blank-input" '
                f'style="width:{len(word)*20}px;" autocomplete="off" placeholder="?">'
            )
            # 원본 텍스트에서 해당 단어를 1회만 치환 (중복 단어 대응)
            processed_text = processed_text.replace(word, blank_html, 1)
        
        return processed_text

    def check_answers_from_db(self, material_id, user_submitted_data):
        """
        DB에 저장된 정답 리스트와 사용자 입력값을 대소문자 구분 없이 비교합니다.
        """
        material = StudyMaterial.query.get(material_id)
        if not material:
            return None

        correct_words = material.blank_words
        results = []
        correct_count = 0

        for i, correct_val in enumerate(correct_words):
            # 사용자가 입력한 값 가져오기
            user_val = user_submitted_data.get(f'answer_{i}', '').strip()
            
            # [대소문자 무시 비교] 양쪽 다 소문자로 변환하여 비교합니다.
            is_correct = (user_val.lower() == correct_val.strip().lower())
            
            if is_correct:
                correct_count += 1
            
            results.append({
                "index": i,
                "user_answer": user_val,
                "correct_answer": correct_val,
                "is_correct": is_correct
            })
            
        return {
            "results": results,
            "total_count": len(correct_words),
            "correct_count": correct_count
        }

# 싱글톤 객체 생성하여 다른 파일에서 import 하여 사용
study_service = StudyService()