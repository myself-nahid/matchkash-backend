from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

# Prediction Input
class PredictionCreate(BaseModel):
    match_id: int
    predicted_winner: str  # "A", "B", "Draw"
    predicted_score_a: int
    predicted_score_b: int

# Match Management
class MatchBase(BaseModel):
    sport: str = "Football"
    league_name: str
    team_a: str
    team_b: str
    start_time: datetime
    entry_fee: Decimal = 20.00
    platform_fee_percent: Decimal = 10.00

class MatchCreate(MatchBase):
    pass

class MatchUpdate(MatchBase):
    score_a: Optional[int] = None
    score_b: Optional[int] = None
    status: Optional[str] = None

class MatchResponse(MatchBase):
    id: int
    status: str
    score_a: Optional[int]
    score_b: Optional[int]
    
    class Config:
        from_attributes = True