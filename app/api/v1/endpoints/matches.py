from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import date, datetime
from typing import List, Optional
from decimal import Decimal
from app.api.deps import get_db, get_current_user
from app.models.match import Match, Prediction, MatchStatus
from app.models.user import Wallet, User
from app.models.transaction import Transaction
from sqlalchemy.orm import joinedload
from app.schemas.match import PredictionCreate, MatchResponse, MyPredictionResponse, LeagueListResponse, LeaderboardResponse, LeaderboardEntry

router = APIRouter()

# HOME SCREEN ENDPOINTS
@router.get("/leagues", response_model=LeagueListResponse)
async def get_leagues(
    sport: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Populate the 'Select League' dropdown"""
    query = select(Match.league_name).distinct()
    if sport:
        query = query.where(Match.sport_name == sport)
    
    result = await db.execute(query)
    leagues = result.scalars().all()
    return {"leagues": leagues}


@router.get("", response_model=dict)
async def get_matches(
    tab: str = "All",
    sport: Optional[str] = None,
    league: Optional[str] = None,
    match_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Home Screen Main API. 
    Handles 'All', 'Football', 'Basketball', Date Picker, and League Select.
    Supports pagination via ?page=1&page_size=10
    """
    
    # 1. Subquery for participants count
    participants_subquery = (
        select(Prediction.match_id, func.count(Prediction.id).label("count"))
        .group_by(Prediction.match_id)
        .subquery()
    )

    # 2. Main Query
    query = (
        select(Match, participants_subquery.c.count)
        .outerjoin(participants_subquery, Match.id == participants_subquery.c.match_id)
        .order_by(Match.match_time_start.asc())
    )

    # 3. Apply Filters
    current_time = datetime.utcnow()

    if sport and sport != "All":
        query = query.where(Match.sport_name == sport)

    if league:
        query = query.where(Match.league_name == league)

    if match_date:
        query = query.where(func.date(Match.match_time_start) == match_date)

    if tab.lower() == "upcoming":
        query = query.where(Match.status == "upcoming").where(Match.match_time_start > current_time)
    elif tab.lower() == "completed":
        query = query.where(Match.status == "completed")
    elif tab.lower() == "latest":
        query = query.where(Match.status.in_(["live", "upcoming"])).order_by(Match.match_time_start.asc())

    # 4. Count total records before pagination
    count_query = select(func.count(Match.id))
    if sport and sport != "All":
        count_query = count_query.where(Match.sport_name == sport)
    if league:
        count_query = count_query.where(Match.league_name == league)
    if match_date:
        count_query = count_query.where(func.date(Match.match_time_start) == match_date)
    if tab.lower() == "upcoming":
        count_query = count_query.where(Match.status == "upcoming").where(Match.match_time_start > current_time)
    elif tab.lower() == "completed":
        count_query = count_query.where(Match.status == "completed")
    elif tab.lower() == "latest":
        count_query = count_query.where(Match.status.in_(["live", "upcoming"]))

    total_records = await db.scalar(count_query)
    total_pages = (total_records + page_size - 1) // page_size

    # 5. Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Execute
    result = await db.execute(query)
    matches_data = result.all()

    # 6. Format Response with Prize Pool Calculation
    response_list = []
    for match, count in matches_data:
        participants_count = count or 0
        
        gross_pool = Decimal(match.entry_fee) * participants_count
        fee_amount = gross_pool * (Decimal(match.platform_fee_percent) / 100)
        prize_pool = gross_pool - fee_amount
        
        match_response = MatchResponse(
            **match.__dict__,
            participants_count=participants_count,
            prize_pool=round(prize_pool, 2)
        )
        response_list.append(match_response)

    return {
        "page": page,
        "page_size": page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "data": response_list
    }

# PREDICTION ENDPOINTS (JOIN & HISTORY)
@router.post("/join")
async def join_contest(
    prediction_in: PredictionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """'Predict Now' Button Logic"""
    match = await db.get(Match, prediction_in.match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if match.status != MatchStatus.UPCOMING:
        raise HTTPException(status_code=400, detail="Prediction locked. Match has started.")

    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    if not wallet or wallet.balance < match.entry_fee:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    existing = await db.scalar(select(Prediction).where(
        Prediction.user_id == user.id, 
        Prediction.match_id == match.id
    ))
    if existing:
        raise HTTPException(status_code=400, detail="You have already joined this contest")

    # Deduct Fee
    wallet.balance -= match.entry_fee
    db.add(wallet)

    # Save Prediction
    prediction = Prediction(
        user_id=user.id,
        match_id=match.id,
        predicted_winner=prediction_in.predicted_winner,
        predicted_score_a=prediction_in.predicted_score_a,
        predicted_score_b=prediction_in.predicted_score_b,
        status="PENDING"
    )
    db.add(prediction)

    # Log Transaction
    tx = Transaction(
        user_id=user.id,
        amount=-match.entry_fee,
        type="Entry Fee",
        status="Completed",
        reference=f"Match: {match.id}"
    )
    db.add(tx)

    await db.commit()
    return {"message": "Prediction submitted successfully. Good luck!"}


@router.get("/my-predictions", response_model=dict)
async def get_my_predictions(
    filter: str = "All",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    'All Predictions' Screen API.
    Handles tabs: All, Latest (Pending), Won, Lose.
    Supports pagination via ?page=1&page_size=10
    """
    query = (
        select(Prediction)
        .options(joinedload(Prediction.match))
        .where(Prediction.user_id == user.id)
        .order_by(Prediction.created_at.desc())
    )

    if filter.lower() == "won":
        query = query.where(Prediction.status == "WON")
    elif filter.lower() == "lose":
        query = query.where(Prediction.status == "LOST")
    elif filter.lower() == "latest":
        query = query.where(Prediction.status == "PENDING")

    # Count total records before pagination
    count_query = select(func.count(Prediction.id)).where(Prediction.user_id == user.id)
    if filter.lower() == "won":
        count_query = count_query.where(Prediction.status == "WON")
    elif filter.lower() == "lose":
        count_query = count_query.where(Prediction.status == "LOST")
    elif filter.lower() == "latest":
        count_query = count_query.where(Prediction.status == "PENDING")

    total_records = await db.scalar(count_query)
    total_pages = (total_records + page_size - 1) // page_size

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    predictions = result.scalars().all()

    response = []
    for p in predictions:
        response.append(MyPredictionResponse(
            id=p.id,
            match_id=p.match.id,
            league_name=p.match.league_name,
            team_a=p.match.team_a,
            team_b=p.match.team_b,
            team_a_logo=p.match.team_a_logo,
            team_b_logo=p.match.team_b_logo,
            match_date=p.match.match_time_start,
            predicted_winner=p.predicted_winner,
            predicted_score_a=p.predicted_score_a,
            predicted_score_b=p.predicted_score_b,
            actual_score_a=p.match.score_a,
            actual_score_b=p.match.score_b,
            status=p.status,
            rank=p.rank,
            prize_amount=p.prize_amount
        ))

    return {
        "page": page,
        "page_size": page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "data": response
    }


@router.get("/{match_id}", response_model=MatchResponse)
async def get_match_detail(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get single match details by ID with calculated prize pool and participants count"""
    
    # 1. Subquery for participants count for this specific match
    participants_subquery = (
        select(Prediction.match_id, func.count(Prediction.id).label("count"))
        .where(Prediction.match_id == match_id)
        .group_by(Prediction.match_id)
        .subquery()
    )

    # 2. Query match and join with count
    query = (
        select(Match, participants_subquery.c.count)
        .outerjoin(participants_subquery, Match.id == participants_subquery.c.match_id)
        .where(Match.id == match_id)
    )

    result = await db.execute(query)
    match_data = result.one_or_none()

    if not match_data:
        raise HTTPException(status_code=404, detail="Match not found")

    match, count = match_data
    participants_count = count or 0

    # Calculate Prize Pool (Gross pool - Platform Fee)
    gross_pool = Decimal(match.entry_fee) * participants_count
    fee_amount = gross_pool * (Decimal(match.platform_fee_percent) / 100)
    prize_pool = gross_pool - fee_amount

    return MatchResponse(
        **match.__dict__,
        participants_count=participants_count,
        prize_pool=round(prize_pool, 2)
    )

# Leaderboard Screen Endpoint
@router.get("/{match_id}/leaderboard", response_model=dict)
async def get_match_leaderboard(
    match_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Fetches the detailed leaderboard for a specific match.
    Supports pagination via ?page=1&page_size=10
    """
    
    # 1. Get Match Details
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # 2. Count total predictions
    total_records = await db.scalar(
        select(func.count(Prediction.id)).where(Prediction.match_id == match_id)
    )
    total_pages = (total_records + page_size - 1) // page_size

    # 3. Get paginated predictions
    predictions_query = (
        select(Prediction)
        .options(joinedload(Prediction.user))
        .where(Prediction.match_id == match_id)
        .order_by(Prediction.rank.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(predictions_query)
    predictions = result.scalars().unique().all()
    
    # 4. Format the leaderboard entries
    leaderboard_entries = []
    for p in predictions:
        predicted_team = ""
        if p.predicted_winner == "A":
            predicted_team = match.team_a
        elif p.predicted_winner == "B":
            predicted_team = match.team_b
        else:
            predicted_team = "Draw"

        entry = LeaderboardEntry(
            rank=p.rank,
            player_name=p.user.full_name,
            player_phone=p.user.phone,
            predicted_team=predicted_team,
            status=p.status
        )
        leaderboard_entries.append(entry)

    return {
        "page": page,
        "page_size": page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "data": LeaderboardResponse(
            match_id=match.id,
            sport=match.sport_name,
            league_name=match.league_name,
            team_a=match.team_a,
            team_b=match.team_b,
            match_time_start=match.match_time_start,
            participants_count=len(leaderboard_entries),
            leaderboard=leaderboard_entries
        )
    }