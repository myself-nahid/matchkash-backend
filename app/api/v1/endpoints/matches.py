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
        query = query.where(Match.sport == sport)
    
    result = await db.execute(query)
    leagues = result.scalars().all()
    return {"leagues": leagues}


@router.get("", response_model=List[MatchResponse])
async def get_matches(
    # Filters based on UI
    tab: str = "All",          # All, Latest, Upcoming, Completed
    sport: Optional[str] = None, # Football, Basketball
    league: Optional[str] = None,
    match_date: Optional[date] = None, # Pick a Date
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Home Screen Main API. 
    Handles 'All', 'Football', 'Basketball', Date Picker, and League Select.
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
        .order_by(Match.start_time.asc())
    )

    # 3. Apply Filters
    
    # Filter: Sport (Football/Basketball)
    if sport and sport != "All":
        query = query.where(Match.sport == sport)

    # Filter: League Dropdown
    if league:
        query = query.where(Match.league_name == league)

    # Filter: Pick a Date
    if match_date:
        # Cast datetime to date for comparison
        query = query.where(func.date(Match.start_time) == match_date)

    # Filter: Tabs (All, Latest, Upcoming, Completed)
    current_time = datetime.utcnow()
    
    if tab.lower() == "upcoming":
        query = query.where(Match.status == "upcoming").where(Match.start_time > current_time)
    elif tab.lower() == "completed":
        query = query.where(Match.status == "completed")
    elif tab.lower() == "latest":
        # Logic: Show Live matches first, then Upcoming matches starting very soon
        query = query.where(Match.status.in_(["live", "upcoming"])).order_by(Match.start_time.asc())
    
    # Execute
    result = await db.execute(query)
    matches_data = result.all()

    # 4. Format Response with Prize Pool Calculation
    response_list = []
    for match, count in matches_data:
        participants_count = count or 0
        
        # Prize Pool = (Entry * Users) - Platform Fee
        gross_pool = Decimal(match.entry_fee) * participants_count
        fee_amount = gross_pool * (Decimal(match.platform_fee_percent) / 100)
        prize_pool = gross_pool - fee_amount
        
        match_response = MatchResponse(
            **match.__dict__,
            participants_count=participants_count,
            prize_pool=round(prize_pool, 2)
        )
        response_list.append(match_response)
        
    return response_list

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


@router.get("/my-predictions", response_model=List[MyPredictionResponse])
async def get_my_predictions(
    filter: str = "All", # All, Latest, Won, Lose
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    'All Predictions' Screen API.
    Handles tabs: All, Latest (Pending), Won, Lose.
    """
    query = (
        select(Prediction)
        .options(joinedload(Prediction.match)) # Eager load match details
        .where(Prediction.user_id == user.id)
        .order_by(Prediction.created_at.desc())
    )

    # UI Tab Filters
    if filter.lower() == "won":
        query = query.where(Prediction.status == "WON")
    elif filter.lower() == "lose":
        query = query.where(Prediction.status == "LOST")
    elif filter.lower() == "latest":
        # 'Latest' usually means Active/Pending matches in this context
        query = query.where(Prediction.status == "PENDING")

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
            match_date=p.match.start_time,
            predicted_winner=p.predicted_winner,
            predicted_score_a=p.predicted_score_a,
            predicted_score_b=p.predicted_score_b,
            actual_score_a=p.match.score_a,
            actual_score_b=p.match.score_b,
            status=p.status,
            rank=p.rank,
            prize_amount=p.prize_amount
        ))
    
    return response

# Leaderboard Screen Endpoint
@router.get("/{match_id}/leaderboard", response_model=LeaderboardResponse)
async def get_match_leaderboard(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Fetches the detailed leaderboard for a specific match"""
    
    # 1. Get Match Details
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # 2. Get all predictions for this match, joining user data
    predictions_query = (
        select(Prediction)
        .options(joinedload(Prediction.user))
        .where(Prediction.match_id == match_id)
        .order_by(Prediction.rank.asc())
    )
    result = await db.execute(predictions_query)
    predictions = result.scalars().unique().all()
    
    # 3. Format the leaderboard entries
    leaderboard_entries = []
    for p in predictions:
        # Determine predicted team
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