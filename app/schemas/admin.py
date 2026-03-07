from pydantic import BaseModel
from typing import List
from decimal import Decimal

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