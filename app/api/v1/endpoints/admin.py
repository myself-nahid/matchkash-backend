from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from typing import List
from app.api.deps import get_db, get_current_admin_user
from app.models.match import Match, MatchStatus
from app.models.user import User, Wallet
from app.models.transaction import Transaction
from app.schemas.match import AdminMatchCreate, AdminMatchUpdate, AdminResultEntry, MatchResponse, LeaderboardResponse, LeaderboardEntry
from app.schemas.wallet import AdminTransactionResponse
from app.models.match import Match, MatchStatus, Prediction
from app.models.user import User, Wallet
from app.models.transaction import Transaction
from app.schemas.match import AdminMatchCreate, AdminMatchUpdate, AdminResultEntry, MatchResponse, LeaderboardResponse, LeaderboardEntry
from app.schemas.wallet import AdminTransactionResponse
from app.services.contest_engine import ContestEngine
from sqlalchemy.orm import joinedload
from typing import List, Optional
from decimal import Decimal
from app.services.contest_engine import ContestEngine
from sqlalchemy import func


router = APIRouter()

# --- Match Management ---

@router.get("/matches", response_model=List[MatchResponse])
async def admin_get_all_matches(
    status: Optional[str] = None, # Upcoming, Live, Completed, Cancelled
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Get all matches with participant counts and prize pools"""
    participants_subquery = (
        select(Prediction.match_id, func.count(Prediction.id).label("count"))
        .group_by(Prediction.match_id)
        .subquery()
    )
    query = (
        select(Match, participants_subquery.c.count)
        .outerjoin(participants_subquery, Match.id == participants_subquery.c.match_id)
        .order_by(Match.start_time.desc())
    )
    if status:
        query = query.where(Match.status == status.lower())
    
    result = await db.execute(query)
    matches_data = result.all()
    
    response_list = []
    for match, count in matches_data:
        participants_count = count or 0
        prize_pool = (
            (Decimal(match.entry_fee) * participants_count) *
            (1 - (Decimal(match.platform_fee_percent) / 100))
        )
        match_response = MatchResponse(
            **match.__dict__,
            participants_count=participants_count,
            prize_pool=round(prize_pool, 2)
        )
        response_list.append(match_response)
        
    return response_list

@router.post("/matches", response_model=MatchResponse)
async def admin_create_match(
    match_in: AdminMatchCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Create a new match"""
    new_match = Match(
        sport=match_in.sport,
        league_name=match_in.league_name,
        team_a=match_in.team_a,
        team_b=match_in.team_b,
        start_time=match_in.start_time,
        entry_fee=match_in.entry_fee,
        platform_fee_percent=match_in.platform_fee, # Note the name conversion
        status=MatchStatus.UPCOMING
    )
    db.add(new_match)
    await db.commit()
    await db.refresh(new_match)
    return new_match

@router.put("/matches/{match_id}", response_model=MatchResponse)
async def admin_update_match(
    match_id: int,
    match_in: AdminMatchUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Edit an existing match"""
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.status != MatchStatus.UPCOMING:
        raise HTTPException(status_code=400, detail="Cannot edit a match that is not upcoming")

    # Update fields from the request
    match.sport = match_in.sport
    match.league_name = match_in.league_name
    match.team_a = match_in.team_a
    match.team_b = match_in.team_b
    match.start_time = match_in.start_time
    match.entry_fee = match_in.entry_fee
    match.platform_fee_percent = match_in.platform_fee

    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match

@router.delete("/matches/{match_id}")
async def admin_delete_match(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Delete an upcoming match"""
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.status != MatchStatus.UPCOMING:
        raise HTTPException(status_code=400, detail="Cannot delete a match that has already started or finished")

    await db.delete(match)
    await db.commit()
    return {"message": "Match deleted successfully"}

@router.post("/matches/{match_id}/result")
async def admin_enter_result(
    match_id: int,
    result_in: AdminResultEntry,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Enter the final score for a match"""
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
        
    match.score_a = result_in.score_a
    match.score_b = result_in.score_b
    match.status = MatchStatus.COMPLETED
    
    db.add(match)
    await db.commit()

    # Trigger prize calculation in the background
    engine = ContestEngine()
    background_tasks.add_task(engine.process_match_results, db, match_id)
    
    return {"message": "Result updated, prize calculation queued."}


@router.get("/matches/{match_id}/leaderboard", response_model=LeaderboardResponse)
async def admin_get_leaderboard(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: View the leaderboard for a specific match"""
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    predictions_query = (
        select(Prediction)
        .options(joinedload(Prediction.user))
        .where(Prediction.match_id == match_id)
        .order_by(Prediction.rank.asc())
    )
    result = await db.execute(predictions_query)
    predictions = result.scalars().unique().all()
    
    leaderboard_entries = []
    for p in predictions:
        predicted_team = ""
        if p.predicted_winner == "A": predicted_team = match.team_a
        elif p.predicted_winner == "B": predicted_team = match.team_b
        else: predicted_team = "Draw"

        entry = LeaderboardEntry(
            rank=p.rank,
            player_name=p.user.full_name,
            player_phone=p.user.phone,
            predicted_team=predicted_team,
            status=p.status
        )
        leaderboard_entries.append(entry)

    return LeaderboardResponse(
        match_id=match.id,
        sport=match.sport,
        league_name=match.league_name,
        team_a=match.team_a,
        team_b=match.team_b,
        start_time=match.start_time,
        participants_count=len(leaderboard_entries),
        leaderboard=leaderboard_entries
    )

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