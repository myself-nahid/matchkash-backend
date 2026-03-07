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
from app.schemas.admin import DashboardStatsResponse, AdminUserListResponse, AdminUserDetailResponse, AdminWalletDetail, AdminTransactionDetail, AdminPredictionDetail, AdminUserWalletPopup, AdminUserTransactionPopup, AdminUserPredictionPopup
from app.services.contest_engine import ContestEngine
from sqlalchemy.orm import joinedload
from typing import List, Optional
from decimal import Decimal
from app.services.contest_engine import ContestEngine
from sqlalchemy import func
from datetime import datetime, date
from sqlalchemy import extract


router = APIRouter()

@router.get("/dashboard", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Gathers all statistics for the main admin dashboard page."""
    
    today = date.today()
    current_year = today.year

    # --- Card Calculations ---
    total_users_q = select(func.count(User.id))
    active_matches_q = select(func.count(Match.id)).where(Match.status.in_(['upcoming', 'live']))
    pending_withdrawals_q = select(func.count(Transaction.id)).where(Transaction.type == "Withdraw", Transaction.status == "Pending")
    active_users_today_q = select(func.count(func.distinct(Prediction.user_id))).where(func.date(Prediction.created_at) == today)

    # Financial calculations from predictions
    financial_q = select(
        func.sum(Match.entry_fee).label("total_collection"),
        func.sum(Match.entry_fee * (Match.platform_fee_percent / 100)).label("total_revenue")
    ).join(Prediction, Match.id == Prediction.match_id)

    # Execute all queries
    total_users = await db.scalar(total_users_q)
    active_matches = await db.scalar(active_matches_q)
    pending_withdrawals = await db.scalar(pending_withdrawals_q)
    active_users_today = await db.scalar(active_users_today_q)
    financial_res = (await db.execute(financial_q)).first()

    # --- Monthly Revenue Chart Calculation ---
    monthly_revenue_data = []
    for month in range(1, 13):
        monthly_revenue_q = select(func.sum(Match.entry_fee * (Match.platform_fee_percent / 100))).\
            join(Prediction, Match.id == Prediction.match_id).\
            where(
                extract('year', Prediction.created_at) == current_year,
                extract('month', Prediction.created_at) == month
            )
        
        monthly_revenue = await db.scalar(monthly_revenue_q)
        monthly_revenue_data.append(monthly_revenue or Decimal('0.0'))

    return DashboardStatsResponse(
        total_users=total_users or 0,
        active_matches=active_matches or 0,
        pending_withdrawals=pending_withdrawals or 0,
        active_users_today=active_users_today or 0,
        total_entry_collection=financial_res.total_collection if financial_res else Decimal('0.0'),
        total_platform_revenue=financial_res.total_revenue if financial_res else Decimal('0.0'),
        monthly_revenue=monthly_revenue_data
    )

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

@router.get("/users", response_model=List[AdminUserListResponse])
async def admin_get_all_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Get a list of all users with summary stats"""
    
    # Subquery to count contests joined by each user
    contest_joined_sq = select(Prediction.user_id, func.count().label("contest_count")).group_by(Prediction.user_id).subquery()
    # Subquery to count contests won
    win_sq = select(Prediction.user_id, func.count().label("win_count")).where(Prediction.status == "WON").group_by(Prediction.user_id).subquery()
    # Subquery to count contests lost
    lose_sq = select(Prediction.user_id, func.count().label("lose_count")).where(Prediction.status == "LOST").group_by(Prediction.user_id).subquery()

    query = (
        select(
            User.id, User.full_name, User.phone, User.is_active,
            func.coalesce(Wallet.balance, Decimal('0.00')).label("balance"), 
            func.coalesce(contest_joined_sq.c.contest_count, 0).label("contest_joined"),
            func.coalesce(win_sq.c.win_count, 0).label("total_win"),
            func.coalesce(lose_sq.c.lose_count, 0).label("total_lose")
        )
        .outerjoin(Wallet, User.id == Wallet.user_id)
        .outerjoin(contest_joined_sq, User.id == contest_joined_sq.c.user_id)
        .outerjoin(win_sq, User.id == win_sq.c.user_id)
        .outerjoin(lose_sq, User.id == lose_sq.c.user_id)
        .order_by(User.id.desc())
    )
    
    result = await db.execute(query)
    users_data = result.mappings().all() # .mappings() allows dict-like access

    return [AdminUserListResponse(**user) for user in users_data]

@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def admin_get_user_details(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Get full details of a single user (for popups)"""
    user = await db.get(
        User, user_id, 
        options=[
            joinedload(User.wallet), 
            joinedload(User.transactions).joinedload(Transaction.user), # Eager load for performance
            joinedload(User.predictions).joinedload(Prediction.match)
        ]
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Calculate total withdrawn for wallet details
    total_withdrawn_q = select(func.sum(Transaction.amount)).where(
        Transaction.user_id == user_id,
        Transaction.type == "Withdraw",
        Transaction.status == "Completed"
    )
    total_withdrawn = abs(await db.scalar(total_withdrawn_q) or Decimal('0.0'))

    # Format response
    return AdminUserDetailResponse(
        id=user.id,
        full_name=user.full_name,
        phone=user.phone,
        created_at=user.created_at,
        is_active=user.is_active,
        wallet=AdminWalletDetail(
            balance=user.wallet.balance,
            total_won=user.wallet.total_won,
            total_deposited=user.wallet.total_deposited,
            total_withdrawn=total_withdrawn
        ),
        transactions=[AdminTransactionDetail.from_orm(tx) for tx in sorted(user.transactions, key=lambda x: x.created_at, reverse=True)],
        predictions=[AdminPredictionDetail(
            match_id=p.match.id,
            league_name=p.match.league_name,
            team_a=p.match.team_a,
            team_b=p.match.team_b,
            predicted_winner=p.predicted_winner,
            predicted_score_a=p.predicted_score_a,
            predicted_score_b=p.predicted_score_b,
            status=p.status,
            rank=p.rank,
            prize_amount=p.prize_amount,
            created_at=p.created_at
        ) for p in sorted(user.predictions, key=lambda x: x.created_at, reverse=True)]
    )


@router.post("/users/{user_id}/toggle_status")
async def admin_toggle_user_status(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Suspend (deactivate) or reactivate a user"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = not user.is_active
    db.add(user)
    await db.commit()
    
    status = "activated" if user.is_active else "suspended"
    return {"message": f"User has been successfully {status}."}


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Admin: Permanently delete a user. Use with caution."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()
    return {"message": "User has been permanently deleted."}



@router.get("/users/{user_id}/wallet", response_model=AdminUserWalletPopup)
async def get_user_wallet_details(
    user_id: int, 
    db: AsyncSession = Depends(get_db), 
    admin: User = Depends(get_current_admin_user)
):
    """Data for the 'Wallet' Modal"""
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    # Aggregate transactions to get exact totals for the UI
    transactions = await db.scalars(select(Transaction).where(Transaction.user_id == user_id))
    
    total_deposit = Decimal('0.0')
    total_withdrawal = Decimal('0.0')
    total_winning = Decimal('0.0')
    total_deduction = Decimal('0.0')

    for tx in transactions:
        amount = abs(tx.amount)
        if tx.type.upper() == "DEPOSIT":
            total_deposit += amount
        elif tx.type.upper() == "WITHDRAW" and tx.status == "Completed":
            total_withdrawal += amount
        elif tx.type.upper() == "WINNING_PAYOUT":
            total_winning += amount
        elif tx.type.upper() == "ENTRY_FEE":
            total_deduction += amount

    return AdminUserWalletPopup(
        total_balance=wallet.balance,
        total_deposit=total_deposit,
        total_withdrawal=total_withdrawal,
        total_winning=total_winning,
        total_deduction=total_deduction
    )


@router.get("/users/{user_id}/transactions", response_model=List[AdminUserTransactionPopup])
async def get_user_transaction_details(
    user_id: int, 
    db: AsyncSession = Depends(get_db), 
    admin: User = Depends(get_current_admin_user)
):
    """Data for the 'Transaction History' Modal"""
    transactions = await db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
    )

    # Fetch all matches in one go to map the League Names efficiently
    all_matches = await db.scalars(select(Match))
    match_dict = {m.id: m.league_name for m in all_matches}

    response =[]
    for tx in transactions:
        # Map database types to exact UI text
        ui_type = tx.type
        if tx.type.upper() == "WINNING_PAYOUT": ui_type = "Win"
        elif tx.type.upper() == "ENTRY_FEE": ui_type = "Deduction"

        # Extract Match ID from reference (e.g., "Match: 5")
        match_name = ""
        if tx.reference and tx.reference.startswith("Match:"):
            try:
                m_id = int(tx.reference.split(":")[1].strip())
                match_name = match_dict.get(m_id, "")
            except:
                pass

        response.append(AdminUserTransactionPopup(
            date=tx.created_at,
            type=ui_type,
            amount=abs(tx.amount),
            match_name=match_name
        ))

    return response


@router.get("/users/{user_id}/predictions", response_model=List[AdminUserPredictionPopup])
async def get_user_prediction_details(
    user_id: int, 
    db: AsyncSession = Depends(get_db), 
    admin: User = Depends(get_current_admin_user)
):
    """Data for the 'Prediction Details' Modal"""
    predictions = await db.scalars(
        select(Prediction)
        .options(joinedload(Prediction.match))
        .where(Prediction.user_id == user_id)
        .order_by(Prediction.created_at.desc())
    )

    response =[]
    for p in predictions:
        m = p.match
        
        # Determine the name of the predicted team
        if p.predicted_winner == "A":
            predicted_team_name = m.team_a
        elif p.predicted_winner == "B":
            predicted_team_name = m.team_b
        else:
            predicted_team_name = "Draw"

        # Format Dates exactly like the UI
        # 12/12/2024
        match_date_str = m.start_time.strftime("%d/%m/%Y") 
        # 8.00am
        match_time_str = m.start_time.strftime("%I.%M%p").lower() 
        if match_time_str.startswith('0'): 
            match_time_str = match_time_str[1:] # Remove leading zero (e.g., 08.00am -> 8.00am)

        response.append(AdminUserPredictionPopup(
            sport_name=m.sport,
            league_name=m.league_name,
            match_date=match_date_str,
            match_time_start=match_time_str,
            team_a=m.team_a,
            team_b=m.team_b,
            prediction=predicted_team_name
        ))

    return response

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