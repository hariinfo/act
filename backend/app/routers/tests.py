from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import random

from ..database import get_db
from ..models import (
    Test, TestSection, TestSectionQuestion, TestAttempt, TestAttemptAnswer,
    Question, Subject, User, AttemptStatus,
)
from ..schemas import (
    TestCreate, TestOut, TestDetailOut, TestSectionDetailOut,
    TestAttemptOut, AnswerSubmit, TestResultOut, SectionScore,
    QuestionTestTaker, AnswerOut,
)
from ..auth import get_current_user, get_admin_user

router = APIRouter(prefix="/api/tests", tags=["tests"])


@router.post("/", response_model=TestOut, status_code=status.HTTP_201_CREATED)
def create_test(
    data: TestCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    test = Test(
        name=data.name,
        description=data.description,
        created_by=admin.id,
        time_limit_minutes=data.time_limit_minutes,
    )
    db.add(test)
    db.flush()

    total_questions = 0
    for sec_data in data.sections:
        section = TestSection(
            test_id=test.id,
            subject_id=sec_data.subject_id,
            name=sec_data.name,
            num_questions=sec_data.num_questions,
            time_limit_minutes=sec_data.time_limit_minutes,
            order=sec_data.order,
        )
        db.add(section)
        db.flush()

        if sec_data.auto_pick:
            q_filter = db.query(Question).filter(Question.subject_id == sec_data.subject_id)
            if sec_data.topic:
                q_filter = q_filter.filter(Question.topic == sec_data.topic)
            if sec_data.source_test:
                q_filter = q_filter.filter(Question.source_test == sec_data.source_test)
            available = q_filter.all()
            picked = random.sample(available, min(sec_data.num_questions, len(available)))
            for i, q in enumerate(picked):
                sq = TestSectionQuestion(
                    test_section_id=section.id, question_id=q.id,
                    order=q.question_number or (i + 1),
                )
                db.add(sq)
            total_questions += len(picked)
        else:
            for i, qid in enumerate(sec_data.question_ids):
                q = db.query(Question).filter(Question.id == qid).first()
                sq = TestSectionQuestion(
                    test_section_id=section.id, question_id=qid,
                    order=q.question_number if q and q.question_number else (i + 1),
                )
                db.add(sq)
            total_questions += len(sec_data.question_ids)

    db.commit()
    db.refresh(test)

    return TestOut(
        id=test.id,
        name=test.name,
        description=test.description,
        is_active=test.is_active,
        time_limit_minutes=test.time_limit_minutes,
        created_at=test.created_at,
        sections=[
            {
                "id": s.id,
                "subject_id": s.subject_id,
                "name": s.name,
                "num_questions": s.num_questions,
                "time_limit_minutes": s.time_limit_minutes,
                "order": s.order,
            }
            for s in test.sections
        ],
        total_questions=total_questions,
    )


@router.get("/", response_model=list[TestOut])
def list_tests(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    tests = (
        db.query(Test)
        .filter(Test.is_active == True)
        .options(joinedload(Test.sections))
        .order_by(Test.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    result = []
    for test in tests:
        total_q = sum(s.num_questions for s in test.sections)
        result.append(
            TestOut(
                id=test.id,
                name=test.name,
                description=test.description,
                is_active=test.is_active,
                time_limit_minutes=test.time_limit_minutes,
                created_at=test.created_at,
                sections=[
                    {
                        "id": s.id,
                        "subject_id": s.subject_id,
                        "name": s.name,
                        "num_questions": s.num_questions,
                        "time_limit_minutes": s.time_limit_minutes,
                        "order": s.order,
                    }
                    for s in test.sections
                ],
                total_questions=total_q,
            )
        )
    return result


# NOTE: /attempts/... routes MUST come before /{test_id} to avoid route conflicts

@router.get("/my-attempts", response_model=list[TestAttemptOut])
def get_my_attempts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempts = (
        db.query(TestAttempt)
        .filter(
            TestAttempt.user_id == current_user.id,
            TestAttempt.status == AttemptStatus.in_progress,
        )
        .all()
    )
    return attempts


@router.post("/attempts/{attempt_id}/answer", response_model=AnswerOut)
def submit_answer(
    attempt_id: int,
    data: AnswerSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
    if not attempt or attempt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.status != AttemptStatus.in_progress:
        raise HTTPException(status_code=400, detail="Test already completed")

    # Check if answer already exists for this question
    existing = (
        db.query(TestAttemptAnswer)
        .filter(
            TestAttemptAnswer.attempt_id == attempt_id,
            TestAttemptAnswer.question_id == data.question_id,
        )
        .first()
    )

    question = db.query(Question).filter(Question.id == data.question_id).first()
    is_correct = (
        data.selected_answer and question and
        data.selected_answer.upper() == question.correct_answer.upper()
    ) if data.selected_answer else None

    if existing:
        existing.selected_answer = data.selected_answer
        existing.is_correct = is_correct
        existing.time_spent_seconds = data.time_spent_seconds
        existing.section_id = data.section_id
        db.commit()
        db.refresh(existing)
        return existing
    else:
        answer = TestAttemptAnswer(
            attempt_id=attempt_id,
            question_id=data.question_id,
            selected_answer=data.selected_answer,
            is_correct=is_correct,
            time_spent_seconds=data.time_spent_seconds,
            section_id=data.section_id,
        )
        db.add(answer)
        db.commit()
        db.refresh(answer)
        return answer


@router.post("/attempts/{attempt_id}/complete", response_model=TestResultOut)
def complete_test(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = (
        db.query(TestAttempt)
        .options(joinedload(TestAttempt.test).joinedload(Test.sections).joinedload(TestSection.subject))
        .filter(TestAttempt.id == attempt_id)
        .first()
    )
    if not attempt or attempt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attempt not found")

    attempt.status = AttemptStatus.completed
    attempt.completed_at = datetime.utcnow()

    answers = db.query(TestAttemptAnswer).filter(TestAttemptAnswer.attempt_id == attempt_id).all()
    total_correct = sum(1 for a in answers if a.is_correct)
    total_questions = sum(s.num_questions for s in attempt.test.sections)
    overall_pct = (total_correct / total_questions * 100) if total_questions > 0 else 0

    # Look up correct answers for all answered questions
    q_ids = [a.question_id for a in answers]
    questions_map = {}
    if q_ids:
        qs = db.query(Question).filter(Question.id.in_(q_ids)).all()
        questions_map = {q.id: q.correct_answer for q in qs}

    # Calculate section scores
    section_scores = []
    scaled_scores = []
    for section in sorted(attempt.test.sections, key=lambda s: s.order):
        section_answers = [a for a in answers if a.section_id == section.id]
        correct = sum(1 for a in section_answers if a.is_correct)
        total = section.num_questions
        pct = (correct / total * 100) if total > 0 else 0
        # ACT scaled score: roughly map percentage to 1-36
        scaled = max(1, min(36, round(pct / 100 * 36)))
        scaled_scores.append(scaled)
        section_scores.append(
            SectionScore(
                section_id=section.id,
                section_name=section.name or section.subject.name,
                subject_name=section.subject.name,
                correct=correct,
                total=total,
                percentage=round(pct, 1),
                scaled_score=scaled,
            )
        )

    composite = round(sum(scaled_scores) / len(scaled_scores)) if scaled_scores else 0
    attempt.score = composite
    db.commit()

    return TestResultOut(
        attempt_id=attempt.id,
        test_name=attempt.test.name,
        total_correct=total_correct,
        total_questions=total_questions,
        overall_percentage=round(overall_pct, 1),
        composite_score=composite,
        section_scores=section_scores,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        answers=[
            AnswerOut(
                id=a.id,
                question_id=a.question_id,
                selected_answer=a.selected_answer,
                is_correct=a.is_correct,
                time_spent_seconds=a.time_spent_seconds,
                correct_answer=questions_map.get(a.question_id),
            )
            for a in answers
        ],
    )


@router.get("/attempts/{attempt_id}", response_model=TestAttemptOut)
def get_attempt(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
    if not attempt or attempt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return attempt


@router.get("/attempts/{attempt_id}/answers", response_model=list[AnswerOut])
def get_attempt_answers(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
    if not attempt or attempt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attempt not found")

    answers = db.query(TestAttemptAnswer).filter(TestAttemptAnswer.attempt_id == attempt_id).all()
    return [
        AnswerOut(
            id=a.id,
            question_id=a.question_id,
            selected_answer=a.selected_answer,
            is_correct=a.is_correct,
            time_spent_seconds=a.time_spent_seconds,
            section_id=a.section_id,
        )
        for a in answers
    ]


@router.get("/attempts/{attempt_id}/results", response_model=TestResultOut)
def get_results(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = (
        db.query(TestAttempt)
        .options(joinedload(TestAttempt.test).joinedload(Test.sections).joinedload(TestSection.subject))
        .filter(TestAttempt.id == attempt_id)
        .first()
    )
    if not attempt or attempt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attempt not found")

    answers = db.query(TestAttemptAnswer).filter(TestAttemptAnswer.attempt_id == attempt_id).all()
    total_correct = sum(1 for a in answers if a.is_correct)
    total_questions = sum(s.num_questions for s in attempt.test.sections)
    overall_pct = (total_correct / total_questions * 100) if total_questions > 0 else 0

    # Look up correct answers for all answered questions
    q_ids = [a.question_id for a in answers]
    questions_map = {}
    if q_ids:
        qs = db.query(Question).filter(Question.id.in_(q_ids)).all()
        questions_map = {q.id: q.correct_answer for q in qs}

    section_scores = []
    scaled_scores = []
    for section in sorted(attempt.test.sections, key=lambda s: s.order):
        section_answers = [a for a in answers if a.section_id == section.id]
        correct = sum(1 for a in section_answers if a.is_correct)
        total = section.num_questions
        pct = (correct / total * 100) if total > 0 else 0
        scaled = max(1, min(36, round(pct / 100 * 36)))
        scaled_scores.append(scaled)
        section_scores.append(
            SectionScore(
                section_id=section.id,
                section_name=section.name or section.subject.name,
                subject_name=section.subject.name,
                correct=correct,
                total=total,
                percentage=round(pct, 1),
                scaled_score=scaled,
            )
        )

    composite = round(sum(scaled_scores) / len(scaled_scores)) if scaled_scores else 0

    return TestResultOut(
        attempt_id=attempt.id,
        test_name=attempt.test.name,
        total_correct=total_correct,
        total_questions=total_questions,
        overall_percentage=round(overall_pct, 1),
        composite_score=composite,
        section_scores=section_scores,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        answers=[
            AnswerOut(
                id=a.id,
                question_id=a.question_id,
                selected_answer=a.selected_answer,
                is_correct=a.is_correct,
                time_spent_seconds=a.time_spent_seconds,
                correct_answer=questions_map.get(a.question_id),
            )
            for a in answers
        ],
    )


# NOTE: /{test_id} routes MUST come after /attempts/... routes to avoid route conflicts

@router.get("/{test_id}", response_model=TestDetailOut)
def get_test_detail(
    test_id: int,
    attempt_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    test = (
        db.query(Test)
        .options(
            joinedload(Test.sections)
            .joinedload(TestSection.section_questions)
            .joinedload(TestSectionQuestion.question)
        )
        .filter(Test.id == test_id)
        .first()
    )
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Check if this is a review (completed attempt)
    is_review = False
    if attempt_id:
        attempt = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
        if attempt and attempt.status == AttemptStatus.completed:
            is_review = True

    sections_out = []
    for section in sorted(test.sections, key=lambda s: s.order):
        questions_out = []
        for sq in sorted(section.section_questions, key=lambda sq: sq.order):
            q = sq.question
            if q:
                qt = QuestionTestTaker(
                    id=q.id,
                    subject_id=q.subject_id,
                    question_number=sq.order,
                    question_text=q.question_text,
                    question_image=q.question_image,
                    option_a=q.option_a,
                    option_b=q.option_b,
                    option_c=q.option_c,
                    option_d=q.option_d,
                    option_e=q.option_e,
                    correct_answer=q.correct_answer if is_review else None,
                    topic=q.topic,
                    passage_text=q.passage_text,
                    passage_image=q.passage_image,
                    option_labels=q.option_labels,
                    explanation=q.explanation if is_review else None,
                    source_test=q.source_test,
                )
                questions_out.append(qt)
        sections_out.append(
            TestSectionDetailOut(
                id=section.id,
                subject_id=section.subject_id,
                name=section.name,
                num_questions=section.num_questions,
                time_limit_minutes=section.time_limit_minutes,
                order=section.order,
                questions=questions_out,
            )
        )

    return TestDetailOut(
        id=test.id,
        name=test.name,
        description=test.description,
        time_limit_minutes=test.time_limit_minutes,
        sections=sections_out,
    )


@router.post("/{test_id}/start", response_model=TestAttemptOut)
def start_test(
    test_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    test = db.query(Test).filter(Test.id == test_id, Test.is_active == True).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Check for existing in-progress attempt
    existing = (
        db.query(TestAttempt)
        .filter(
            TestAttempt.test_id == test_id,
            TestAttempt.user_id == current_user.id,
            TestAttempt.status == AttemptStatus.in_progress,
        )
        .first()
    )
    if existing:
        return existing

    attempt = TestAttempt(
        test_id=test_id,
        user_id=current_user.id,
        status=AttemptStatus.in_progress,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt
