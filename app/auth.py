import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request  # CHANGED: Добавлен Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import User
from app.schemas.schemas import TokenData
from app.database import get_db

logger = logging.getLogger(__name__)

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

# Конфигурация токенов
SECRET_KEY = "your-secret-key-keep-it-safe"
REFRESH_SECRET_KEY = "your-refresh-secret-key-different"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# CHANGED: Кастомизированная схема для Swagger UI
# class CustomOAuth2PasswordBearer(OAuth2PasswordBearer):
#     async def __call__(self, request: Request) -> Optional[str]:
#         # Переопределяем параметры для формы
#         return await super().__call__(request)

class CustomOAuth2PasswordBearer(OAuth2PasswordBearer):
    async def __call__(self, request: Request) -> Optional[str]:
        # Получаем токен из куки вместо заголовка
        token = request.cookies.get("access_token")
        return token


# oauth2_scheme = CustomOAuth2PasswordBearer(
#     tokenUrl="auth/login",
#     scheme_name="EmailAuth",
#     description="Введите ваш **email** в поле 'username' и пароль",  # Уточнение
#     scopes={"me": "Read user info"}
# )

oauth2_scheme = CustomOAuth2PasswordBearer(
    tokenUrl="auth/login",
    scheme_name="CookieAuth",
    description="Используйте форму входа для аутентификации",
)

def get_password_hash(password: str) -> str:
    """Хэширование пароля"""
    logger.debug("Generating password hash")
    return pwd_context.hash(password)

async def authenticate_user(
    db: AsyncSession, 
    email: str, 
    password: str
) -> Optional[User]:
    """Аутентификация по email и паролю"""
    logger.info(f"Auth attempt for email: {email}")
    
    try:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar()
        
        if not user:
            logger.warning(f"User {email} not found")
            return None
            
        logger.debug(f"User found: {user.email}")
        logger.debug("Verifying password...")
        
        is_valid = pwd_context.verify(password, user.hashed_password)
        logger.info(f"Password valid: {is_valid}")
        
        if not is_valid:
            logger.warning(f"Invalid password for {email}")
            
        return user if is_valid else None
        
    except Exception as e:
        logger.error(f"Auth error: {str(e)}", exc_info=True)
        raise

def create_access_token(
    data: dict, 
    expires_delta: Optional[timedelta] = None
) -> str:
    """Создание access токена"""
    logger.debug("Creating access token")
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Access token created for: {data.get('sub')}")
    return encoded_jwt

def create_refresh_token(
    data: dict, 
    expires_delta: Optional[timedelta] = None
) -> str:
    """Создание refresh токена"""
    logger.debug("Creating refresh token")
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=7))
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Refresh token created for: {data.get('sub')}")
    return encoded_jwt

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db)
) -> User:
    """Получение текущего пользователя по access токену"""
    logger.info("Starting token validation")
    logger.debug(f"Received token: {token[:15]}...")
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.debug(f"Decoded payload: {payload}")
        
        if payload.get("type") != "access":
            logger.error(f"Invalid token type: {payload.get('type')} (expected 'access')")
            raise credentials_exception
            
        email: str = payload.get("sub")
        if not email:
            logger.error("Missing 'sub' claim in token")
            raise credentials_exception
            
        logger.info(f"Token validated for email: {email}")
        
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise credentials_exception
    
    try:
        logger.info(f"Searching user in DB: {email}")
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar()
        
        if not user:
            logger.error(f"User {email} not found in database")
            raise credentials_exception
            
        logger.info(f"User resolved: ID={user.id}, Email={user.email}")
        return user
        
    except Exception as e:
        logger.error(f"Database error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

def verify_refresh_token(token: str) -> Optional[str]:
    """Верификация refresh токена"""
    logger.debug("Verifying refresh token")
    try:
        logger.debug(f"Token received: {token[:15]}...")
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "refresh":
            logger.error("Invalid token type (expected 'refresh')")
            return None
            
        email = payload.get("sub")
        if not email:
            logger.error("Missing 'sub' claim in refresh token")
            return None
            
        logger.debug(f"Valid refresh token for: {email}")
        return email
        
    except JWTError as e:
        logger.error(f"Refresh token error: {str(e)}")
        return None

def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:  # Добавить аннотацию возвращаемого типа
    """Проверка активности пользователя"""
    logger.debug(f"Checking active user: {current_user.email}")
    return current_user
