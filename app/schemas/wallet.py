from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime

class WalletResponse(BaseModel):
    balance: Decimal
    total_won: Decimal
    total_deposited: Decimal

    class Config:
        from_attributes = True

class TransactionResponse(BaseModel):
    id: int
    amount: Decimal
    type: str
    status: str
    reference: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class WithdrawalRequest(BaseModel):
    amount: Decimal
    method: str  # "MonCash" or "NatCash"
    account_number: str