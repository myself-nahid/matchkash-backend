import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.api.deps import get_db
from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.models.user import User, Wallet, TokenBlocklist
from app.schemas.user import TokenResponse, UserCreate, UserLogin, OTPVerify, ForgotPassword, ResetPassword, ResendOTP, TokenRefreshRequest, forgot_password_otp_response, verifyOTPResponse
from app.api.deps import oauth2_scheme
from jose import jwt, JWTError
from app.core.config import settings
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from app.core.utils import normalize_phone_number
from sqlalchemy import func

router = APIRouter()

def generate_otp():
    """Generates a random 6-digit OTP"""
    return str(random.randint(100000, 999999))

def send_sms_otp(phone_number: str, otp_code: str):
    """
    Sends OTP using a 3-tier fallback system:
    1. WhatsApp
    2. SMS via Alphanumeric Sender ID ('Xentra')
    3. SMS via Standard Twilio Number
    """
    # Ensure the phone number has a '+' sign for Twilio
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number

    message_body = f"Welcome to Xentra! Your verification code is: {otp_code}"
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # --- ATTEMPT 1: WHATSAPP ---
        try:
            print(f"🔄 Attempting WhatsApp OTP to {phone_number}...")
            message = client.messages.create(
                body=message_body,
                from_=f"whatsapp:{settings.TWILIO_PHONE_NUMBER}",
                to=f"whatsapp:{phone_number}"
            )
            print(f"✅ WhatsApp OTP sent successfully! SID: {message.sid}")
            return True
        except TwilioRestException as e:
            print(f"⚠️ WhatsApp failed (User might not have WA). Error: {e.msg}")
            print("🔄 Falling back to Alphanumeric SMS...")

        # --- ATTEMPT 2: ALPHANUMERIC SMS ("Xentra") ---
        try:
            # Note: This will automatically bypass US A2P 10DLC restrictions 
            # for international numbers that support Alphanumeric IDs (like Haiti).
            message = client.messages.create(
                body=message_body,
                from_="Xentra",  
                to=phone_number
            )
            print(f"✅ Alphanumeric SMS ('Xentra') sent successfully! SID: {message.sid}")
            return True
        except TwilioRestException as e:
            print(f"⚠️ Alphanumeric SMS failed. Error: {e.msg}")
            print("🔄 Falling back to standard SMS routing...")

        # --- ATTEMPT 3: STANDARD SMS FALLBACK ---
        try:
            message = client.messages.create(
                body=message_body,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            print(f"✅ Standard SMS sent successfully! SID: {message.sid}")
            return True
        except TwilioRestException as final_e:
            print(f"❌ ALL OTP DELIVERY METHODS FAILED: {final_e.msg}")
            return False

    except Exception as critical_error:
        print(f"❌ CRITICAL TWILIO ERROR: {str(critical_error)}")
        return False

@router.post("/register")
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Prevent registration with Twilio phone number (Twilio doesn't allow sending SMS to itself)
    if user_in.phone == settings.TWILIO_PHONE_NUMBER:
        raise HTTPException(status_code=400, detail="Cannot register with this phone number")

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

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400, 
            detail="Phone number is already registered or request was sent twice. Please log in."
        )

    # Send real OTP via Twilio
    # Note: Ensure the phone number includes the country code (e.g., +880 for BD, +509 for Haiti)
    sms_sent = send_sms_otp(user_in.phone, otp)
    
    if not sms_sent:
        raise HTTPException(
            status_code=500, 
            detail="Failed to send SMS. Please check if the phone number is correct."
        )

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


@router.post("/verify-otp", response_model=verifyOTPResponse)
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
    return {"status": "success", "message": "OTP verified successfully"}

@router.post("/resend-otp")
async def resend_otp(data: ResendOTP, db: AsyncSession = Depends(get_db)):
    """Generate a new OTP and resend it to the user"""
    
    # Check if phone number is the same as Twilio number
    if data.phone == settings.TWILIO_PHONE_NUMBER:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    
    # 1. Find the user by phone
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Generate a NEW OTP
    new_otp = generate_otp() # Assuming you have the generate_otp() function from earlier
    
    # 3. Update the database with the new OTP
    user.otp_code = new_otp
    db.add(user)
    await db.commit()

    # 4. Send the SMS via Twilio
    sms_sent = send_sms_otp(user.phone, new_otp)
    if not sms_sent:
        raise HTTPException(status_code=500, detail="Failed to send SMS")

    return {
        "message": "A new OTP has been sent to your phone number."
    }

@router.post("/login", response_model=TokenResponse)
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    # 1. Normalize the phone number from the frontend request
    normalized_phone = normalize_phone_number(user_in.phone)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format")

    # 2. Find ALL potential users whose normalized phone number ends with the input
    # This handles different country codes and formatting.
    # Note: In PostgreSQL, 'g' flag for global replace is the default.
    query = select(User).where(
    func.regexp_replace(User.phone, '[^0-9]', '', 'g').like(f"%{normalized_phone}")
    )
    result = await db.execute(query)
    potential_users = result.scalars().all()

    # 3. If no potential users are found, it's an incorrect phone number
    if not potential_users:
        raise HTTPException(status_code=400, detail="Incorrect phone or password")

    # 4. Loop through the potential users and find the one with the matching password
    authenticated_user = None
    for user in potential_users:
        if verify_password(user_in.password, user.hashed_password):
            authenticated_user = user
            break  # Found our user, stop looping

    # 5. If no user had a matching password after the loop, it's an incorrect password
    if not authenticated_user:
        raise HTTPException(status_code=400, detail="Incorrect phone or password")
        
    # 6. Check if the authenticated user's account is active
    if not authenticated_user.is_active:
        raise HTTPException(status_code=400, detail="Account is not verified. Please verify your OTP.")

    # 7. Generate and return tokens for the correct user
    access_token = create_access_token(subject=authenticated_user.id)
    refresh_token = create_refresh_token(subject=authenticated_user.id)
    
    return {
        "status": "success",
        "message": "Login successful",
        "data": {
            "access_token": access_token,
            "user_role": authenticated_user.role,
            "refresh_token": refresh_token
        }
    }

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

@router.post("/refresh-token", response_model=TokenResponse)
async def refresh_access_token(data: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Takes a valid refresh_token and returns a new access_token & refresh_token pair.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired",
    )
    
    # 1. Check if the refresh token is blacklisted (logged out)
    is_blacklisted = await db.scalar(select(TokenBlocklist).where(TokenBlocklist.token == data.refresh_token))
    if is_blacklisted:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked. Please log in again.")

    # 2. Decode and validate the refresh token
    try:
        payload = jwt.decode(data.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if user_id is None or token_type != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 3. Verify user still exists and is active
    user = await db.get(User, int(user_id))
    if not user or not user.is_active:
        raise credentials_exception

    # 4. Generate a fresh pair of tokens
    new_access_token = create_access_token(subject=user.id)
    new_refresh_token = create_refresh_token(subject=user.id)

    # Optional: Blacklist the OLD refresh token to prevent reuse (Token Rotation)
    old_token_block = TokenBlocklist(token=data.refresh_token)
    db.add(old_token_block)
    await db.commit()

    return {
        "status": "success",
        "message": "Token refreshed successfully",
        "data": {
            "access_token": new_access_token,
            "user_role": user.role,
            "refresh_token": new_refresh_token
        }
    }

@router.post("/forgot-password")
async def forgot_password(data: ForgotPassword, db: AsyncSession = Depends(get_db)):
    """Step 1: Request an OTP to reset the password"""
    
    # Check if phone number is the same as Twilio number
    if data.phone == settings.TWILIO_PHONE_NUMBER:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    
    # 1. Check if user exists
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User with this phone number not found")

    # 2. Generate new OTP and save to database
    otp = generate_otp()
    user.otp_code = otp
    await db.commit()

    # 3. Send SMS via Twilio
    sms_sent = send_sms_otp(user.phone, otp)
    
    if not sms_sent:
        raise HTTPException(
            status_code=500, 
            detail="Failed to send SMS. Please try again later."
        )

    return {"message": "OTP sent successfully. Please check your phone."}

@router.post("/forgot-password-verify-otp")
async def forgot_password_verify_otp(data: OTPVerify, db: AsyncSession = Depends(get_db)):
    """Step 2: Just verifies if the OTP is correct so the app can move to the New Password screen"""
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalars().first()

    # Verify OTP
    if not user or user.otp_code != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    return {"status": "success", "message": "OTP verified successfully. Proceed to reset password."}


@router.post("/reset-password")
async def reset_password(data: ResetPassword, db: AsyncSession = Depends(get_db)):
    """Step 3: Verifies OTP one last time and changes the password"""
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify OTP again to ensure security
    if not user.otp_code or user.otp_code != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # Hash the new password and update the user
    user.hashed_password = get_password_hash(data.new_password)
    
    # NOW we clear the OTP so it can't be used again
    user.otp_code = None
    
    await db.commit()

    return {"status": "success", "message": "Password has been reset successfully. You can now log in."}

# @router.post("/reset-password-verify-otp", response_model=TokenResponse)
# async def verify_otp(data: OTPVerify, db: AsyncSession = Depends(get_db)):
#     result = await db.execute(select(User).where(User.phone == data.phone))
#     user = result.scalars().first()

#     # Verify OTP
#     if not user or user.otp_code != data.otp:
#         raise HTTPException(status_code=400, detail="Invalid or expired OTP")

#     # Success! Activate user and clear OTP
#     user.is_active = True
#     user.otp_code = None

#     # Check if Wallet exists, if not, create it
#     wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
#     if not wallet_result.scalars().first():
#         wallet = Wallet(user_id=user.id, balance=0.00)
#         db.add(wallet)

#     await db.commit()

#     # Give them the access token (Auto-Login)
#     access_token = create_access_token(subject=user.id)
#     return {"status": "success", "message": "OTP verified successfully"}

@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
):
    """
    Logs the user out by blacklisting their current JWT token.
    Once blacklisted, this exact token can never be used again.
    """
    # Check if it's already blacklisted to prevent duplicate errors
    is_blacklisted = await db.scalar(select(TokenBlocklist).where(TokenBlocklist.token == token))
    
    if not is_blacklisted:
        # Add the token to the blocklist
        blacklisted_token = TokenBlocklist(token=token)
        db.add(blacklisted_token)
        await db.commit()

    return {"message": "Successfully logged out"}