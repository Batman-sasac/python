import uuid

class StudyService:
    def __init__(self):
        # 임시 인메모리 DB (서버 재시작 시 초기화됨)
        # 구조: { "session_id": [ {"word": "사과", "id": "uuid1"}, ... ] }
        self.db_blanks = {}

    def save_blank_word(self, session_id, word):
        """사용자가 선택한 단어를 DB에 저장"""
        if session_id not in self.db_blanks:
            self.db_blanks[session_id] = []
        
        blank_id = str(uuid.uuid4())[:8]
        self.db_blanks[session_id].append({
            "id": blank_id,
            "word": word.strip()
        })
        return blank_id

    def make_blank_text(self, original_text, session_id):
        # 해당 세션에 저장된 단어가 없으면 원본 그대로 반환
        if session_id not in self.db_blanks or not original_text:
            return original_text

        processed_text = original_text
        for item in self.db_blanks[session_id]:
            word = item["word"]
            # 실제 입력 가능한 HTML input 태그를 만듭니다.
            # size를 지정하거나 style로 너비를 주면 입력하기 편합니다.
            blank_html = f'<input type="text" name="answer_{item["id"]}" class="blank-input" style="width:{len(word)*20}px;" autocomplete="off">'
            
            # 원본에서 단어를 찾아 input 태그로 교체
            processed_text = processed_text.replace(word, blank_html, 1)
        
        return processed_text
        
    def check_answers(self, session_id, user_submitted_data):
        """사용자가 입력한 값과 DB의 정답을 비교"""
        if session_id not in self.db_blanks:
            return []

        results = []
        for item in self.db_blanks[session_id]:
            user_val = user_submitted_data.get(f'answer_{item["id"]}', '').strip()
            correct_val = item["word"]
            
            is_correct = (user_val == correct_val)
            results.append({
                "id": item["id"],
                "is_correct": is_correct,
                "user_answer": user_val,
                "correct_answer": correct_val
            })
        return results

# 싱글톤 객체 생성
study_service = StudyService()