from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.user import User, TokenBlocklist 
# from app.schemas.user import Token
from app.schemas.user import TokenResponse

# Point to the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_db() -> AsyncGenerator:
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. SECURE LOGOUT CHECK: Is the token blacklisted?
    is_blacklisted = await db.scalar(select(TokenBlocklist).where(TokenBlocklist.token == token))
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again."
        )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type") # 👈 Extract token type
        
        if user_id is None:
            raise credentials_exception
            
        # Block refresh tokens from being used for normal API calls
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Please use an access token.",
            )
            
    except JWTError:
        raise credentials_exception

    from sqlalchemy.orm import joinedload
    result = await db.execute(
        select(User)
        .options(joinedload(User.wallet))
        .where(User.id == int(user_id))
    )
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=400, detail="The user doesn't have enough privileges"
        )
    return current_user