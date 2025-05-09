from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Form,
    status,
    UploadFile,
    File
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from pathlib import Path
import shutil
import uuid
from datetime import datetime
from typing import Optional

from app.models import models
from app.schemas import schemas
from app import database
from app.auth import get_current_user
from app.dependencies import templates
from sqlalchemy import text

from sqlalchemy import cast, String

router = APIRouter(
    prefix="/subjects/{subject_id}/assignments",
    tags=["assignments"]
)

UPLOAD_DIR = "uploads/assignments"
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


# -------------------------------
# Helper Functions
# -------------------------------

async def get_subject_with_groups(
    db: AsyncSession,
    subject_id: int,
    user: models.User
) -> models.Subject:
    # Исправленный запрос
    subject = await db.execute(
        select(models.Subject)
        .options(
            selectinload(models.Subject.groups),
            selectinload(models.Subject.teacher)
        )
        .where(models.Subject.id == subject_id)
    )
    subject = subject.scalar()

    if not subject:
        raise HTTPException(404, "Subject not found")
    if user.role != "teacher" or subject.teacher.user_id != user.id:
        raise HTTPException(403, "Forbidden")

    return subject


async def get_assignment_with_submissions(
        db: AsyncSession,
        assignment_id: int,
        user: models.User
) -> models.CourseMaterial:
    assignment = await db.execute(
        select(models.CourseMaterial)
        .options(
            selectinload(models.CourseMaterial.submissions)
            .selectinload(models.Submission.student)
            .selectinload(models.Student.user),
            selectinload(models.CourseMaterial.group)
        )
        .where(and_(
            models.CourseMaterial.id == assignment_id,
            cast(models.CourseMaterial.type, String) == 'assignment'
        )))

    assignment = assignment.scalar()

    if not assignment:
        raise HTTPException(404, "Assignment not found")

    return assignment


# -------------------------------
# HTML Endpoints
# -------------------------------

@router.get("/", response_class=HTMLResponse)
async def assignments_list(
        request: Request,
        subject_id: int,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = await get_subject_with_groups(db, subject_id, current_user)

    assignments = await db.execute(
        select(models.CourseMaterial)
        .options(
            selectinload(models.CourseMaterial.submissions),
            selectinload(models.CourseMaterial.group)
        )
        .where(and_(
            models.CourseMaterial.subject_id == subject_id,
            cast(models.CourseMaterial.type, String) == 'assignment'
        ))
    )
    assignments = assignments.scalars().all()

    return templates.TemplateResponse(
        "assignments/list.html",
        {
            "request": request,
            "subject": subject,
            "assignments": assignments,
            "current_time": datetime.now(),
            "current_user": current_user
        }
    )


@router.get("/{assignment_id}", response_class=HTMLResponse)
async def assignment_detail(
        request: Request,
        subject_id: int,
        assignment_id: int,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = await get_subject_with_groups(db, subject_id, current_user)
    assignment = await get_assignment_with_submissions(db, assignment_id, current_user)

    return templates.TemplateResponse(
        "assignments/detail.html",
        {
            "request": request,
            "subject": subject,
            "assignment": assignment,
            "current_time": datetime.now()
        }
    )


# -------------------------------
# Submission Handling
# -------------------------------

@router.post("/{assignment_id}/grade")
async def grade_submission(
        subject_id: int,
        assignment_id: int,
        submission_id: int = Form(...),
        grade: int = Form(...),
        feedback: Optional[str] = Form(None),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    # Проверка прав преподавателя
    await get_subject_with_groups(db, subject_id, current_user)

    submission = await db.execute(
        select(models.Submission)
        .where(models.Submission.id == submission_id)
    )
    submission = submission.scalar()

    if not submission or submission.assignment_id != assignment_id:
        raise HTTPException(404, "Submission not found")

    submission.grade = grade
    submission.feedback = feedback
    submission.status = "graded"
    submission.graded_at = datetime.now()

    await db.commit()
    return RedirectResponse(
        f"/subjects/{subject_id}/assignments/{assignment_id}",
        status_code=303
    )


@router.post("/{assignment_id}/submit")
async def submit_assignment(
        subject_id: int,
        assignment_id: int,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    # Проверка прав студента
    if current_user.role != "student":
        raise HTTPException(403, "Only students can submit assignments")

    # Получение задания
    assignment = await db.execute(
        select(models.CourseMaterial)
        .options(selectinload(models.CourseMaterial.group))
        .where(models.CourseMaterial.id == assignment_id)
    )
    assignment = assignment.scalar()

    # Проверка дедлайна
    if assignment.deadline < datetime.now():
        raise HTTPException(400, "Assignment deadline has passed")

    # Проверка принадлежности к группе
    student = await db.execute(
        select(models.Student)
        .where(models.Student.user_id == current_user.id)
    )
    student = student.scalar()

    if not student or student.group_id != assignment.group_id:
        raise HTTPException(403, "Not enrolled in this group")

    # Сохранение файла
    file_dir = Path(UPLOAD_DIR) / f"assignment_{assignment_id}"
    file_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{student.id}_{uuid.uuid4().hex}{Path(file.filename).suffix}"
    file_path = file_dir / file_name

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Создание или обновление submission
    existing = await db.execute(
        select(models.Submission)
        .where(and_(
            models.Submission.student_id == student.id,
            models.Submission.assignment_id == assignment_id
        ))
    )
    existing = existing.scalar()

    if existing:
        existing.file_path = str(file_path)
        existing.submitted_at = datetime.now()
        existing.status = "submitted"
    else:
        submission = models.Submission(
            student_id=student.id,
            assignment_id=assignment_id,
            file_path=str(file_path),
            status="submitted"
        )
        db.add(submission)

    await db.commit()
    return RedirectResponse(
        f"/subjects/{subject_id}/assignments",
        status_code=303
    )