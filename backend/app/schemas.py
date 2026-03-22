from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# ── Auth ──
class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# ── Subject ──
class SubjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


# ── Question ──
class QuestionCreate(BaseModel):
    subject_id: int
    question_text: str
    question_image: Optional[str] = None
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: Optional[str] = None
    correct_answer: str
    explanation: Optional[str] = None
    difficulty: int = 3
    topic: Optional[str] = None
    source_test: Optional[str] = None
    passage_text: Optional[str] = None
    passage_image: Optional[str] = None
    option_labels: Optional[str] = "ABCDE"


class QuestionUpdate(BaseModel):
    subject_id: Optional[int] = None
    question_text: Optional[str] = None
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    option_e: Optional[str] = None
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    difficulty: Optional[int] = None
    topic: Optional[str] = None
    source_test: Optional[str] = None
    passage_text: Optional[str] = None


class QuestionOut(BaseModel):
    id: int
    subject_id: int
    question_text: str
    question_image: Optional[str] = None
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: Optional[str] = None
    correct_answer: str
    explanation: Optional[str] = None
    difficulty: int
    topic: Optional[str] = None
    source_test: Optional[str] = None
    passage_text: Optional[str] = None
    passage_image: Optional[str] = None
    option_labels: Optional[str] = "ABCDE"
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionTestTaker(BaseModel):
    """Question for test takers - correct_answer included for review after completion"""
    id: int
    subject_id: int
    question_number: Optional[int] = None
    question_text: str
    question_image: Optional[str] = None
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: Optional[str] = None
    correct_answer: Optional[str] = None
    topic: Optional[str] = None
    passage_text: Optional[str] = None
    passage_image: Optional[str] = None
    option_labels: Optional[str] = "ABCDE"
    explanation: Optional[str] = None
    source_test: Optional[str] = None

    class Config:
        from_attributes = True


# ── Test ──
class SectionQuestionAssign(BaseModel):
    question_id: int
    order: int


class TestSectionCreate(BaseModel):
    subject_id: int
    name: Optional[str] = None
    num_questions: int
    time_limit_minutes: int
    order: int
    question_ids: list[int] = []
    auto_pick: bool = False
    topic: Optional[str] = None
    source_test: Optional[str] = None


class TestCreate(BaseModel):
    name: str
    description: Optional[str] = None
    time_limit_minutes: int = 175
    sections: list[TestSectionCreate]


class TestSectionOut(BaseModel):
    id: int
    subject_id: int
    name: Optional[str] = None
    num_questions: int
    time_limit_minutes: int
    order: int

    class Config:
        from_attributes = True


class TestSectionDetailOut(TestSectionOut):
    questions: list[QuestionTestTaker] = []


class TestOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    time_limit_minutes: int
    created_at: datetime
    sections: list[TestSectionOut] = []
    total_questions: int = 0

    class Config:
        from_attributes = True


class TestDetailOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    time_limit_minutes: int
    sections: list[TestSectionDetailOut] = []

    class Config:
        from_attributes = True


# ── Test Attempt ──
class AnswerSubmit(BaseModel):
    question_id: int
    selected_answer: Optional[str] = None
    section_id: Optional[int] = None
    time_spent_seconds: Optional[int] = None


class TestAttemptOut(BaseModel):
    id: int
    test_id: int
    user_id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    score: Optional[float] = None
    status: str
    current_section_index: int

    class Config:
        from_attributes = True


class AnswerOut(BaseModel):
    id: int
    question_id: int
    selected_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    time_spent_seconds: Optional[int] = None
    correct_answer: Optional[str] = None
    section_id: Optional[int] = None

    class Config:
        from_attributes = True


class SectionScore(BaseModel):
    section_id: int
    section_name: str
    subject_name: str
    correct: int
    total: int
    percentage: float
    scaled_score: int


class TestResultOut(BaseModel):
    attempt_id: int
    test_name: str
    total_correct: int
    total_questions: int
    overall_percentage: float
    composite_score: int
    section_scores: list[SectionScore]
    started_at: datetime
    completed_at: Optional[datetime] = None
    answers: list[AnswerOut] = []


class SourceInfo(BaseModel):
    source_test: str
    total_questions: int
    by_subject: dict[str, int]
    by_topic: dict[str, int]
    created_at: Optional[datetime] = None


class DashboardStats(BaseModel):
    total_questions: int
    total_tests: int
    total_users: int
    total_attempts: int
    questions_by_subject: dict[str, int]
    sources: list[SourceInfo] = []
