from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

# Responses
class WalletResponse(BaseModel):
    balance: Decimal
    total_won: Decimal
    total_deposited: Decimal

    class Config:
        from_attributes = True

class TransactionResponse(BaseModel):
    id: int
    amount: Decimal
    type: str       # Deposit, Withdraw, Entry Fee, Winning Payout
    status: str     # Completed, Pending, Rejected
    reference: Optional[str] # Stores the Moncash/Natcash number
    created_at: datetime

    class Config:
        from_attributes = True

# Requests 
class DepositRequest(BaseModel):
    amount: Decimal
    method: str          # "Moncash" or "Natcash"
    phone_number: str    # The number entered in the UI

class WithdrawRequest(BaseModel):
    amount: Decimal
    method: str          # "Moncash" or "Natcash"
    phone_number: str

class AdminTransactionUser(BaseModel):
    full_name: Optional[str]
    phone: str

    class Config:
        from_attributes = True

class AdminTransactionResponse(BaseModel):
    id: int
    amount: Decimal
    status: str
    created_at: datetime
    reference: Optional[str]
    user: AdminTransactionUser 

    class Config:
        from_attributes = True