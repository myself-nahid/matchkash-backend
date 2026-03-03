from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(DECIMAL(10, 2), nullable=False)
    type = Column(String) # DEPOSIT, WITHDRAW, ENTRY_FEE, WINNING_PAYOUT
    status = Column(String, default="COMPLETED") # PENDING, COMPLETED, REJECTED
    reference = Column(String, nullable=True) # E.g., "Match ID: 5" or "MonCash Transaction ID"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="transactions")