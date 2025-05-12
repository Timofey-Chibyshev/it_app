import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import text
from app.models import models
from app.auth import get_password_hash

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost/edu_platform_db"
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        # Удаляем все таблицы с CASCADE
        await conn.execute(text("DROP TABLE IF EXISTS users, groups, subjects, course_materials, assignment_submissions, schedules, teachers, students, group_subject CASCADE"))
        
        # Создаем все таблицы заново
        await conn.run_sync(models.Base.metadata.create_all)

    async with async_session() as session:
        try:
            # Создаем тестовых пользователей
            teacher_user = models.User(
                first_name="Иван",
                last_name="Преподавателев",
                patronymic="Петрович",
                email="teacher@edu.ru",
                hashed_password=get_password_hash("teacher123"),
                role="teacher",
                is_active=True
            )
            
            student_user = models.User(
                first_name="Мария",
                last_name="Студентова",
                patronymic="Ивановна",
                email="student@edu.ru",
                hashed_password=get_password_hash("student456"),
                role="student",
                is_active=True
            )
            
            session.add_all([teacher_user, student_user])
            await session.flush()  # Получаем ID пользователей

            # Создаем тестовую группу
            group = models.Group(number="ИТ-21")
            session.add(group)
            await session.flush()  # Получаем ID группы

            # Создаем профили преподавателя и студента
            teacher = models.Teacher(
                user_id=teacher_user.id,
                position="Старший преподаватель"
            )
            
            student = models.Student(
                user_id=student_user.id,
                group_id=group.id
            )
            
            session.add_all([teacher, student])
            await session.flush()  # Генерируем ID студента

            # Создаем учебный предмет
            subject = models.Subject(
                name="Базы данных",
                type="practice",
                teacher_id=teacher.user_id
            )
            session.add(subject)
            await session.flush()  # Получаем ID предмета

            # Связываем группу и предмет
            await session.execute(
                insert(models.group_subject).values(
                    group_id=group.id,
                    subject_id=subject.id
                )
            )

            # Добавляем учебный материал
            course_material = models.CourseMaterial(
                title="Введение в SQL",
                file_path="/materials/sql_intro.pdf",
                description="Основы работы с SQL",
                type="lecture",
                deadline=datetime(2025, 12, 31, 23, 59),
                subject_id=subject.id,
                group_id=group.id
            )
            session.add(course_material)
            await session.flush() 

            # Добавляем пример сдачи задания
            submission = models.AssignmentSubmission(
                student_id=student.id,  # Используем id из таблицы students
                material_id=course_material.id,
                file_path="/submissions/student1.pdf",
                grade=95,
                feedback="Отличная работа!",
                status="graded"
            )

            # Создаем расписание
            schedule = models.Schedule(
                start_time=datetime(2024, 1, 15, 10, 0),
                end_time=datetime(2024, 1, 15, 12, 0),
                subject_id=subject.id
            )
            session.add(schedule)

            await session.commit()
            print("✅ Тестовые данные успешно созданы!")

        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка при инициализации БД: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(init_db())