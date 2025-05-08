# from fastapi import (
#     APIRouter,
#     Depends,
#     HTTPException,
#     Request,
#     Form,
#     status
# )
# from fastapi.responses import HTMLResponse, RedirectResponse
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select, func
# from sqlalchemy.orm import selectinload
# from pathlib import Path
# import sys
#
# # Добавляем путь к корневой директории проекта
# sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))
#
# from app.models import models
# from app.schemas import schemas
# from app import database
# from app.auth import get_current_user
# from app.dependencies import templates
#
# router = APIRouter(
#     prefix="/subjects",
#     tags=["subjects"],
#     responses={404: {"description": "Not found"}}
# )
#
#
# # -----------------------------------------------
# #                  API Endpoints
# # -----------------------------------------------
#
# @router.get("/my", response_model=list[schemas.SubjectResponse])
# async def get_my_subjects(
#         db: AsyncSession = Depends(database.get_db),
#         current_user: models.User = Depends(get_current_user)
# ):
#     """
#     Получение списка предметов для текущего пользователя
#     """
#     if current_user.role == "teacher":
#         result = await db.execute(
#             select(models.Subject)
#             .join(models.Teacher)
#             .options(
#                 selectinload(models.Subject.groups),
#                 selectinload(models.Subject.teacher)
#             )
#             .where(models.Teacher.user_id == current_user.id)
#         )
#         return result.scalars().all()
#
#     # Для студентов
#     result = await db.execute(
#         select(models.Student)
#         .where(models.Student.user_id == current_user.id)
#         .options(
#             selectinload(models.Student.group)
#             .selectinload(models.Group.subjects)
#             .selectinload(models.Subject.teacher)
#         )
#     )
#     student = result.scalar()
#
#     if not student or not student.group:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Student is not assigned to a group"
#         )
#
#     return student.group.subjects
#
#
# @router.post("/", response_model=schemas.SubjectResponse)
# async def create_subject(
#         subject_data: schemas.SubjectCreate,
#         db: AsyncSession = Depends(database.get_db),
#         current_user: models.User = Depends(get_current_user)
# ):
#     """
#     Создание нового предмета (только для преподавателей)
#     """
#     if current_user.role != "teacher":
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Only teachers can create subjects"
#         )
#
#     # Проверяем, существует ли уже предмет с таким названием
#     existing_subject = await db.execute(
#         select(models.Subject)
#         .where(func.lower(models.Subject.name) == func.lower(subject_data.name))
#     )
#     if existing_subject.scalar():
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Subject with this name already exists"
#         )
#
#     new_subject = models.Subject(
#         **subject_data.dict(exclude={"groups"}),
#         teacher_id=current_user.id
#     )
#
#     # Добавляем группы к предмету
#     if subject_data.groups:
#         groups = await db.execute(
#             select(models.Group)
#             .where(models.Group.id.in_(subject_data.groups))
#         )
#         new_subject.groups = groups.scalars().all()
#
#     db.add(new_subject)
#     await db.commit()
#     await db.refresh(new_subject)
#     return new_subject
#
#
# # -----------------------------------------------
# #                  HTML Endpoints
# # -----------------------------------------------
#
# @router.get("/my", response_class=HTMLResponse)
# async def subjects_list_page(
#         request: Request,
#         db: AsyncSession = Depends(database.get_db),
#         current_user: models.User = Depends(get_current_user)
# ):
#     """
#     Отображение списка предметов в зависимости от роли пользователя
#     """
#     subjects = await get_my_subjects(db, current_user)
#
#     template_context = {
#         "request": request,
#         "current_user": current_user,
#         "subjects": subjects
#     }
#
#     if current_user.role == "teacher":
#         # Дополнительные данные для преподавателя
#         total_groups = sum(len(subject.groups) for subject in subjects)
#         template_context.update({
#             "total_subjects": len(subjects),
#             "total_groups": total_groups,
#             "template": "teacher"
#         })
#         template_name = "subjects/teacher_list.html"
#     else:
#         # Дополнительные данные для студента
#         for subject in subjects:
#             subject.active_assignments = [
#                 a for a in subject.assignments if a.is_active
#             ]
#         template_context.update({
#             "template": "student"
#         })
#         template_name = "subjects/student_list.html"
#
#     return templates.TemplateResponse(
#         template_name,
#         template_context
#     )
#
#
# @router.get("/create", response_class=HTMLResponse)
# async def create_subject_page(
#         request: Request,
#         db: AsyncSession = Depends(database.get_db),
#         current_user: models.User = Depends(get_current_user)
# ):
#     """
#     Страница создания нового предмета
#     """
#     if current_user.role != "teacher":
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Access denied"
#         )
#
#     # Получаем список всех групп
#     groups = await db.execute(select(models.Group))
#     groups = groups.scalars().all()
#
#     return templates.TemplateResponse(
#         "subjects/create.html",
#         {
#             "request": request,
#             "current_user": current_user,
#             "groups": groups
#         }
#     )
#
#
# @router.post("/create", response_class=HTMLResponse)
# async def handle_create_subject(
#         request: Request,
#         name: str = Form(...),
#         description: str = Form(...),
#         groups: list[int] = Form(None),
#         db: AsyncSession = Depends(database.get_db),
#         current_user: models.User = Depends(get_current_user)
# ):
#     """
#     Обработка формы создания предмета
#     """
#     try:
#         subject_data = schemas.SubjectCreate(
#             name=name,
#             description=description,
#             groups=groups or []
#         )
#
#         subject = await create_subject(subject_data, db, current_user)
#         return RedirectResponse(
#             url=f"/subjects/{subject.id}",
#             status_code=status.HTTP_303_SEE_OTHER
#         )
#
#     except HTTPException as e:
#         error_message = e.detail
#         groups = await db.execute(select(models.Group))
#         return templates.TemplateResponse(
#             "subjects/create.html",
#             {
#                 "request": request,
#                 "current_user": current_user,
#                 "groups": groups.scalars().all(),
#                 "error_message": error_message,
#                 "form_data": {
#                     "name": name,
#                     "description": description,
#                     "groups": groups
#                 }
#             },
#             status_code=e.status_code
#         )
#
#
# # -----------------------------------------------
# #                  Дополнительные функции
# # -----------------------------------------------
#
# @router.get("/{subject_id}", response_class=HTMLResponse)
# async def subject_detail_page(
#         subject_id: int,
#         request: Request,
#         db: AsyncSession = Depends(database.get_db),
#         current_user: models.User = Depends(get_current_user)
# ):
#     """
#     Детальная страница предмета
#     """
#     subject = await db.execute(
#         select(models.Subject)
#         .options(
#             selectinload(models.Subject.groups),
#             selectinload(models.Subject.assignments),
#             selectinload(models.Subject.teacher)
#         )
#         .where(models.Subject.id == subject_id)
#     )
#     subject = subject.scalar()
#
#     if not subject:
#         raise HTTPException(status_code=404, detail="Subject not found")
#
#     # Проверка доступа
#     if current_user.role == "student":
#         student = await db.execute(
#             select(models.Student)
#             .where(models.Student.user_id == current_user.id)
#         )
#         student = student.scalar()
#         if not student or student.group_id not in [g.id for g in subject.groups]:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Access denied"
#             )
#
#     return templates.TemplateResponse(
#         "subjects/detail.html",
#         {
#             "request": request,
#             "subject": subject,
#             "current_user": current_user,
#             "is_teacher": current_user.role == "teacher"
#         }
#     )

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
import logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/subjects",
    tags=["subjects"],
    responses={404: {"description": "Not found"}}
)


# -----------------------------------------------
#                  API Endpoints
# -----------------------------------------------

@router.get("/api/my", response_model=list[schemas.SubjectResponse])
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
            .join(
                models.Teacher,
                models.Subject.teacher_id == models.Teacher.user_id  # Явное условие соединения
            )
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
    subject = await db.execute(
        select(models.Subject)
        .options(
            selectinload(models.Subject.groups),
            selectinload(models.Subject.teacher),
            selectinload(models.Subject.materials)
            .selectinload(models.CourseMaterial.submissions),
            selectinload(models.Subject.schedule)
        )
        .where(models.Subject.id == subject_id)
    )
    subject = subject.scalar()

    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Проверка доступа для студентов
    if current_user.role == "student":
        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()

        if not student or student.group_id not in [g.id for g in subject.groups]:
            raise HTTPException(status_code=403, detail="Access denied")

    return templates.TemplateResponse(
        "subjects/detail.html",
        {
            "request": request,
            "subject": subject,
            "current_user": current_user,
            "is_teacher": current_user.role == "teacher"
        }
    )


UPLOAD_DIR = "uploads"
Path(UPLOAD_DIR).mkdir(exist_ok=True)
from datetime import datetime


@router.get("/{subject_id}/materials", response_class=HTMLResponse)
async def materials_page(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    try:
        # Проверка существования предмета
        subject = await db.execute(
            select(models.Subject)
            .options(
                selectinload(models.Subject.teacher),
                selectinload(models.Subject.groups),
                selectinload(models.Subject.materials)
                .selectinload(models.CourseMaterial.submissions)
            )
            .where(models.Subject.id == subject_id)
        )
        subject = subject.scalar()

        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")

        # Проверка прав доступа
        if current_user.role != "teacher" or subject.teacher.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Forbidden")

        # Получение групп предмета
        groups = subject.groups

        # Получение параметров запроса
        error = request.query_params.get("error")
        success = request.query_params.get("success")

        return templates.TemplateResponse(
            "subjects/materials.html",
            {
                "request": request,
                "subject": subject,
                "groups": groups,
                "materials": subject.materials,
                "current_time": datetime.now(),
                "error": error,
                "success": success
            }
        )

    except HTTPException as e:
        error_context = {
            "request": request,
            "status_code": e.status_code,
            "detail": e.detail
        }
        return templates.TemplateResponse(
            "error.html",
            error_context,
            status_code=e.status_code
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "status_code": 500,
                "detail": "Internal Server Error"
            },
            status_code=500
        )


from fastapi import UploadFile, File
import shutil
import os
import uuid

@router.post("/{subject_id}/materials")
async def create_material(
        subject_id: int,
        request: Request,
        file: UploadFile = File(...),
        material_type: str = Form(...),
        group_id: int = Form(...),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    try:
        # Проверка прав
        subject = await get_subject_with_check(db, subject_id, current_user)

        # Создание папки для загрузок
        upload_dir = Path(UPLOAD_DIR) / f"subject_{subject_id}" / f"group_{group_id}"
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Генерация уникального имени файла
        file_ext = Path(file.filename).suffix
        unique_name = f"{uuid.uuid4()}{file_ext}"
        file_path = upload_dir / unique_name

        # Сохранение файла
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Запись в БД
        new_material = models.CourseMaterial(
            title=file.filename,
            type=material_type,
            file_path=str(file_path),
            subject_id=subject_id,
            group_id=group_id
        )
        db.add(new_material)
        await db.commit()

        # Перенаправление с сообщением об успехе
        return RedirectResponse(
            request.url_for("materials_page", subject_id=subject_id),
            status_code=303,
            headers={"success": file.filename}
        )

    except Exception as e:
        # Перенаправление с сообщением об ошибке
        return RedirectResponse(
            request.url_for("materials_page", subject_id=subject_id),
            status_code=303,
            headers={"error": str(e)}
        )


@router.get("/{subject_id}/submissions", response_class=HTMLResponse)
async def subject_submissions_page(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """
    Страница с заданиями студентов
    """
    subject = await get_subject_with_check(db, subject_id, current_user)

    # Получаем все материалы с заданиями
    materials = await db.execute(
        select(models.CourseMaterial)
        .options(selectinload(models.CourseMaterial.submissions))
        .where(
            models.CourseMaterial.subject_id == subject_id,
            models.CourseMaterial.type == 'assignment'
        )
    )
    materials = materials.scalars().all()

    return templates.TemplateResponse(
        "subjects/teacher_submissions.html",
        {
            "request": request,
            "subject": subject,
            "current_user": current_user,
            "materials": materials
        }
    )


@router.post("/submissions/{submission_id}/grade")
async def grade_submission(
        submission_id: int,
        grade: int = Form(...),
        feedback: str = Form(None),
        status: str = Form(...),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """
    Оценка задания студента
    """
    submission = await db.execute(
        select(models.AssignmentSubmission)
        .options(selectinload(models.AssignmentSubmission.material))
        .where(models.AssignmentSubmission.id == submission_id)
    )
    submission = submission.scalar()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Проверка что преподаватель ведет предмет
    subject = await db.execute(
        select(models.Subject)
        .where(models.Subject.id == submission.material.subject_id)
    )
    subject = subject.scalar()

    if subject.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    submission.grade = grade
    submission.feedback = feedback
    submission.status = status

    await db.commit()

    return RedirectResponse(
        url=f"/subjects/{subject.id}/submissions",
        status_code=303
    )


async def get_subject_with_check(db: AsyncSession, subject_id: int, user: models.User):
    """
    Вспомогательная функция для проверки прав доступа к предмету
    """
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
        raise HTTPException(status_code=404, detail="Subject not found")

    if user.role != "teacher" or subject.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return subject


@router.get("/my", response_class=HTMLResponse)
async def subjects_list_page(
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """Главная страница списка предметов"""
    try:
        logger.info("Starting subjects list processing")
        if current_user.role == "teacher":
            # Загрузка предметов с группами и преподавателем
            result = await db.execute(
                select(models.Subject)
                .options(
                    selectinload(models.Subject.groups),
                    selectinload(models.Subject.teacher)
                )
                .where(models.Subject.teacher_id == current_user.id)
            )
            subjects = result.scalars().all()

            # Статистика для преподавателя
            total_groups = sum(len(subject.groups) for subject in subjects)
            logger.debug(f"Loaded subjects: {subjects}")
            return templates.TemplateResponse(
                "subjects/teacher_list.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "subjects": subjects,
                    "total_subjects": len(subjects),
                    "total_groups": total_groups
                }
            )

        # Логика для студентов
        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
            .options(selectinload(models.Student.group))
        )
        student = student.scalar()

        if not student or not student.group:
            raise HTTPException(status_code=403, detail="Student not in group")

        return templates.TemplateResponse(
            "subjects/student_list.html",
            {
                "request": request,
                "current_user": current_user,
                "subjects": student.group.subjects
            }
        )

    except Exception as e:
        logger.error(f"Error in subjects list: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/create", response_class=HTMLResponse)
async def create_subject_page(
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """Страница создания предмета"""
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Forbidden")

    groups = await db.execute(select(models.Group))
    return templates.TemplateResponse(
        "subjects/create.html",
        {
            "request": request,
            "current_user": current_user,
            "groups": groups.scalars().all()
        }
    )
@router.get("/{subject_id}", response_class=HTMLResponse)
async def subject_detail_page(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """Детальная страница предмета"""
    subject = await db.execute(
        select(models.Subject)
        .options(
            selectinload(models.Subject.groups),
            selectinload(models.Subject.materials),
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
            .options(selectinload(models.Student.group))
        )
        student = student.scalar()
        if not student or student.group_id not in [g.id for g in subject.groups]:
            raise HTTPException(status_code=403, detail="Access denied")

    return templates.TemplateResponse(
        "subjects/detail.html",
        {
            "request": request,
            "subject": subject,
            "current_user": current_user,
            "materials": subject.materials,
            "groups": subject.groups
        }
    )

@router.post("/create", response_class=HTMLResponse)
async def handle_create_subject(
        request: Request,
        name: str = Form(...),
        subject_type: str = Form(...),
        groups: list[int] = Form([]),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    """Обработка создания предмета"""
    try:
        # Создаем предмет
        new_subject = models.Subject(
            name=name,
            type=subject_type,
            teacher_id=current_user.id
        )

        # Привязываем группы
        if groups:
            result = await db.execute(
                select(models.Group).where(models.Group.id.in_(groups))
            )
            new_subject.groups = result.scalars().all()

        db.add(new_subject)
        await db.commit()

        return RedirectResponse(
            url=f"/subjects/{new_subject.id}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    except Exception as e:
        await db.rollback()
        groups = await db.execute(select(models.Group))
        return templates.TemplateResponse(
            "subjects/create.html",
            {
                "request": request,
                "current_user": current_user,
                "groups": groups.scalars().all(),
                "error": f"Ошибка: {str(e)}",
                "form_data": request.form()
            },
            status_code=400
        )


from pathlib import Path
import shutil
import os
from datetime import datetime

UPLOAD_DIR = "uploads"
Path(UPLOAD_DIR).mkdir(exist_ok=True)


async def get_subject_with_check(db: AsyncSession, subject_id: int, user: models.User):
    """Проверка прав доступа к предмету"""
    subject = await db.execute(
        select(models.Subject)
        .options(selectinload(models.Subject.teacher))
        .where(models.Subject.id == subject_id)
    )
    subject = subject.scalar()

    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    if user.role != "teacher" or subject.teacher.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return subject


@router.get("/{subject_id}/materials", response_class=HTMLResponse)
async def materials_page(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = await get_subject_with_check(db, subject_id, current_user)

    # Получаем материалы с группами
    materials = await db.execute(
        select(models.CourseMaterial)
        .options(
            selectinload(models.CourseMaterial.group),
            selectinload(models.CourseMaterial.submissions)
        )
        .where(models.CourseMaterial.subject_id == subject_id)
    )

    return templates.TemplateResponse(
        "subjects/materials.html",
        {
            "request": request,
            "subject": subject,
            "materials": materials.scalars().all(),
            "groups": subject.groups,
            "current_time": datetime.now()
        }
    )


@router.post("/{subject_id}/materials")
async def create_material(
        subject_id: int,
        request: Request,
        title: str = Form(...),
        description: str = Form(None),
        material_type: str = Form(...),
        group_id: int = Form(...),
        deadline: datetime = Form(None),
        file: UploadFile = File(...),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = await get_subject_with_check(db, subject_id, current_user)

    # Валидация дедлайна
    if material_type == "assignment" and not deadline:
        raise HTTPException(
            status_code=400,
            detail="Deadline is required for assignments"
        )

    # Сохранение файла
    file_dir = Path(UPLOAD_DIR) / f"subject_{subject_id}" / f"group_{group_id}"
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / file.filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Создание материала
    new_material = models.CourseMaterial(
        title=title,
        description=description,
        type=material_type,
        file_path=str(file_path),
        subject_id=subject_id,
        group_id=group_id,
        deadline=deadline
    )

    db.add(new_material)
    await db.commit()

    return RedirectResponse(
        url=f"/subjects/{subject_id}/materials",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{subject_id}/submissions", response_class=HTMLResponse)
async def view_submissions(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = await get_subject_with_check(db, subject_id, current_user)

    # Получаем все сдачи по предмету
    submissions = await db.execute(
        select(models.AssignmentSubmission)
        .options(
            selectinload(models.AssignmentSubmission.material),
            selectinload(models.AssignmentSubmission.student)
        )
        .join(models.CourseMaterial)
        .where(models.CourseMaterial.subject_id == subject_id)
    )

    return templates.TemplateResponse(
        "subjects/submissions.html",
        {
            "request": request,
            "subject": subject,
            "submissions": submissions.scalars().all()
        }
    )


@router.post("/submissions/{submission_id}/grade")
async def grade_submission(
        submission_id: int,
        grade: int = Form(...),
        feedback: str = Form(None),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    submission = await db.execute(
        select(models.AssignmentSubmission)
        .options(selectinload(models.AssignmentSubmission.material))
        .where(models.AssignmentSubmission.id == submission_id)
    )
    submission = submission.scalar()

    # Проверка прав
    subject = await db.execute(
        select(models.Subject)
        .where(models.Subject.id == submission.material.subject_id)
    )
    subject = subject.scalar()

    if subject.teacher.user_id != current_user.id:
        raise HTTPException(status_code=403)

    # Обновление данных
    submission.grade = grade
    submission.feedback = feedback
    submission.status = "graded"

    await db.commit()

    return RedirectResponse(
        url=f"/subjects/{subject.id}/submissions",
        status_code=303
    )