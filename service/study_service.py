from models import db, StudyMaterial

class StudyService:
    def save_material(self, user_id, original_text, blank_words):
        """
        추출 텍스트와 빈칸 리스트를 한 엔티티로 묶어 DB에 저장
        """
        new_material = StudyMaterial(
            user_id=user_id,
            original_text=original_text,
            blank_words=blank_words, # SQLAlchemy JSON 컬럼에 리스트 저장
        )
        db.session.add(new_material)
        db.session.commit()
        
        return new_material.id