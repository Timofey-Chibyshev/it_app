
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
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pathlib import Path
import sys
import shutil
import uuid
# Добавляем путь к корневой директории проекта
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))
from datetime import datetime

from app.models import models
from app.schemas import schemas
from app import database
from app.auth import get_current_user
from app.dependencies import templates
import logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/subjects",
    tags=["subjects"],
    responses={404: {"description": "Not found"}}
)


@router.get("/api/my", response_model=list[schemas.SubjectResponse])
async def get_my_subjects(
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    if current_user.role == "teacher":
        result = await db.execute(
            select(models.Subject)
            .join(models.Teacher)
            .options(
                selectinload(models.Subject.groups),
                selectinload(models.Subject.teacher)
            )
            .where(models.Teacher.user_id == current_user.id)
        )
        return result.scalars().all()

    # Для студентов
    student = (await db.execute(
        select(models.Student)
        .where(models.Student.user_id == current_user.id)
        .options(selectinload(models.Student.group))
    )).scalar()

    if not student or not student.group:
        raise HTTPException(status_code=403, detail="Student not in group")

    return student.group.subjects


@router.post("/", response_model=schemas.SubjectResponse)
async def create_subject(
        subject_data: schemas.SubjectCreate,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create subjects")

    existing_subject = (await db.execute(
        select(models.Subject)
        .where(func.lower(models.Subject.name) == func.lower(subject_data.name))
    )).scalar()

    if existing_subject:
        raise HTTPException(status_code=400, detail="Subject already exists")

    new_subject = models.Subject(
        **subject_data.dict(exclude={"groups"}),
        teacher_id=current_user.id
    )

    if subject_data.groups:
        groups = (await db.execute(
            select(models.Group)
            .where(models.Group.id.in_(subject_data.groups))
        )).scalars().all()
        new_subject.groups = groups

    db.add(new_subject)
    await db.commit()
    await db.refresh(new_subject)
    return new_subject


# -------------------------------
# HTML Endpoints
# -------------------------------

@router.get("/my", response_class=HTMLResponse)
async def subjects_list_page(
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subjects = await get_my_subjects(db, current_user)

    context = {
        "request": request,
        "current_user": current_user,
        "subjects": subjects
    }

    if current_user.role == "teacher":
        context.update({
            "total_subjects": len(subjects),
            "total_groups": sum(len(s.groups) for s in subjects),
            "template": "teacher"
        })
        template = "subjects/teacher_list.html"
    else:
        for subject in subjects:
            subject.active_assignments = [a for a in subject.assignments if a.is_active]
        context.update({"template": "student"})
        template = "subjects/student_list.html"

    return templates.TemplateResponse(template, context)


@router.get("/create", response_class=HTMLResponse)
async def create_subject_page(
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Forbidden")

    groups = (await db.execute(select(models.Group))).scalars().all()
    return templates.TemplateResponse(
        "subjects/create.html",
        {"request": request, "current_user": current_user, "groups": groups}
    )


@router.post("/create", response_class=HTMLResponse)
async def handle_create_subject(
        request: Request,
        name: str = Form(...),
        # description: str = Form(...),
        type: str = Form(...),  # Исправлено имя параметра
        groups: list[int] = Form([]),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    try:
        subject_data = schemas.SubjectCreate(
            name=name,
            # description=description,
            type=type,
            groups=groups
        )
        subject = await create_subject(subject_data, db, current_user)
        return RedirectResponse(f"/subjects/{subject.id}", status_code=303)

    except HTTPException as e:
        groups = (await db.execute(select(models.Group))).scalars().all()
        return templates.TemplateResponse(
            "subjects/create.html",
            {
                "request": request,
                "current_user": current_user,
                "groups": groups,
                "error": str(e.detail),
                "form_data": request.form()
            },
            status_code=e.status_code
        )


@router.get("/{subject_id}", response_class=HTMLResponse)
async def subject_detail_page(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = (await db.execute(
        select(models.Subject)
        .options(
            selectinload(models.Subject.groups),
            selectinload(models.Subject.teacher),
            selectinload(models.Subject.materials)
        )
        .where(models.Subject.id == subject_id)
    )).scalar()

    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Проверка доступа для студентов
    if current_user.role == "student":
        student = (await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
            .options(selectinload(models.Student.group))
        )).scalar()

        if not student or student.group_id not in [g.id for g in subject.groups]:
            raise HTTPException(status_code=403, detail="Access denied")

    return templates.TemplateResponse(
        "subjects/detail.html",
        {
            "request": request,
            "subject": subject,
            "current_user": current_user,
            "is_teacher": current_user.role == "teacher",
            "materials": subject.materials,
            "groups": subject.groups
        }
    )
