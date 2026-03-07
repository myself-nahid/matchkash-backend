from pydantic import BaseModel, model_validator
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

# Revenue Dashboard Schema 
class RevenueStatsResponse(BaseModel):
    # Summary Cards
    todays_revenue: Decimal
    this_weeks_revenue: Decimal
    this_months_revenue: Decimal
    total_revenue: Decimal
    total_entry_collected: Decimal
    total_prize_distributed: Decimal

    # Charts
    monthly_revenue: List[Decimal]  # 12 items (Jan - Dec)
    weekly_revenue: List[Decimal]   # 5 items (Week 1 - Week 5 of current month)
    daily_revenue: List[Decimal]    # 7 items (Sun - Sat of current week)

    class Config:
        from_attributes = True

# --- Settings: Account Info ---
class AdminAccountUpdate(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class AdminAccountResponse(BaseModel):
    email: Optional[str]
    phone: str
    address: Optional[str]

    class Config:
        from_attributes = True

# --- Settings: Security ---
class AdminSecurityUpdate(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str

    @model_validator(mode='after')
    def check_passwords_match(self) -> 'AdminSecurityUpdate':
        if self.new_password != self.confirm_new_password:
            raise ValueError('New passwords do not match')
        return self

# --- Settings: Language ---
class AdminLanguageUpdate(BaseModel):
    language: str

# --- Settings: Legal/Policies ---
class SystemPolicySchema(BaseModel):
    terms_and_conditions: Optional[str] = None
    contest_rules: Optional[str] = None

    class Config:
        from_attributes = True