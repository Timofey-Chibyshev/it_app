from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text, Table, Boolean, CheckConstraint
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
from app.database import Base

# Ассоциативная таблица для связи групп и предметов (многие-ко-многим)
group_subject = Table(
    'group_subject',
    Base.metadata,
    Column('group_id', ForeignKey('groups.id'), primary_key=True),
    Column('subject_id', ForeignKey('subjects.id'), primary_key=True)
)

class User(Base):
    __tablename__ = 'users'

    # Основные поля пользователя
    id = Column(Integer, primary_key=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    patronymic = Column(String(50))  # Отчество (может быть пустым)
    email = Column(String(100), unique=True, nullable=False)  # Уникальный email
    hashed_password = Column(String(255), nullable=False)  # Захешированный пароль
    role = Column(Enum('student', 'teacher', name='user_roles'), nullable=False)  # Роль в системе
    is_active = Column(Boolean, default=True)  # Активен ли аккаунт

    # Связи с профилями (каскадное удаление)
    student_profile = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    teacher_profile = relationship("Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Student(Base):
    __tablename__ = 'students'

    # Автоинкрементный ID как первичный ключ
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Внешний ключ на users.id с уникальным ограничением
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id'))

    # Остальные отношения остаются без изменений
    user = relationship("User", back_populates="student_profile")
    group = relationship("Group", back_populates="students")
    submissions = relationship("AssignmentSubmission", back_populates="student")

class Teacher(Base):
    __tablename__ = 'teachers'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    position = Column(String(100), nullable=False)  # Должность преподавателя

    user = relationship("User", back_populates="teacher_profile")
    subjects = relationship("Subject", back_populates="teacher", cascade="all, delete-orphan")  # Ведущие предметы

class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True)
    number = Column(String(20), unique=True, nullable=False)  # Номер группы (например, "ИТ-21")

    students = relationship("Student", back_populates="group", lazy="selectin")
    subjects = relationship("Subject", secondary=group_subject, back_populates="groups", lazy="selectin")  # Предметы группы

class Subject(Base):
    __tablename__ = 'subjects'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # Название предмета
    type = Column(Enum('lecture', 'practice', name='subject_types'), nullable=False)  # Тип предмета
    teacher_id = Column(Integer, ForeignKey('teachers.user_id'), nullable=False)  # Преподаватель

    teacher = relationship("Teacher", back_populates="subjects")
    groups = relationship("Group", secondary=group_subject, back_populates="subjects", lazy="selectin")  # Группы, изучающие предмет
    materials = relationship("CourseMaterial", back_populates="subject")  # Материалы курса
    schedule = relationship("Schedule", back_populates="subject")  # Расписание занятий

class CourseMaterial(Base):
    __tablename__ = 'course_materials'

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)  # Название материала
    file_path = Column(String(255), nullable=False)  # Путь к файлу на сервере
    description = Column(Text)  # Описание материала
    type = Column(Enum('lecture', 'practice', 'assignment', name='material_types'), nullable=False)  # Тип материала
    created_at = Column(DateTime, default=datetime.utcnow)  # Дата создания
    deadline = Column(DateTime)  # Дедлайн для задания (если тип assignment)
    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=False)  # Принадлежность к предмету
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=False)  # Для какой группы

    # Связи ORM
    subject = relationship("Subject", back_populates="materials")
    group = relationship("Group")
    submissions = relationship("AssignmentSubmission", back_populates="material")  # Сданные задания

    # Проверка что дедлайн в будущем
    __table_args__ = (
        CheckConstraint('deadline > CURRENT_TIMESTAMP', name='check_future_deadline'),
    )

class AssignmentSubmission(Base):
    __tablename__ = 'assignment_submissions'

    id = Column(Integer, primary_key=True)
    submission_date = Column(DateTime, default=datetime.utcnow)  # Дата сдачи
    status = Column(Enum('submitted', 'graded', 'rejected', name='submission_status'), default='submitted')  # Статус
    grade = Column(Integer)  # Оценка (0-100)
    feedback = Column(Text)  # Комментарий преподавателя
    file_path = Column(String(255))  # Путь к файлу решения
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)  # Студент
    material_id = Column(Integer, ForeignKey('course_materials.id'), nullable=False)  # Задание

    # Связи
    student = relationship("Student", back_populates="submissions")
    material = relationship("CourseMaterial", back_populates="submissions")

    # Проверка оценки
    __table_args__ = (
        CheckConstraint('grade BETWEEN 0 AND 100', name='grade_range_check'),
    )

class Schedule(Base):
    __tablename__ = 'schedules'

    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, nullable=False)  # Начало занятия
    end_time = Column(DateTime, nullable=False)  # Конец занятия
    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=False)  # Привязка к предмету

    subject = relationship("Subject", back_populates="schedule", lazy='selectin')

    # Проверка что end_time > start_time
    __table_args__ = (
        CheckConstraint('end_time > start_time', name='check_time_order'),
    )
