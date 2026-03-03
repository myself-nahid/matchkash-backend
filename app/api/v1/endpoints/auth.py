from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User, Wallet
from app.schemas.user import UserCreate, UserLogin, Token

router = APIRouter()

@router.post("/register", response_model=Token)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check existing user
    result = await db.execute(select(User).where(User.phone == user_in.phone))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Phone number already registered")

    # Create User
    new_user = User(
        phone=user_in.phone,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        role="user"
    )
    db.add(new_user)
    await db.flush() # Flush to get ID for wallet

    # Initialize Wallet
    wallet = Wallet(user_id=new_user.id, balance=0.00)
    db.add(wallet)
    
    await db.commit()

    access_token = create_access_token(subject=new_user.id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == user_in.phone))
    user = result.scalars().first()

    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect phone or password")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User is inactive")

    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}