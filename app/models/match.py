from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, ForeignKey, Enum, func
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
    match_title = Column(String, nullable=False) # E.g., "Team A vs Team B"
    sport_name = Column(String, default="Football") # Football or Basketball
    league_name = Column(String)
    match_date = Column(DateTime(timezone=True), nullable=False)
    match_time_start = Column(DateTime(timezone=True), nullable=False)
    team_a = Column(String)
    team_b = Column(String)
    team_a_logo = Column(String, nullable=True)
    team_b_logo = Column(String, nullable=True)
    platform_fee_percent = Column(DECIMAL(5, 2), default=10.00)
    promotional_amount = Column(DECIMAL(10, 2), default=0.00) # For marketing/promotions
    feature_match = Column(Integer, default=0) # 0 = No, 1 = Yes (For UI Highlighting)
    # Financial Configuration
    entry_fee = Column(DECIMAL(10, 2), default=20.00)
    image_url = Column(String, nullable=True) # Optional field for match image/logo
    # match_time_start = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(MatchStatus), default=MatchStatus.UPCOMING)
    # Results
    score_a = Column(Integer, nullable=True)
    score_b = Column(Integer, nullable=True)
    winning_team = Column(String, nullable=True) # "A", "B", or "Draw"

    predictions = relationship("Prediction", back_populates="match")

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    match_id = Column(Integer, ForeignKey("matches.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
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