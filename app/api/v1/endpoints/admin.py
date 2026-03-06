from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from typing import List
from app.api.deps import get_db, get_current_admin_user
from app.models.match import Match, MatchStatus
from app.models.user import User, Wallet
from app.models.transaction import Transaction
from app.schemas.match import MatchCreate
from app.schemas.wallet import AdminTransactionResponse
from app.services.contest_engine import ContestEngine

router = APIRouter()

# Match Management
@router.post("/matches")
async def create_match(
    match_in: MatchCreate, 
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    match = Match(**match_in.dict())
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match

@router.post("/matches/{match_id}/result")
async def set_match_result(
    match_id: int,
    score_a: int,
    score_b: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
        
    match.score_a = score_a
    match.score_b = score_b
    match.status = MatchStatus.COMPLETED
    
    db.add(match)
    await db.commit()

    engine = ContestEngine()
    background_tasks.add_task(engine.process_match_results, db, match_id)
    
    return {"message": "Result updated, prize calculation queued."}

# Withdrawal Management 
@router.get("/withdrawals", response_model=List[AdminTransactionResponse])
async def get_all_withdrawals(
    status: str = "All", # Can be All, Pending, Completed, Rejected
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: View all withdrawal requests with user details"""
    query = (
        select(Transaction)
        .options(joinedload(Transaction.user))
        .where(Transaction.type == "Withdraw")
        .order_by(Transaction.created_at.desc())
    )
    
    if status != "All":
        query = query.where(Transaction.status == status)
        
    result = await db.execute(query)
    return result.scalars().unique().all()


@router.post("/withdrawals/{transaction_id}/approve", response_model=AdminTransactionResponse)
async def approve_withdrawal(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Approve a pending withdrawal request"""
    tx = await db.get(Transaction, transaction_id, options=[joinedload(Transaction.user)])
    
    if not tx or tx.type != "Withdraw" or tx.status != "Pending":
        raise HTTPException(status_code=404, detail="Pending withdrawal not found")

    # Change status to Completed
    tx.status = "Completed"
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    
    return tx

@router.post("/withdrawals/{transaction_id}/reject", response_model=AdminTransactionResponse)
async def reject_withdrawal(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Reject a pending withdrawal and refund the user"""
    tx = await db.get(Transaction, transaction_id, options=[joinedload(Transaction.user)])
    
    if not tx or tx.type != "Withdraw" or tx.status != "Pending":
        raise HTTPException(status_code=404, detail="Pending withdrawal not found")

    # 1. Change status to Rejected
    tx.status = "Rejected"

    # 2. Find user's wallet and REFUND the money
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == tx.user_id))
    if wallet:
        # Amount is negative (e.g., -100), so subtracting it will add it back
        wallet.balance -= tx.amount 
        db.add(wallet)

    db.add(tx)
    await db.commit()
    await db.refresh(tx)

    return tx