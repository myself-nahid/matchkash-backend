from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

class DashboardStatsResponse(BaseModel):
    # Top row cards
    total_users: int
    active_matches: int
    total_entry_collection: Decimal
    total_platform_revenue: Decimal
    
    # Second row cards
    active_users_today: int
    pending_withdrawals: int
    
    # Chart data
    monthly_revenue: List[Decimal] # A list of 12 values, for Jan-Dec

class AdminUserListResponse(BaseModel):
    id: int
    full_name: Optional[str]
    phone: str
    balance: Decimal
    contest_joined: int
    total_win: int
    total_lose: int
    is_active: bool  # To show status as "Active" or "Removed"

    class Config:
        from_attributes = True

# --- For Detailed User View (Popups) ---

class AdminPredictionDetail(BaseModel):
    match_id: int
    league_name: str
    team_a: str
    team_b: str
    predicted_winner: str
    predicted_score_a: int
    predicted_score_b: int
    status: str
    rank: Optional[int]
    prize_amount: Decimal
    created_at: datetime

class AdminTransactionDetail(BaseModel):
    id: int
    type: str
    amount: Decimal
    status: str
    reference: Optional[str]
    created_at: datetime

class AdminWalletDetail(BaseModel):
    balance: Decimal
    total_won: Decimal
    total_deposited: Decimal
    total_withdrawn: Decimal
    
class AdminUserDetailResponse(BaseModel):
    id: int
    full_name: Optional[str]
    phone: str
    created_at: datetime
    is_active: bool
    wallet: AdminWalletDetail
    transactions: List[AdminTransactionDetail]
    predictions: List[AdminPredictionDetail]

    class Config:
        from_attributes = True

# 1. Wallet Popup Schema 
class AdminUserWalletPopup(BaseModel):
    total_balance: Decimal
    total_deposit: Decimal
    total_withdrawal: Decimal
    total_winning: Decimal
    total_deduction: Decimal

# 2. Transaction History Popup Schema 
class AdminUserTransactionPopup(BaseModel):
    date: datetime
    type: str         # "Deposit", "Withdraw", "Win", "Deduction" (Mapped for UI)
    amount: Decimal
    match_name: str   # E.g., "Fifa world cup" or empty string

# 3. Prediction Details Popup Schema
class AdminUserPredictionPopup(BaseModel):
    sport_name: str
    league_name: str
    match_date: str       # E.g., "12/12/2026"
    match_time_start: str # E.g., "8.00am"
    team_a: str
    team_b: str
    prediction: str       # E.g., "Team A" or "Draw"