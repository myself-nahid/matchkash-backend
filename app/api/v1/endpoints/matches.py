from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload, aliased
from datetime import datetime
from typing import List
from decimal import Decimal

# Dependency and Model Imports
from app.api.deps import get_db, get_current_user
from app.models.match import Match, Prediction, MatchStatus
from app.models.user import Wallet, User
from app.models.transaction import Transaction

# Schema Imports
from app.schemas.match import PredictionCreate, MatchResponse, LeaderboardResponse, LeaderboardEntry

router = APIRouter()


# --- Home Screen Endpoint ---

@router.get("", response_model=List[MatchResponse])
async def get_all_matches(
    status: str = "All", # Filter by "Upcoming", "Live", "Completed"
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Fetches the list of matches for the Home screen.
    Calculates participant count and prize pool for each match.
    """
    # Create a subquery to count participants for each match
    participants_subquery = (
        select(Prediction.match_id, func.count(Prediction.id).label("count"))
        .group_by(Prediction.match_id)
        .subquery()
    )

    # Main query to get matches, joining the count subquery
    query = (
        select(Match, participants_subquery.c.count)
        .outerjoin(participants_subquery, Match.id == participants_subquery.c.match_id)
        .order_by(Match.start_time.asc())
    )
    
    if status != "All":
        query = query.where(Match.status == status.lower())
    
    result = await db.execute(query)
    matches_data = result.all()

    # Format the response
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


# --- Prediction Screen Endpoint ---

@router.post("/join")
async def join_contest(
    prediction_in: PredictionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Handles the 'Predict Now' button action"""
    match = await db.get(Match, prediction_in.match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if match.status != MatchStatus.UPCOMING:
        raise HTTPException(status_code=400, detail="Prediction locked. Match is not upcoming.")

    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    if not wallet or wallet.balance < match.entry_fee:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    existing = await db.scalar(select(Prediction).where(
        Prediction.user_id == user.id, 
        Prediction.match_id == match.id
    ))
    if existing:
        raise HTTPException(status_code=400, detail="You have already joined this contest")

    wallet.balance -= match.entry_fee
    db.add(wallet)

    prediction = Prediction(
        user_id=user.id,
        match_id=match.id,
        predicted_winner=prediction_in.predicted_winner,
        predicted_score_a=prediction_in.predicted_score_a,
        predicted_score_b=prediction_in.predicted_score_b,
        status="PENDING"
    )
    db.add(prediction)

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


# --- Leaderboard Screen Endpoint ---

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