from sqlalchemy import Column, Integer, String, Boolean, DateTime, DECIMAL, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(Enum(UserRole, native_enum=False, values_callable=lambda obj: [e.value for e in obj]), default=UserRole.USER)
    is_active = Column(Boolean, default=False)
    otp_code = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    profile_photo = Column(String, nullable=True)
    push_token = Column(String, nullable=True)

    # Admin/User Settings
    email = Column(String, unique=True, nullable=True)
    address = Column(String, nullable=True)
    language = Column(String, default="English")

    # Wallet (One-to-One)
    wallet = relationship("Wallet", back_populates="user", uselist=False)
    predictions = relationship("Prediction", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")

    @property
    def user_balance(self):
        """Helper to get balance directly from user instance for schemas"""
        if self.wallet:
            return self.wallet.balance
        return 0.00

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    balance = Column(DECIMAL(10, 2), default=0.00)  # GDES Currency
    total_won = Column(DECIMAL(10, 2), default=0.00)
    total_deposited = Column(DECIMAL(10, 2), default=0.00)
    
    user = relationship("User", back_populates="wallet")

class TokenBlocklist(Base):
    __tablename__ = "token_blocklist"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id")) # The person receiving the notification
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    type = Column(String) # e.g., "WITHDRAWAL_REQUEST"
    reference_id = Column(Integer, nullable=True) # e.g., The Transaction ID
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="notifications")