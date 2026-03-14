import os
import shutil
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdateProfile, UserUpdatePassword, UserAvatarUpdate
from app.core.security import verify_password, get_password_hash

load_dotenv()

router = APIRouter()

UPLOAD_DIR = "uploads/avatars"
SERVER_URL = os.getenv("SERVER_URL", "").rstrip("/")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Fetch current user details for the Account Settings screen"""
    return current_user

@router.put("/me/profile", response_model=UserResponse)
async def update_my_profile(
    data: UserUpdateProfile, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Update Name (Phone is usually read-only as it's the login ID)"""
    if data.full_name is not None:
        current_user.full_name = data.full_name
        
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return current_user

@router.put("/me/password")
async def change_my_password(
    data: UserUpdatePassword, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Change Password securely from the Account Settings screen"""
    
    # 1. Verify the current password is correct
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # 2. Prevent changing to the exact same password (optional but good practice)
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="New password cannot be the same as the old one")

    # 3. Hash and save the new password
    current_user.hashed_password = get_password_hash(data.new_password)
    
    db.add(current_user)
    await db.commit()
    
    return {"message": "Password updated successfully"}

# @router.post("/me/avatar", response_model=UserResponse)
# async def upload_profile_photo(
#     payload: UserAvatarUpdate,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     """Save Cloudinary avatar URL"""

#     # Convert HttpUrl → str
#     current_user.profile_photo = str(payload.profile_photo)

#     db.add(current_user)
#     await db.commit()
#     await db.refresh(current_user)

#     return current_user

@router.post("/me/avatar", response_model=UserResponse)
async def upload_profile_photo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a new profile picture (Camera Icon in UI)"""
    
    # Validate file type (basic)
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Generate a unique filename using the user's ID
    file_extension = file.filename.split(".")[-1]
    file_name = f"user_{current_user.id}_avatar.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    # Save the file locally (In production, you'd upload to AWS S3 / GCP here)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Update database with the full URL including SERVER_URL
    current_user.profile_photo = f"{SERVER_URL}/{file_path}".replace("\\", "/")
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return current_user