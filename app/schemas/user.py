from datetime import datetime
from pydantic import BaseModel, HttpUrl, model_validator
from typing import Optional

class UserBase(BaseModel):
    phone: str
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str
    re_password: str  

    # Pydantic v2 Validator
    @model_validator(mode='after')
    def check_passwords_match(self) -> 'UserCreate':
        pw1 = self.password
        pw2 = self.re_password
        if pw1 is not None and pw2 is not None and pw1 != pw2:
            raise ValueError('Passwords do not match')
        return self

class UserLogin(BaseModel):
    phone: str
    password: str

# class UserResponse(UserBase):
#     id: int
#     is_active: bool
#     role: str

#     class Config:
#         from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class OTPVerify(BaseModel):
    phone: str
    otp: str

class ForgotPassword(BaseModel):
    phone: str

class ResetPassword(BaseModel):
    phone: str
    otp: str
    new_password: str
    re_new_password: str

    @model_validator(mode='after')
    def check_passwords_match(self) -> 'ResetPassword':
        if self.new_password != self.re_new_password:
            raise ValueError('Passwords do not match')
        return self
    
class UserUpdateProfile(BaseModel):
    full_name: Optional[str] = None

class UserUpdatePassword(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

    @model_validator(mode='after')
    def check_passwords_match(self) -> 'UserUpdatePassword':
        if self.new_password != self.confirm_password:
            raise ValueError('New passwords do not match')
        return self

class UserResponse(BaseModel):
    id: int
    phone: str
    full_name: Optional[str]
    profile_photo: Optional[str]
    is_active: bool
    role: str
    created_at: datetime  

    class Config:
        from_attributes = True

class UserAvatarUpdate(BaseModel):
    profile_photo: HttpUrl