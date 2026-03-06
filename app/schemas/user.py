from pydantic import BaseModel, model_validator
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

class UserResponse(UserBase):
    id: int
    is_active: bool
    role: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str