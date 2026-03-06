from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.api.deps import get_db, get_current_user
from app.models.user import User, Wallet
from app.models.transaction import Transaction
from app.schemas.wallet import WalletResponse, TransactionResponse, DepositRequest, WithdrawRequest
from decimal import Decimal

router = APIRouter()

@router.get("/me", response_model=WalletResponse)
async def get_my_wallet(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current balance, total won, and total deposited"""
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet

@router.get("/transactions", response_model=List[TransactionResponse])
async def get_my_transactions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get history for the Wallet screen"""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
    )
    return result.scalars().all()

@router.post("/deposit")
async def request_deposit(
    request: DepositRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mock Deposit: Instantly adds money for testing.
    Later, this will connect to MonCash/NatCash Webhooks.
    """
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    
    # 1. Add money to wallet
    wallet.balance += request.amount
    wallet.total_deposited += request.amount

    # 2. Record Transaction
    tx = Transaction(
        user_id=user.id,
        amount=request.amount,
        type="Deposit",
        status="Completed",
        reference=f"{request.method} - {request.phone_number}"
    )
    
    db.add(wallet)
    db.add(tx)
    await db.commit()
    
    return {"message": "Deposit successful", "new_balance": wallet.balance}

@router.post("/withdraw")
async def request_withdrawal(
    request: WithdrawRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit a withdrawal request (Goes to Pending status)"""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    
    if wallet.balance < request.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # 1. Deduct immediately to prevent user from spending it while pending
    wallet.balance -= request.amount
    
    # 2. Record Transaction as 'Pending'
    tx = Transaction(
        user_id=user.id,
        amount=-request.amount, # Negative because it's a deduction
        type="Withdraw",
        status="Pending",
        reference=f"{request.method} - {request.phone_number}"
    )
    
    db.add(wallet)
    db.add(tx)
    await db.commit()
    
    return {"message": "Withdrawal request submitted successfully. Waiting for admin approval."}