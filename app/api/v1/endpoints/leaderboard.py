from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from typing import List, Optional, Dict
from decimal import Decimal

# Dependency, Model, and Schema Imports
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.match import Match, Prediction
from app.schemas.match import LeaderboardMatchInfo, DetailedLeaderboardResponse, SimpleLeaderboardEntry


router = APIRouter()


@router.get("/matches", response_model=Dict)
async def get_leaderboard_match_list(
    status: str = "All", # All, Upcoming, Latest, Completed
    league: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetches the list of matches for the main leaderboard screen (first screenshot).
    Supports pagination.
    """
    # 1. Subquery to count participants
    participants_subquery = (
        select(Prediction.match_id, func.count(Prediction.id).label("count"))
        .group_by(Prediction.match_id)
        .subquery()
    )

    # 2. Main query to get matches
    query = (
        select(Match, participants_subquery.c.count)
        .outerjoin(participants_subquery, Match.id == participants_subquery.c.match_id)
    )

    # 3. Apply Filters
    if status.lower() == "upcoming":
        query = query.where(Match.status == "upcoming")
    elif status.lower() == "completed":
        query = query.where(Match.status == "completed")
    elif status.lower() == "latest": # Latest can mean live or recently completed
        query = query.where(Match.status.in_(["live", "completed"]))
    
    if league:
        query = query.where(Match.league_name == league)
        
    query = query.order_by(Match.match_time_start.desc())

    # 4. Count total records before pagination
    count_query = select(func.count(Match.id))
    if status.lower() == "upcoming":
        count_query = count_query.where(Match.status == "upcoming")
    elif status.lower() == "completed":
        count_query = count_query.where(Match.status == "completed")
    elif status.lower() == "latest":
        count_query = count_query.where(Match.status.in_(["live", "completed"]))
    if league:
        count_query = count_query.where(Match.league_name == league)
    
    total_records = await db.scalar(count_query)
    total_pages = (total_records + page_size - 1) // page_size

    # 5. Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
        
    result = await db.execute(query)
    matches_data = result.all()

    # 6. Format response
    response_list = []
    for match, count in matches_data:
        participants_count = count or 0
        gross_pool = Decimal(match.entry_fee) * participants_count
        fee_amount = gross_pool * (Decimal(match.platform_fee_percent) / 100)
        prize_pool = gross_pool - fee_amount
        
        response_list.append(LeaderboardMatchInfo(
            match_id=match.id,
            league_name=match.league_name,
            team_a=match.team_a,
            team_b=match.team_b,
            start_time=match.match_time_start,
            score_a=match.score_a,
            score_b=match.score_b,
            prize_pool=round(prize_pool, 2),
            participants_count=participants_count,
            status=match.status
        ))
        
    return {
        "page": page,
        "page_size": page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "data": response_list
    }


@router.get("/matches/{match_id}", response_model=DetailedLeaderboardResponse)
async def get_detailed_leaderboard(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetches the detailed, ranked leaderboard for a single match (second screenshot).
    """
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Get all predictions for this match, sorted by rank
    predictions_query = (
        select(Prediction)
        .options(joinedload(Prediction.user))
        .where(Prediction.match_id == match_id)
        .order_by(Prediction.rank.asc().nulls_last(), Prediction.created_at.asc()) # Show ranked users first
    )
    result = await db.execute(predictions_query)
    predictions = result.scalars().unique().all()
    
    total_participants = len(predictions)
    my_rank = None
    
    leaderboard_entries = []
    for p in predictions:
        if p.user_id == current_user.id:
            my_rank = p.rank
            
        leaderboard_entries.append(SimpleLeaderboardEntry(
            rank=p.rank,
            player_name=p.user.full_name or f"Player {p.user_id:04d}",
            status="Won" if p.status == "WON" else "" # UI only shows "Won"
        ))

    # Format the "Your Position" text
    my_position_text = f"#{my_rank} of {total_participants}" if my_rank else f"Unranked of {total_participants}"
    if match.status == "upcoming":
        my_position_text = f"0 of {total_participants}"


    return DetailedLeaderboardResponse(
        team_a=match.team_a,
        team_b=match.team_b,
        image_url=match.image_url,
        my_position_text=my_position_text,
        total_participants=total_participants,
        leaderboard=leaderboard_entries
    )