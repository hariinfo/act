from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, DateTime,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
import enum

from .database import Base


class AttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    abandoned = "abandoned"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    tests_created = relationship("Test", back_populates="creator")
    attempts = relationship("TestAttempt", back_populates="user")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    questions = relationship("Question", back_populates="subject")
    sections = relationship("TestSection", back_populates="subject")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_image = Column(Text, nullable=True)
    option_a = Column(Text, nullable=False)
    option_b = Column(Text, nullable=False)
    option_c = Column(Text, nullable=False)
    option_d = Column(Text, nullable=False)
    option_e = Column(Text, nullable=True)
    correct_answer = Column(String(1), nullable=False)
    explanation = Column(Text, nullable=True)
    difficulty = Column(Integer, default=3)
    topic = Column(String(100), nullable=True)
    source_test = Column(String(100), nullable=True)
    passage_text = Column(Text, nullable=True)
    passage_image = Column(Text, nullable=True)
    option_labels = Column(String(5), default="ABCDE")  # "ABCDE" or "FGHJK"
    question_number = Column(Integer, nullable=True)  # Original ACT question number
    created_at = Column(DateTime, default=datetime.utcnow)

    subject = relationship("Subject", back_populates="questions")
    section_questions = relationship("TestSectionQuestion", back_populates="question")
    attempt_answers = relationship("TestAttemptAnswer", back_populates="question")


class Test(Base):
    __tablename__ = "tests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    time_limit_minutes = Column(Integer, default=175)
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User", back_populates="tests_created")
    sections = relationship("TestSection", back_populates="test", order_by="TestSection.order")
    attempts = relationship("TestAttempt", back_populates="test")


class TestSection(Base):
    __tablename__ = "test_sections"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("tests.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    name = Column(String(100), nullable=True)
    num_questions = Column(Integer, nullable=False)
    time_limit_minutes = Column(Integer, nullable=False)
    order = Column(Integer, nullable=False)

    test = relationship("Test", back_populates="sections")
    subject = relationship("Subject", back_populates="sections")
    section_questions = relationship(
        "TestSectionQuestion", back_populates="section", order_by="TestSectionQuestion.order"
    )


class TestSectionQuestion(Base):
    __tablename__ = "test_section_questions"

    id = Column(Integer, primary_key=True, index=True)
    test_section_id = Column(Integer, ForeignKey("test_sections.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    order = Column(Integer, nullable=False)

    section = relationship("TestSection", back_populates="section_questions")
    question = relationship("Question", back_populates="section_questions")


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("tests.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    score = Column(Float, nullable=True)
    status = Column(SAEnum(AttemptStatus), default=AttemptStatus.in_progress)
    current_section_index = Column(Integer, default=0)

    test = relationship("Test", back_populates="attempts")
    user = relationship("User", back_populates="attempts")
    answers = relationship("TestAttemptAnswer", back_populates="attempt")


class TestAttemptAnswer(Base):
    __tablename__ = "test_attempt_answers"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("test_attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("test_sections.id"), nullable=True)
    selected_answer = Column(String(1), nullable=True)
    is_correct = Column(Boolean, nullable=True)
    time_spent_seconds = Column(Integer, nullable=True)

    attempt = relationship("TestAttempt", back_populates="answers")
    question = relationship("Question", back_populates="attempt_answers")
