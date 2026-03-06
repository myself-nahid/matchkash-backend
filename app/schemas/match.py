from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

# For Making Predictions (Request) 
class PredictionCreate(BaseModel):
    match_id: int
    predicted_winner: str  # "A", "B", or "Draw"
    predicted_score_a: int
    predicted_score_b: int

# For Home Screen (Response) 
class MatchResponse(BaseModel):
    id: int
    sport: str
    league_name: str
    team_a: str
    team_b: str
    team_a_logo: Optional[str] = None
    team_b_logo: Optional[str] = None
    start_time: datetime
    status: str
    entry_fee: Decimal
    
    # Dynamically calculated fields for the UI
    prize_pool: Decimal = 0.00
    participants_count: int = 0
    
    class Config:
        from_attributes = True

# For Leaderboard Screen (Response)
class LeaderboardEntry(BaseModel):
    rank: Optional[int]
    player_name: Optional[str]
    player_phone: str # Or player_id, depending on what UI shows
    predicted_team: Optional[str]
    status: str # Won, Lost, Pending

class LeaderboardResponse(BaseModel):
    match_id: int
    sport: str
    league_name: str
    team_a: str
    team_b: str
    start_time: datetime
    participants_count: int
    leaderboard: List[LeaderboardEntry]

    class Config:
        from_attributes = True


class AdminMatchCreate(BaseModel):
    sport: str = "Football"
    league_name: str
    team_a: str
    team_b: str
    start_time: datetime
    entry_fee: Decimal = 20.00
    platform_fee: Decimal = 10.00  

class AdminMatchUpdate(BaseModel):
    sport: str
    league_name: str
    team_a: str
    team_b: str
    start_time: datetime
    entry_fee: Decimal
    platform_fee: Decimal

class AdminResultEntry(BaseModel):
    score_a: int
    score_b: int