import json
import logging
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("uvicorn.error")

# Semaphore to serialize PDF parsing — PyMuPDF (fitz) segfaults under concurrent use
_pdf_parse_lock = threading.Semaphore(1)
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional

from ..database import get_db
from ..models import (
    User, Question, Test, TestAttempt, TestAttemptAnswer,
    TestSection, TestSectionQuestion, Subject, AttemptStatus,
)
from ..schemas import DashboardStats, SourceInfo, UserOut, QuestionCreate, QuestionOut
from ..auth import get_admin_user, hash_password, get_current_user
from ..config import settings
from ..pdf_parser import parse_act_pdf
from ..topic_classifier import classify_questions
from ..explanation_generator import generate_explanations

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    subjects = db.query(Subject).all()
    subject_map = {s.id: s.name for s in subjects}
    by_subject = {}
    for s in subjects:
        count = db.query(Question).filter(Question.subject_id == s.id).count()
        by_subject[s.name] = count

    # Build source (uploaded PDF) breakdown
    source_rows = (
        db.query(Question.source_test)
        .distinct()
        .filter(Question.source_test.isnot(None))
        .all()
    )
    sources = []
    for (src,) in source_rows:
        src_questions = db.query(Question).filter(Question.source_test == src).all()
        first_created = min((q.created_at for q in src_questions), default=None)

        src_by_subject = {}
        for q in src_questions:
            sname = subject_map.get(q.subject_id, "Unknown")
            src_by_subject[sname] = src_by_subject.get(sname, 0) + 1

        src_by_topic = {}
        for q in src_questions:
            if q.topic:
                src_by_topic[q.topic] = src_by_topic.get(q.topic, 0) + 1

        sources.append(SourceInfo(
            source_test=src,
            total_questions=len(src_questions),
            by_subject=src_by_subject,
            by_topic=src_by_topic,
            created_at=first_created,
        ))

    sources.sort(key=lambda s: s.created_at or "", reverse=True)

    return DashboardStats(
        total_questions=db.query(Question).count(),
        total_tests=db.query(Test).count(),
        total_users=db.query(User).count(),
        total_attempts=db.query(TestAttempt).count(),
        questions_by_subject=by_subject,
        sources=sources,
    )


@router.delete("/questions/all")
def delete_all_questions(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Delete ALL questions and related test data (tests, attempts, answers)."""
    # Delete in dependency order
    db.query(TestAttemptAnswer).delete()
    db.query(TestAttempt).delete()
    db.query(TestSectionQuestion).delete()
    db.query(TestSection).delete()
    db.query(Test).delete()
    db.query(Question).delete()
    db.commit()
    return {"message": "All questions, tests, and related data deleted."}


@router.post("/seed-subjects")
def seed_subjects(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    subjects_data = [
        {"name": "English", "description": "Grammar, usage, and rhetorical skills - 75 questions, 45 minutes"},
        {"name": "Math", "description": "Pre-algebra through trigonometry - 60 questions, 60 minutes"},
        {"name": "Reading", "description": "Reading comprehension across four passages - 40 questions, 35 minutes"},
        {"name": "Science", "description": "Scientific reasoning and data interpretation - 40 questions, 35 minutes"},
    ]
    created = []
    for data in subjects_data:
        existing = db.query(Subject).filter(Subject.name == data["name"]).first()
        if not existing:
            s = Subject(**data)
            db.add(s)
            created.append(data["name"])
    db.commit()
    return {"message": f"Seeded subjects: {', '.join(created) if created else 'all already exist'}"}


@router.post("/create-admin", response_model=UserOut)
def create_admin(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    admin_count = db.query(User).filter(User.is_admin == True).count()
    if admin_count > 0:
        raise HTTPException(
            status_code=403,
            detail="Admin already exists. Use admin credentials to create more.",
        )

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/create-admin-auth", response_model=UserOut)
def create_admin_auth(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    source_test: str = Form(None),
    sections_filter: str = Form(None),  # comma-separated: "English,Math"
    skip_topics: bool = Form(False),
    skip_explanations: bool = Form(False),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Upload an ACT PDF and parse it into sections with questions and images.
    Returns SSE stream with progress updates, final event contains the full result."""
    logger.info(f"[Upload] === UPLOAD ENDPOINT HIT === file={file.filename}")
    logger.info(f"[Upload] Options: sections_filter={sections_filter}, skip_topics={skip_topics}, skip_explanations={skip_explanations}")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    content = await file.read()
    logger.info(f"[Upload] Read {len(content)} bytes")

    # Parse sections filter
    allowed_sections = None
    if sections_filter:
        allowed_sections = [s.strip() for s in sections_filter.split(",") if s.strip()]

    def generate():
        logger.info("[Upload] Starting PDF processing pipeline...")
        # Step 1: Parse PDF
        logger.info("[Upload] Step 1: Parsing PDF...")
        filter_hint = f" (will filter to: {', '.join(allowed_sections)})" if allowed_sections else ""
        yield f"data: {json.dumps({'step': 'parsing', 'message': f'Waiting to parse PDF...{filter_hint}'})}\n\n"
        # Serialize PDF parsing — PyMuPDF segfaults under concurrent use
        _pdf_parse_lock.acquire()
        try:
            yield f"data: {json.dumps({'step': 'parsing', 'message': f'Parsing PDF pages...{filter_hint}'})}\n\n"
            result = parse_act_pdf(content)
        finally:
            _pdf_parse_lock.release()
        result["filename"] = file.filename
        result["source_test"] = source_test or file.filename.replace(".pdf", "")

        all_sections = len(result.get("sections", []))
        all_q = sum(len(s["questions"]) for s in result.get("sections", []))

        # Filter sections if requested
        if allowed_sections:
            result["sections"] = [s for s in result.get("sections", []) if s["name"] in allowed_sections]
            logger.info(f"[Upload] Filtered to sections: {[s['name'] for s in result['sections']]}")

        total_sections = len(result.get("sections", []))
        total_q = sum(len(s["questions"]) for s in result.get("sections", []))
        answers_extracted = result.get("answers_extracted", 0)
        answer_msg = f' | {answers_extracted} correct answers extracted' if answers_extracted else ' | No answer key found'
        filter_msg = f' (filtered from {all_sections} sections)' if allowed_sections else ''
        logger.info(f"[Upload] Parsed: {total_sections} sections, {total_q} questions{answer_msg}{filter_msg}")
        yield f"data: {json.dumps({'step': 'parsed', 'message': f'Found {total_sections} sections with {total_q} questions{answer_msg}{filter_msg}', 'total_sections': total_sections})}\n\n"

        # Use a mutable list to collect SSE events from callbacks
        pending_events = []

        # Step 2: Classify topics per section (unless skipped)
        if skip_topics:
            logger.info("[Upload] Step 2: SKIPPED topic classification (user opted out)")
            yield f"data: {json.dumps({'step': 'classified', 'message': 'Topic classification skipped', 'section_index': 0, 'total_sections': total_sections})}\n\n"
        else:
            logger.info(f"[Upload] Step 2: Classifying topics for {total_sections} sections...")
            for i, section in enumerate(result.get("sections", [])):
                sec_name = section["name"]
                sec_q_count = len(section["questions"])
                logger.info(f"[Upload] Classifying {sec_name} ({sec_q_count} questions)...")
                yield f"data: {json.dumps({'step': 'classifying', 'message': f'Classifying topics for {sec_name} ({sec_q_count} questions)...', 'section_index': i, 'total_sections': total_sections})}\n\n"

                def on_classify_progress(batch_num, total_batches, batch_size, elapsed, _sec=sec_name, _i=i):
                    pending_events.append(
                        f"data: {json.dumps({'step': 'classifying_detail', 'message': f'{_sec}: classified batch {batch_num}/{total_batches} ({batch_size} questions, {elapsed:.1f}s)', 'section_index': _i, 'total_sections': total_sections})}\n\n"
                    )

                topics = classify_questions(sec_name, section["questions"], on_progress=on_classify_progress)
                for q, topic in zip(section["questions"], topics):
                    if topic:
                        q["topic"] = topic

                # Flush pending detail events
                for evt in pending_events:
                    yield evt
                pending_events.clear()

                classified_count = sum(1 for q in section["questions"] if q.get("topic"))
                logger.info(f"[Upload] {sec_name}: {classified_count}/{sec_q_count} topics assigned")
                yield f"data: {json.dumps({'step': 'classified', 'message': f'{sec_name}: {classified_count}/{sec_q_count} topics assigned', 'section_index': i, 'total_sections': total_sections})}\n\n"

        # Step 3: Generate explanations per section (unless skipped)
        if skip_explanations:
            logger.info("[Upload] Step 3: SKIPPED explanation generation (user opted out)")
            yield f"data: {json.dumps({'step': 'explained', 'message': 'Explanation generation skipped', 'section_index': 0, 'total_sections': total_sections})}\n\n"
        else:
            logger.info(f"[Upload] Step 3: Generating explanations for {total_sections} sections...")
            for i, section in enumerate(result.get("sections", [])):
                sec_name = section["name"]
                sec_q_count = len(section["questions"])
                logger.info(f"[Upload] Explaining {sec_name} ({sec_q_count} questions)...")
                yield f"data: {json.dumps({'step': 'explaining', 'message': f'Generating explanations for {sec_name} ({sec_q_count} questions)...', 'section_index': i, 'total_sections': total_sections})}\n\n"

                def on_explain_progress(idx, total, q_num, status, elapsed, _sec=sec_name, _i=i):
                    status_label = "done" if status == "ok" else "failed"
                    pending_events.append(
                        f"data: {json.dumps({'step': 'explaining_detail', 'message': f'{_sec}: explanation for Q{q_num} {status_label} ({idx+1}/{total}, {elapsed:.1f}s)', 'section_index': _i, 'total_sections': total_sections, 'question_number': q_num, 'question_index': idx + 1, 'question_total': total})}\n\n"
                    )

                explanations = generate_explanations(sec_name, section["questions"], on_progress=on_explain_progress)
                explained_count = 0
                for q, explanation in zip(section["questions"], explanations):
                    if explanation:
                        q["explanation"] = explanation
                        explained_count += 1

                # Flush pending detail events
                for evt in pending_events:
                    yield evt
                pending_events.clear()

            logger.info(f"[Upload] {sec_name}: {explained_count}/{sec_q_count} explanations generated")
            yield f"data: {json.dumps({'step': 'explained', 'message': f'{sec_name}: {explained_count}/{sec_q_count} explanations generated', 'section_index': i, 'total_sections': total_sections})}\n\n"

        # Step 4: Done - send the full result
        logger.info("[Upload] Step 4: Done! Sending result...")
        yield f"data: {json.dumps({'step': 'done', 'message': 'Processing complete!', 'result': result})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class ImportSectionQuestion(BaseModel):
    question_number: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: Optional[str] = None
    correct_answer: Optional[str] = None
    option_labels: Optional[str] = "ABCDE"
    passage_text: Optional[str] = None
    passage_image: Optional[str] = None
    question_image: Optional[str] = None
    topic: Optional[str] = None
    explanation: Optional[str] = None
    difficulty: int = 3


class ImportSection(BaseModel):
    name: str
    time_limit_minutes: int
    questions: list[ImportSectionQuestion]


class ImportTestRequest(BaseModel):
    test_name: str
    source_test: str
    sections: list[ImportSection]


@router.post("/import-test")
def import_and_create_test(
    data: ImportTestRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    Import parsed PDF data: create all questions and assemble them into a test
    that mirrors the original ACT PDF structure.
    """
    # Ensure subjects exist
    subject_map = {}
    for s in db.query(Subject).all():
        subject_map[s.name] = s.id

    if not subject_map:
        raise HTTPException(status_code=400, detail="Seed subjects first (Admin > Seed Subjects)")

    # Create the test
    total_time = sum(s.time_limit_minutes for s in data.sections)
    test = Test(
        name=data.test_name,
        description=f"Imported from {data.source_test}",
        created_by=admin.id,
        time_limit_minutes=total_time,
    )
    db.add(test)
    db.flush()

    total_questions_created = 0

    for order, sec_data in enumerate(data.sections, 1):
        subject_id = subject_map.get(sec_data.name)
        if not subject_id:
            # Try partial match
            for sname, sid in subject_map.items():
                if sname.lower() in sec_data.name.lower() or sec_data.name.lower() in sname.lower():
                    subject_id = sid
                    break
        if not subject_id:
            subject_id = list(subject_map.values())[0]

        section = TestSection(
            test_id=test.id,
            subject_id=subject_id,
            name=sec_data.name,
            num_questions=len(sec_data.questions),
            time_limit_minutes=sec_data.time_limit_minutes,
            order=order,
        )
        db.add(section)
        db.flush()

        for q_order, q_data in enumerate(sec_data.questions, 1):
            question = Question(
                subject_id=subject_id,
                question_text=q_data.question_text,
                option_a=q_data.option_a,
                option_b=q_data.option_b,
                option_c=q_data.option_c,
                option_d=q_data.option_d,
                option_e=q_data.option_e,
                correct_answer=q_data.correct_answer or "?",
                option_labels=q_data.option_labels or "ABCDE",
                difficulty=q_data.difficulty,
                topic=q_data.topic,
                source_test=data.source_test,
                passage_text=q_data.passage_text,
                passage_image=q_data.passage_image,
                question_image=q_data.question_image,
                explanation=q_data.explanation,
                question_number=q_data.question_number,
            )
            db.add(question)
            db.flush()

            sq = TestSectionQuestion(
                test_section_id=section.id,
                question_id=question.id,
                order=q_data.question_number,
            )
            db.add(sq)
            total_questions_created += 1

    db.commit()
    db.refresh(test)

    return {
        "message": f"Test '{data.test_name}' created successfully",
        "test_id": test.id,
        "total_questions": total_questions_created,
        "sections": [
            {"name": s.name, "questions": s.num_questions, "time_minutes": s.time_limit_minutes}
            for s in test.sections
        ],
    }


# ── User Management ──

@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    data: CreateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
    }


class SendTestEmailRequest(BaseModel):
    user_id: int
    test_id: int
    password: Optional[str] = None


@router.post("/send-test-email")
def send_test_email(
    data: SendTestEmailRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    test = db.query(Test).filter(Test.id == data.test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    test_url = f"{settings.APP_URL}/tests/{test.id}"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1a237e; color: white; padding: 24px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 24px;">ACT Practice Test</h1>
        </div>
        <div style="padding: 24px; background: #f5f5f5; border: 1px solid #ddd;">
            <p>Hi <strong>{user.username}</strong>,</p>
            <p>You have been assigned a new practice test:</p>
            <div style="background: white; border-radius: 8px; padding: 20px; margin: 16px 0; border: 1px solid #ddd;">
                <h2 style="margin: 0 0 8px; color: #1a237e;">{test.name}</h2>
                <p style="margin: 0; color: #666;">{test.description or ''}</p>
            </div>
            <div style="background: white; border-radius: 8px; padding: 16px; margin: 16px 0; border: 1px solid #ddd;">
                <p style="margin: 0 0 8px; font-weight: bold;">Your Login Credentials:</p>
                <p style="margin: 4px 0;">Username: <strong>{user.username}</strong></p>
                {f'<p style="margin: 4px 0;">Password: <strong>{data.password}</strong></p>' if data.password else ''}
            </div>
            <div style="text-align: center; margin: 24px 0;">
                <a href="{test_url}" style="display: inline-block; background: #1a237e; color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">
                    Start Test
                </a>
            </div>
            <p style="font-size: 13px; color: #999; text-align: center;">
                Or copy this link: {test_url}
            </p>
        </div>
    </div>
    """

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return {
            "message": "Email not configured (SMTP settings missing). Test link generated.",
            "test_url": test_url,
            "email_sent": False,
        }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"ACT Practice Test: {test.name}"
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = user.email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        return {
            "message": f"Email sent to {user.email}",
            "test_url": test_url,
            "email_sent": True,
        }
    except Exception as e:
        return {
            "message": f"Failed to send email: {str(e)}. Test link generated.",
            "test_url": test_url,
            "email_sent": False,
        }


# ── User Performance Tracking ──

@router.get("/users/{user_id}/performance")
def get_user_performance(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    attempts = (
        db.query(TestAttempt)
        .options(
            joinedload(TestAttempt.test).joinedload(Test.sections).joinedload(TestSection.subject)
        )
        .filter(TestAttempt.user_id == user_id, TestAttempt.status == AttemptStatus.completed)
        .order_by(TestAttempt.completed_at.desc())
        .all()
    )

    subject_map = {s.id: s.name for s in db.query(Subject).all()}

    results = []
    for attempt in attempts:
        answers = db.query(TestAttemptAnswer).filter(TestAttemptAnswer.attempt_id == attempt.id).all()
        total_correct = sum(1 for a in answers if a.is_correct)
        total_questions = sum(s.num_questions for s in attempt.test.sections)

        section_scores = []
        for section in sorted(attempt.test.sections, key=lambda s: s.order):
            sec_answers = [a for a in answers if a.section_id == section.id]
            correct = sum(1 for a in sec_answers if a.is_correct)
            total = section.num_questions
            pct = (correct / total * 100) if total > 0 else 0
            scaled = max(1, min(36, round(pct / 100 * 36)))

            # Topic breakdown for this section
            topic_scores = {}
            for a in sec_answers:
                q = db.query(Question).filter(Question.id == a.question_id).first()
                if q and q.topic:
                    if q.topic not in topic_scores:
                        topic_scores[q.topic] = {"correct": 0, "total": 0}
                    topic_scores[q.topic]["total"] += 1
                    if a.is_correct:
                        topic_scores[q.topic]["correct"] += 1

            section_scores.append({
                "section_name": section.name or subject_map.get(section.subject_id, "Unknown"),
                "subject": subject_map.get(section.subject_id, "Unknown"),
                "correct": correct,
                "total": total,
                "percentage": round(pct, 1),
                "scaled_score": scaled,
                "topics": {
                    k: {"correct": v["correct"], "total": v["total"], "percentage": round(v["correct"] / v["total"] * 100, 1) if v["total"] > 0 else 0}
                    for k, v in topic_scores.items()
                },
            })

        scaled_scores = [s["scaled_score"] for s in section_scores]
        composite = round(sum(scaled_scores) / len(scaled_scores)) if scaled_scores else 0

        results.append({
            "attempt_id": attempt.id,
            "test_id": attempt.test_id,
            "test_name": attempt.test.name,
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
            "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
            "total_correct": total_correct,
            "total_questions": total_questions,
            "composite_score": composite,
            "section_scores": section_scores,
        })

    return {
        "user": {"id": user.id, "username": user.username, "email": user.email},
        "attempts": results,
    }
