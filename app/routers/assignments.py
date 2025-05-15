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
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from pathlib import Path
import shutil
import uuid
from datetime import datetime
from typing import Optional
import logging
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.models import models
from app.schemas import schemas
from app import database
from app.auth import get_current_user
from app.dependencies import templates
from sqlalchemy import text
from sqlalchemy import cast, String
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

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

    # Проверка прав для преподавателя и студента
    if user.role == "teacher":
        teacher = await db.execute(
            select(models.Teacher)
            .where(models.Teacher.user_id == user.id)
        )
        teacher = teacher.scalar()
        if not teacher or subject.teacher_id != teacher.user_id:
            raise HTTPException(403, "Forbidden")
    elif user.role == "student":
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
            .selectinload(models.AssignmentSubmission.student)
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
            "submission_status": submission_status,
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
        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()
        if student:
            submission = await db.execute(
                select(models.AssignmentSubmission)
                .where(and_(
                    models.AssignmentSubmission.material_id == assignment_id,
                    models.AssignmentSubmission.student_id == student.id)
                ))
            user_submission = submission.scalar()

    return templates.TemplateResponse(
        "assignments/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "subject": subject,
            "assignment": assignment,
            "user_submission": user_submission,
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
    await get_subject_with_groups(db, subject_id, current_user)

    submission = await db.execute(
        select(models.AssignmentSubmission)
        .where(models.AssignmentSubmission.id == submission_id)
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

@router.post("/{assignment_id}/submit", response_class=RedirectResponse)
async def submit_assignment(
    subject_id: int,
    assignment_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        if current_user.role != "student":
            raise HTTPException(403, "Только студенты могут отправлять задания")

        assignment = await db.execute(
            select(models.CourseMaterial)
            .options(selectinload(models.CourseMaterial.group))
            .where(models.CourseMaterial.id == assignment_id)
        )
        assignment = assignment.scalar()

        if not assignment:
            raise HTTPException(404, "Задание не найдено")

        if assignment.deadline < datetime.now():
            raise HTTPException(400, "Срок сдачи задания истек")

        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()

        if not student or student.group_id != assignment.group_id:
            raise HTTPException(403, "Вы не состоите в нужной группе")

        existing_submission = await db.execute(
            select(models.AssignmentSubmission)
            .where(and_(
                models.AssignmentSubmission.student_id == student.id,
                models.AssignmentSubmission.material_id == assignment_id)
            ))
        existing = existing_submission.scalar()

        student_dir = Path(UPLOAD_DIR) / f"subject_{subject_id}/assignments/assignment_{assignment_id}/student_{student.id}"
        student_dir.mkdir(parents=True, exist_ok=True)

        file_ext = Path(file.filename).suffix
        file_name = f"submission_{uuid.uuid4()}{file_ext}"
        file_path = student_dir / file_name

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if existing:
            existing.file_path = str(file_path.relative_to(UPLOAD_DIR))
            existing.submission_date = datetime.now()
            existing.status = "submitted"
        else:
            submission = models.AssignmentSubmission(
                student_id=student.id,
                material_id=assignment_id,
                file_path=str(file_path.relative_to(UPLOAD_DIR)),
                status="submitted",
                submission_date=datetime.now()
            )
            db.add(submission)

        await db.commit()
        return RedirectResponse(
            f"/subjects/{subject_id}/assignments/{assignment_id}?success=Файл успешно отправлен",
            status_code=303
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Assignment submission error: {str(e)}")
        return RedirectResponse(
            f"/subjects/{subject_id}/assignments/{assignment_id}?error=Ошибка отправки файла",
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
        # Проверка прав преподавателя
        subject = await get_subject_with_groups(db, subject_id, current_user)

        # Проверка дедлайна
        if deadline < datetime.now():
            return RedirectResponse(
                f"/subjects/{subject_id}/assignments?error=Дедлайн должен быть в будущем",
                status_code=303
            )

        # Создаем запись задания
        new_assignment = models.CourseMaterial(
            title=title,
            description=description,
            type="assignment",
            file_path="",  # Временное значение
            subject_id=subject_id,
            group_id=group_id,
            deadline=deadline,
            created_at=datetime.now()
        )

        db.add(new_assignment)
        await db.commit()
        await db.refresh(new_assignment)

        # Создаем директорию для задания
        assignment_dir = Path(UPLOAD_DIR) / f"subject_{subject_id}/assignments/assignment_{new_assignment.id}"
        assignment_dir.mkdir(parents=True, exist_ok=True)

        # Обработка файла
        if file and file.filename:
            file_ext = Path(file.filename).suffix
            file_name = f"assignment_{uuid.uuid4()}{file_ext}"
        else:
            file_name = f"assignment_{uuid.uuid4()}.txt"
            content = f"Название: {title}\nОписание: {description}\nДедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}"

        file_path = assignment_dir / file_name

        # Сохраняем файл
        if file and file.filename:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        # Обновляем путь к файлу
        new_assignment.file_path = str(file_path.relative_to(UPLOAD_DIR))
        await db.commit()

        return RedirectResponse(
            f"/subjects/{subject_id}/assignments?success=Задание успешно создано",
            status_code=303
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Assignment creation error: {str(e)}")
        return RedirectResponse(
            f"/subjects/{subject_id}/assignments?error=Ошибка создания задания",
            status_code=303
        )


@router.get("/download/{material_id}")
async def download_assignment_file(
        subject_id: int,
        material_id: int,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    assignment = await db.execute(
        select(models.CourseMaterial)
        .where(models.CourseMaterial.id == material_id)
    )
    assignment = assignment.scalar()

    if not assignment or not assignment.file_path:
        raise HTTPException(404, "File not found")

    # Проверка прав доступа
    await get_subject_with_groups(db, subject_id, current_user)

    file_path = Path(UPLOAD_DIR) / assignment.file_path
    if not file_path.exists():
        raise HTTPException(404, "File not found")

    return FileResponse(
        file_path,
        filename=f"{assignment.title}{file_path.suffix}",
        media_type="application/octet-stream"
    )


@router.get("/submissions/{submission_id}/download")
async def download_submission_file(
        subject_id: int,
        submission_id: int,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    try:
        # Асинхронно получаем данные отправки
        submission = await db.execute(
            select(models.AssignmentSubmission)
            .options(
                selectinload(models.AssignmentSubmission.material)
                .selectinload(models.CourseMaterial.subject)
                .selectinload(models.Subject.teacher),
                selectinload(models.AssignmentSubmission.student)
                .selectinload(models.Student.user)
            )
            .where(models.AssignmentSubmission.id == submission_id)
        )
        submission = submission.scalar()

        if not submission or not submission.file_path:
            raise HTTPException(404, "File not found")

        # Проверка прав преподавателя
        if current_user.role == "teacher":
            if submission.material.subject.teacher.user_id != current_user.id:
                raise HTTPException(403, "Access denied")

        # Асинхронная проверка существования файла
        full_path = Path(UPLOAD_DIR) / submission.file_path
        if not await run_in_threadpool(full_path.exists):
            raise HTTPException(404, "File not found")

        return FileResponse(
            str(full_path),
            filename=f"Submission_{submission.student.user.first_name}_{submission.student.user.last_name}{full_path.suffix}"
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        raise HTTPException(500, "Internal server error")

@router.post("/{assignment_id}/delete", response_class=RedirectResponse)
async def delete_assignment(
    subject_id: int,
    assignment_id: int,
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        # Проверка прав преподавателя
        subject = await get_subject_with_groups(db, subject_id, current_user)
        if current_user.role != "teacher":
            raise HTTPException(403, "Forbidden")

        # Получаем задание
        assignment = await db.execute(
            select(models.CourseMaterial)
            .where(models.CourseMaterial.id == assignment_id)
        )
        assignment = assignment.scalar()

        if not assignment or assignment.subject_id != subject_id:
            raise HTTPException(404, "Assignment not found")

        # Удаление файлов задания и всех сдач
        assignment_dir = Path(UPLOAD_DIR) / f"subject_{subject_id}/assignments/assignment_{assignment_id}"
        if assignment_dir.exists():
            shutil.rmtree(assignment_dir)

        # Удаление из БД
        await db.delete(assignment)
        await db.commit()

        return RedirectResponse(
            f"/subjects/{subject_id}/assignments?success=Задание+удалено",
            status_code=303
        )

    except HTTPException as e:
        return RedirectResponse(
            f"/subjects/{subject_id}/assignments?error={e.detail}",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error deleting assignment: {str(e)}")
        return RedirectResponse(
            f"/subjects/{subject_id}/assignments?error=Ошибка+удаления",
            status_code=303
        )