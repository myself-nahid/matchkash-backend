from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.api.deps import get_db, get_current_user
from app.models.user import User, Wallet
from app.models.transaction import Transaction
from app.schemas.wallet import WalletResponse, TransactionResponse, WithdrawalRequest

router = APIRouter()

@router.get("/balance", response_model=WalletResponse)
async def get_wallet_balance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    return wallet

@router.get("/transactions", response_model=List[TransactionResponse])
async def get_transaction_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
    )
    return result.scalars().all()

@router.post("/withdraw")
async def request_withdrawal(
    request: WithdrawalRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    
    if wallet.balance < request.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Deduct immediately to prevent double spending
    wallet.balance -= request.amount
    
    # Create Transaction Record
    tx = Transaction(
        user_id=user.id,
        amount=-request.amount,
        type="WITHDRAW",
        status="PENDING", # Needs Admin Approval
        reference=f"{request.method}: {request.account_number}"
    )
    
    db.add(wallet)
    db.add(tx)
    await db.commit()
    
    return {"message": "Withdrawal request submitted successfully"}