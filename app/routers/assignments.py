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
import logging
logger = logging.getLogger(__name__)
from sqlalchemy import cast, String

from app.models.models import AssignmentSubmission as Submission

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
    # Новый вариант проверки прав
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

    # Для преподавателя
    if user.role == "teacher":
        teacher = await db.execute(
            select(models.Teacher)
            .where(models.Teacher.user_id == user.id)
        )
        teacher = teacher.scalar()
        if not teacher or subject.teacher_id != teacher.user_id:
            raise HTTPException(403, "Forbidden")

    # Для студента
    if user.role == "student":
        student = await db.execute(
            select(models.Student)
            .options(selectinload(models.Student.group))
            .where(models.Student.user_id == user.id)
        )
        student = student.scalar()
        if not student or student.group_id not in [g.id for g in subject.groups]:
            raise HTTPException(403, "Access denied for this group")

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
            .selectinload(Submission.student)
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
    try:
        subject = await get_subject_with_groups(db, subject_id, current_user)
    except HTTPException as e:
        return RedirectResponse(f"/?error={e.detail}", status_code=303)

    # Существующий код получения заданий
    base_query = select(models.CourseMaterial).where(and_(
        models.CourseMaterial.subject_id == subject_id,
        cast(models.CourseMaterial.type, String) == 'assignment'
    ))

    if current_user.role == "student":
        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()
        base_query = base_query.where(models.CourseMaterial.group_id == student.group_id)

    assignments = await db.execute(
        base_query.options(
            selectinload(models.CourseMaterial.group),
            selectinload(models.CourseMaterial.submissions)
        )
    )
    assignments = assignments.scalars().all()

    # Добавляем новый код для получения статусов отправок
    submission_status = {}
    if current_user.role == "student" and assignments:
        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()

        if student:
            assignment_ids = [a.id for a in assignments]
            submissions = await db.execute(
                select(models.AssignmentSubmission)
                .where(and_(
                    models.AssignmentSubmission.student_id == student.id,
                    models.AssignmentSubmission.material_id.in_(assignment_ids)
                ))
            )
            submissions = submissions.scalars().all()
            submission_status = {sub.material_id: sub.status for sub in submissions}

    return templates.TemplateResponse(
        "assignments/list.html",
        {
            "request": request,
            "current_user": current_user,
            "subject": subject,
            "assignments": assignments,
            "current_time": datetime.now(),
            "submission_status": submission_status,  # Добавляем статусы в контекст
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success")
        }
    )


@router.get("/{assignment_id}", response_class=HTMLResponse, name="assignment_detail")
async def assignment_detail(
        request: Request,
        subject_id: int,
        assignment_id: int,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = await get_subject_with_groups(db, subject_id, current_user)
    assignment = await get_assignment_with_submissions(db, assignment_id, current_user)

    user_submission = None
    if current_user.role == "student":
        # Найти студента
        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()
        if student:
            # Найти отправку студента
            submission = await db.execute(
                select(models.AssignmentSubmission)
                .where(and_(
                    models.AssignmentSubmission.material_id == assignment_id,
                    models.AssignmentSubmission.student_id == student.id
                ))
            )
            user_submission = submission.scalar()

    return templates.TemplateResponse(
        "assignments/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "subject": subject,
            "assignment": assignment,
            "user_submission": user_submission,  # Передаем отправку студента
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
        select(Submission)
        .where(Submission.id == submission_id)
    )
    submission = submission.scalar()

    if not submission or submission.material_id != assignment_id:
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
        select(Submission)
        .where(and_(
            Submission.student_id == student.id,
            Submission.material_id == assignment_id
        ))
    )
    existing = existing.scalar()

    if existing:
        existing.file_path = str(file_path)
        existing.submission_date = datetime.now()
        existing.status = "submitted"
    else:
        submission = models.AssignmentSubmission(
            student_id=student.id,
            material_id=assignment_id,
            file_path=str(file_path),
            status="submitted"
        )
        db.add(submission)

    await db.commit()
    return RedirectResponse(
        f"/subjects/{subject_id}/assignments/{assignment_id}",
        status_code=303
    )


@router.post("/", response_class=RedirectResponse)
async def create_assignment(
        subject_id: int,
        request: Request,
        title: str = Form(...),
        description: str = Form(None),
        group_id: int = Form(...),
        deadline: datetime = Form(...),
        file: UploadFile = File(None),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    try:
        subject = await get_subject_with_groups(db, subject_id, current_user)

        # Сохранение файла
        file_path = None
        if file and file.filename:
            file_dir = Path(UPLOAD_DIR) / f"subject_{subject_id}"
            file_dir.mkdir(parents=True, exist_ok=True)

            file_name = f"{uuid.uuid4()}{Path(file.filename).suffix}"
            file_path = file_dir / file_name

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

        new_assignment = models.CourseMaterial(
            title=title,
            description=description,
            type="assignment",
            file_path=str(file_path) if file_path else None,
            subject_id=subject_id,
            group_id=group_id,
            deadline=deadline,
            created_at=datetime.now()
        )

        db.add(new_assignment)
        await db.commit()

        return RedirectResponse(
            f"/subjects/{subject_id}/assignments?success={title}",
            status_code=303
        )

    except Exception as e:
        logger.error(f"Error creating assignment: {str(e)}")
        return RedirectResponse(
            f"/subjects/{subject_id}/assignments?error={str(e)}",
            status_code=303
        )