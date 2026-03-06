import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User, Wallet
from app.schemas.user import UserCreate, UserLogin, Token, OTPVerify, ForgotPassword, ResetPassword

router = APIRouter()

def generate_otp():
    """Generates a random 6-digit OTP"""
    return str(random.randint(100000, 999999))

@router.post("/register")
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    result = await db.execute(select(User).where(User.phone == user_in.phone))
    user = result.scalars().first()

    if user and user.is_active:
        raise HTTPException(status_code=400, detail="Phone number already registered and verified")

    # Generate OTP
    otp = generate_otp()

    if user and not user.is_active:
        # User exists but never verified OTP. Update their details.
        user.hashed_password = get_password_hash(user_in.password)
        user.full_name = user_in.full_name
        user.otp_code = otp
    else:
        # Completely new user
        new_user = User(
            phone=user_in.phone,
            full_name=user_in.full_name,
            hashed_password=get_password_hash(user_in.password),
            role="user",
            is_active=False,
            otp_code=otp
        )
        db.add(new_user)

    await db.commit()

    # TODO: Integrate Twilio API here to send `otp` to `user_in.phone`
    print(f"\n[MOCK SMS] Sent OTP: {otp} to {user_in.phone}\n")

    return {
        "message": "OTP sent successfully to your phone number",
        "phone": user_in.phone
    }

# this is real twilio otp send function, when client give twilio credentials that time implelent this function
# import random
# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select
# from twilio.rest import Client  
# from twilio.base.exceptions import TwilioRestException

# from app.api.deps import get_db
# from app.core.config import settings
# from app.core.security import create_access_token, get_password_hash, verify_password
# from app.models.user import User, Wallet
# from app.schemas.user import UserCreate, UserLogin, Token, OTPVerify

# router = APIRouter()

# def generate_otp():
#     """Generates a random 6-digit OTP"""
#     return str(random.randint(100000, 999999))

# def send_sms_otp(phone_number: str, otp_code: str):
#     """Sends a real SMS using Twilio"""
#     try:
#         client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
#         message = client.messages.create(
#             body=f"Welcome to MatchKash! Your verification code is: {otp_code}",
#             from_=settings.TWILIO_PHONE_NUMBER,
#             to=phone_number
#         )
#         print(f"SMS sent successfully. Message SID: {message.sid}")
#         return True
#     except TwilioRestException as e:
#         print(f"Twilio Error: {e}")
#         return False
    

# # @router.post("/register")
# # async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
# #     result = await db.execute(select(User).where(User.phone == user_in.phone))
# #     user = result.scalars().first()

# #     if user and user.is_active:
# #         raise HTTPException(status_code=400, detail="Phone number already registered")

# #     # Generate the 6-digit code
# #     otp = generate_otp()

# #     if user and not user.is_active:
# #         user.hashed_password = get_password_hash(user_in.password)
# #         user.full_name = user_in.full_name
# #         user.otp_code = otp
# #     else:
# #         new_user = User(
# #             phone=user_in.phone,
# #             full_name=user_in.full_name,
# #             hashed_password=get_password_hash(user_in.password),
# #             role="user",
# #             is_active=False,
# #             otp_code=otp
# #         )
# #         db.add(new_user)

# #     await db.commit()

# #     # SEND REAL OTP HERE
# #     # Note: Ensure the phone number includes the country code (e.g., +880 for BD, +509 for Haiti)
# #     sms_sent = send_sms_otp(user_in.phone, otp)
    
# #     if not sms_sent:
# #         raise HTTPException(
# #             status_code=500, 
# #             detail="Failed to send SMS. Please check if the phone number is correct."
# #         )

# #     return {
# #         "message": "OTP sent successfully to your phone number",
# #         "phone": user_in.phone
# #     }


@router.post("/verify-otp", response_model=Token)
async def verify_otp(data: OTPVerify, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalars().first()

    # Verify OTP
    if not user or user.otp_code != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # Success! Activate user and clear OTP
    user.is_active = True
    user.otp_code = None

    # Check if Wallet exists, if not, create it
    wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
    if not wallet_result.scalars().first():
        wallet = Wallet(user_id=user.id, balance=0.00)
        db.add(wallet)

    await db.commit()

    # Give them the access token (Auto-Login)
    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == user_in.phone))
    user = result.scalars().first()

    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect phone or password")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is not verified. Please verify your OTP.")

    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}

# For Twilio
# @router.post("/forgot-password")
# async def forgot_password(data: ForgotPassword, db: AsyncSession = Depends(get_db)):
#     """Step 1: Request an OTP to reset the password"""
    
#     # 1. Check if user exists
#     result = await db.execute(select(User).where(User.phone == data.phone))
#     user = result.scalars().first()

#     if not user:
#         raise HTTPException(status_code=404, detail="User with this phone number not found")

#     # 2. Generate new OTP and save to database
#     otp = generate_otp()
#     user.otp_code = otp
#     await db.commit()

#     # 3. Send SMS (Using your Twilio setup)
#     sms_sent = send_sms_otp(user.phone, otp)
    
#     if not sms_sent:
#         raise HTTPException(
#             status_code=500, 
#             detail="Failed to send SMS. Please try again later."
#         )

#     return {"message": "OTP sent successfully. Please check your phone."}


# @router.post("/reset-password")
# async def reset_password(data: ResetPassword, db: AsyncSession = Depends(get_db)):
#     """Step 2 & 3: Verify OTP and save the new password"""
    
#     # 1. Find the user
#     result = await db.execute(select(User).where(User.phone == data.phone))
#     user = result.scalars().first()

#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     # 2. Verify OTP
#     if not user.otp_code or user.otp_code != data.otp:
#         raise HTTPException(status_code=400, detail="Invalid or expired OTP")

#     # 3. Hash the new password and update the user
#     user.hashed_password = get_password_hash(data.new_password)
    
#     # 4. Clear the OTP so it can't be used again
#     user.otp_code = None
    
#     await db.commit()

#     return {"message": "Password has been reset successfully. You can now log in."}

@router.post("/forgot-password")
async def forgot_password(data: ForgotPassword, db: AsyncSession = Depends(get_db)):
    """Step 1: Request an OTP to reset the password (MOCK)"""
    
    # 1. Check if user exists
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User with this phone number not found")

    # 2. Generate new OTP and save to database
    otp = str(random.randint(100000, 999999))
    user.otp_code = otp
    await db.commit()

    # 3. MOCK SMS - Print to terminal instead of sending real SMS
    print("\n" + "="*50)
    print(f"[MOCK SMS] Password Reset Request")
    print(f"To Phone: {data.phone}")
    print(f"Your OTP Code is: {otp}")
    print("="*50 + "\n")

    return {
        "message": "OTP sent successfully. Please check your phone (or terminal).",
        "mock_otp_hint": otp  # You can remove this line in production!
    }


@router.post("/reset-password")
async def reset_password(data: ResetPassword, db: AsyncSession = Depends(get_db)):
    """Step 2 & 3: Verify OTP and save the new password"""
    
    # 1. Find the user
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Verify OTP
    if not user.otp_code or user.otp_code != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # 3. Hash the new password and update the user
    user.hashed_password = get_password_hash(data.new_password)
    
    # 4. Clear the OTP so it can't be used again
    user.otp_code = None
    
    await db.commit()

    return {"message": "Password has been reset successfully. You can now log in."}