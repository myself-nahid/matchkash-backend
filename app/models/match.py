from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum

class MatchStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    LIVE = "live"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    sport = Column(String, default="Football") # Football or Basketball
    league_name = Column(String)
    team_a = Column(String)
    team_b = Column(String)
    team_a_logo = Column(String, nullable=True)
    team_b_logo = Column(String, nullable=True)
    
    start_time = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(MatchStatus), default=MatchStatus.UPCOMING)
    
    # Financial Configuration
    entry_fee = Column(DECIMAL(10, 2), default=20.00)
    platform_fee_percent = Column(DECIMAL(5, 2), default=10.00)
    
    # Results
    score_a = Column(Integer, nullable=True)
    score_b = Column(Integer, nullable=True)

    predictions = relationship("Prediction", back_populates="match")

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    match_id = Column(Integer, ForeignKey("matches.id"))
    
    # User's prediction
    predicted_winner = Column(String) # "A", "B", or "Draw"
    predicted_score_a = Column(Integer)
    predicted_score_b = Column(Integer)
    
    # Outcome
    rank = Column(Integer, nullable=True)
    prize_amount = Column(DECIMAL(10, 2), default=0.00)
    status = Column(String, default="PENDING") # PENDING, WON, LOST

    user = relationship("User", back_populates="predictions")
    match = relationship("Match", back_populates="predictions")