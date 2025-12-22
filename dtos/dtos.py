from dataclasses import dataclass
from typing import List, Optional

@dataclass
class UserDTO:
    nickname: str
    points: int

@dataclass
class StudyMaterialDTO:
    material_id: int
    original_text: str
    blank_words: List[str]
    created_at: str

@dataclass
class RewardResultDTO:
    is_correct: bool
    user_answer: str
    correct_answer: str
    earned_points: int