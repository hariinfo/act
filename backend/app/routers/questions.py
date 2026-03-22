from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from ..database import get_db
from ..models import Question, Subject, User
from ..schemas import QuestionCreate, QuestionOut, QuestionUpdate, SubjectOut
from ..auth import get_admin_user, get_current_user

router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.get("/subjects", response_model=list[SubjectOut])
def list_subjects(db: Session = Depends(get_db)):
    return db.query(Subject).all()


@router.get("/topics")
def list_topics(
    subject_id: Optional[int] = None,
    source_test: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List distinct topics with question counts, optionally filtered by subject/source."""
    q = (
        db.query(Question.topic, func.count(Question.id).label("count"))
        .filter(Question.topic.isnot(None), Question.topic != "")
    )
    if subject_id:
        q = q.filter(Question.subject_id == subject_id)
    if source_test:
        q = q.filter(Question.source_test == source_test)
    rows = q.group_by(Question.topic).order_by(Question.topic).all()
    return [{"topic": row[0], "count": row[1]} for row in rows]


@router.get("/stats")
def question_stats(db: Session = Depends(get_db)):
    total = db.query(Question).count()
    subjects = db.query(Subject).all()
    by_subject = {}
    for s in subjects:
        count = db.query(Question).filter(Question.subject_id == s.id).count()
        by_subject[s.name] = count

    sources = (
        db.query(Question.source_test)
        .distinct()
        .filter(Question.source_test.isnot(None))
        .all()
    )
    topics = (
        db.query(Question.topic)
        .distinct()
        .filter(Question.topic.isnot(None), Question.topic != "")
        .all()
    )
    return {
        "total_questions": total,
        "by_subject": by_subject,
        "sources": [s[0] for s in sources],
        "topics": [t[0] for t in topics],
    }


@router.get("/", response_model=list[QuestionOut])
def list_questions(
    subject_id: Optional[int] = None,
    difficulty: Optional[int] = None,
    topic: Optional[str] = None,
    source_test: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Question)
    if subject_id:
        q = q.filter(Question.subject_id == subject_id)
    if difficulty:
        q = q.filter(Question.difficulty == difficulty)
    if topic:
        q = q.filter(Question.topic == topic)
    if source_test:
        q = q.filter(Question.source_test == source_test)
    if search:
        q = q.filter(Question.question_text.ilike(f"%{search}%"))
    return q.order_by(Question.id).offset(skip).limit(limit).all()


@router.get("/{question_id}", response_model=QuestionOut)
def get_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.post("/", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def create_question(
    data: QuestionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    question = Question(**data.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.post("/bulk", response_model=list[QuestionOut], status_code=status.HTTP_201_CREATED)
def bulk_create_questions(
    questions: list[QuestionCreate],
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    created = []
    for data in questions:
        question = Question(**data.model_dump())
        db.add(question)
        created.append(question)
    db.commit()
    for q in created:
        db.refresh(q)
    return created


@router.put("/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: int,
    data: QuestionUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(question, key, value)

    db.commit()
    db.refresh(question)
    return question


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.commit()
