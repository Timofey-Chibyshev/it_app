from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Form,
    status
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pathlib import Path
import sys

# Добавляем путь к корневой директории проекта
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from app.models import models
from app.schemas import schemas
from app import database
from app.auth import get_current_user
from app.dependencies import templates

router = APIRouter(
    prefix="/subjects",
    tags=["subjects"],
    responses={404: {"description": "Not found"}}
)


# -----------------------------------------------
#                  API Endpoints
# -----------------------------------------------

@router.get("/my", response_model=list[schemas.SubjectResponse])
async def get_my_subjects(
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """
    Получение списка предметов для текущего пользователя
    """
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
    result = await db.execute(
        select(models.Student)
        .where(models.Student.user_id == current_user.id)
        .options(
            selectinload(models.Student.group)
            .selectinload(models.Group.subjects)
            .selectinload(models.Subject.teacher)
        )
    )
    student = result.scalar()

    if not student or not student.group:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student is not assigned to a group"
        )

    return student.group.subjects


@router.post("/", response_model=schemas.SubjectResponse)
async def create_subject(
        subject_data: schemas.SubjectCreate,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """
    Создание нового предмета (только для преподавателей)
    """
    if current_user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can create subjects"
        )

    # Проверяем, существует ли уже предмет с таким названием
    existing_subject = await db.execute(
        select(models.Subject)
        .where(func.lower(models.Subject.name) == func.lower(subject_data.name))
    )
    if existing_subject.scalar():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subject with this name already exists"
        )

    new_subject = models.Subject(
        **subject_data.dict(exclude={"groups"}),
        teacher_id=current_user.id
    )

    # Добавляем группы к предмету
    if subject_data.groups:
        groups = await db.execute(
            select(models.Group)
            .where(models.Group.id.in_(subject_data.groups))
        )
        new_subject.groups = groups.scalars().all()

    db.add(new_subject)
    await db.commit()
    await db.refresh(new_subject)
    return new_subject


# -----------------------------------------------
#                  HTML Endpoints
# -----------------------------------------------

@router.get("/my", response_class=HTMLResponse)
async def subjects_list_page(
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """
    Отображение списка предметов в зависимости от роли пользователя
    """
    subjects = await get_my_subjects(db, current_user)

    template_context = {
        "request": request,
        "current_user": current_user,
        "subjects": subjects
    }

    if current_user.role == "teacher":
        # Дополнительные данные для преподавателя
        total_groups = sum(len(subject.groups) for subject in subjects)
        template_context.update({
            "total_subjects": len(subjects),
            "total_groups": total_groups,
            "template": "teacher"
        })
        template_name = "subjects/teacher_list.html"
    else:
        # Дополнительные данные для студента
        for subject in subjects:
            subject.active_assignments = [
                a for a in subject.assignments if a.is_active
            ]
        template_context.update({
            "template": "student"
        })
        template_name = "subjects/student_list.html"

    return templates.TemplateResponse(
        template_name,
        template_context
    )


@router.get("/create", response_class=HTMLResponse)
async def create_subject_page(
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """
    Страница создания нового предмета
    """
    if current_user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Получаем список всех групп
    groups = await db.execute(select(models.Group))
    groups = groups.scalars().all()

    return templates.TemplateResponse(
        "subjects/create.html",
        {
            "request": request,
            "current_user": current_user,
            "groups": groups
        }
    )


@router.post("/create", response_class=HTMLResponse)
async def handle_create_subject(
        request: Request,
        name: str = Form(...),
        description: str = Form(...),
        groups: list[int] = Form(None),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """
    Обработка формы создания предмета
    """
    try:
        subject_data = schemas.SubjectCreate(
            name=name,
            description=description,
            groups=groups or []
        )

        subject = await create_subject(subject_data, db, current_user)
        return RedirectResponse(
            url=f"/subjects/{subject.id}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    except HTTPException as e:
        error_message = e.detail
        groups = await db.execute(select(models.Group))
        return templates.TemplateResponse(
            "subjects/create.html",
            {
                "request": request,
                "current_user": current_user,
                "groups": groups.scalars().all(),
                "error_message": error_message,
                "form_data": {
                    "name": name,
                    "description": description,
                    "groups": groups
                }
            },
            status_code=e.status_code
        )


# -----------------------------------------------
#                  Дополнительные функции
# -----------------------------------------------

@router.get("/{subject_id}", response_class=HTMLResponse)
async def subject_detail_page(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """
    Детальная страница предмета
    """
    subject = await db.execute(
        select(models.Subject)
        .options(
            selectinload(models.Subject.groups),
            selectinload(models.Subject.assignments),
            selectinload(models.Subject.teacher)
        )
        .where(models.Subject.id == subject_id)
    )
    subject = subject.scalar()

    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Проверка доступа
    if current_user.role == "student":
        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()
        if not student or student.group_id not in [g.id for g in subject.groups]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

    return templates.TemplateResponse(
        "subjects/detail.html",
        {
            "request": request,
            "subject": subject,
            "current_user": current_user,
            "is_teacher": current_user.role == "teacher"
        }
    )