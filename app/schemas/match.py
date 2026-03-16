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
    match_title: str
    sport_name: str
    league_name: str
    match_date: datetime
    match_time_start: datetime
    team_a: str
    team_b: str
    team_a_logo: Optional[str] = None
    team_b_logo: Optional[str] = None
    platform_fee_percent: Decimal
    promotional_amount: Decimal
    feature_match: int
    entry_fee: Decimal
    image_url: Optional[str] = None
    status: str
    entry_fee: Decimal
    
    # Dynamically calculated fields for the UI
    prize_pool: Decimal = 0.00
    participants_count: int = 0
    
    class Config:
        from_attributes = True

# --- For "All Predictions" Screen (Response) ---
class MyPredictionResponse(BaseModel):
    id: int
    match_id: int
    league_name: str
    team_a: str
    team_b: str
    match_date: datetime
    
    # User's Input
    predicted_winner: str
    predicted_score_a: int
    predicted_score_b: int
    
    # Results
    actual_score_a: Optional[int]
    actual_score_b: Optional[int]
    status: str  # WON, LOST, PENDING
    rank: Optional[int]
    prize_amount: Decimal # e.g. +200.00 or 0.00

    class Config:
        from_attributes = True

class LeagueResponse(BaseModel):
    name: str

# --- For Dropdowns ---
class LeagueListResponse(BaseModel):
    leagues: List[str]

# --- Response: My Predictions Screen ---
class MyPredictionCard(BaseModel):
    match_id: int
    league_name: str
    team_a: str
    team_b: str
    match_date: datetime
    
    # Prediction details
    predicted_team: str  # "Team A", "Team B", "Draw"
    predicted_score_a: int
    predicted_score_b: int
    
    # Results (Optional if match isn't over)
    actual_score_a: Optional[int]
    actual_score_b: Optional[int]
    
    # Status & Stats
    status: str          # "PENDING", "WON", "LOST"
    rank_text: str       # E.g., "3/200" or "-"
    pnl_amount: Decimal  # E.g., +200.00 or -20.00
    pnl_color: str       # "green", "red", "yellow" (Helper for UI)

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
    match_time_start: datetime
    participants_count: int
    leaderboard: List[LeaderboardEntry]

    class Config:
        from_attributes = True


class AdminMatchCreate(BaseModel):
    sport: str = "Football"
    league_name: str
    team_a: str
    team_b: str
    match_time_start: datetime
    entry_fee: Decimal = 20.00
    platform_fee: Decimal = 10.00  

class AdminMatchUpdate(BaseModel):
    sport: str
    league_name: str
    team_a: str
    team_b: str
    match_time_start: datetime
    entry_fee: Decimal
    platform_fee: Decimal

class AdminResultEntry(BaseModel):
    score_a: int
    score_b: int
    winning_team: str # "A", "B", or "Draw"