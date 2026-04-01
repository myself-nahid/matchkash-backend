"""
matches.py
----------
Home screen & prediction endpoints.

Key design decisions
--------------------
* Status is computed in **real-time** from `match_time_start` + sport duration.
  We sync the DB column at the top of every list call so the stored value stays
  fresh (cron-free approach). Terminal states (completed / cancelled) set by
  the admin are never overwritten.
* Tab filters work off the **live computed logic** so upcoming/live/completed
  always reflect wall-clock time, not stale DB values.
* All datetime comparisons use UTC to be globally consistent.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional
from decimal import Decimal

from app.api.deps import get_db, get_current_user
from app.models.match import Match, Prediction, MatchStatus
from app.models.user import Wallet, User
from app.models.transaction import Transaction
from sqlalchemy.orm import joinedload
from app.schemas.match import (
    PredictionCreate,
    MatchResponse,
    MyPredictionResponse,
    LeagueListResponse,
    LeaderboardResponse,
    LeaderboardEntry,
)
from app.services.match_status_service import (
    compute_match_status,
    sync_match_statuses,
    get_live_duration_minutes,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# HOME SCREEN ENDPOINTS
# ---------------------------------------------------------------------------

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
    user: User = Depends(get_current_user),
):
    """
    Home Screen Main API.
    Handles tabs: All | Upcoming | Live | Latest | Completed
    Supports sport filter, league filter, date picker, pagination.

    Tab semantics (real-time, clock-based):
      - All       → every match
      - Upcoming  → match hasn't started yet   (start > now)
      - Live      → currently in progress      (start ≤ now < start + duration)
      - Latest    → live + upcoming combined
      - Completed → admin-completed OR time has fully passed
    """

    # Sync DB statuses so stale upcoming→live→completed transitions are up-to-date
    await sync_match_statuses(db)

    now_utc = datetime.now(timezone.utc)

    # ── participants subquery ───────────────────────────────────────────────
    participants_subquery = (
        select(Prediction.match_id, func.count(Prediction.id).label("count"))
        .group_by(Prediction.match_id)
        .subquery()
    )

    # ── base query ──────────────────────────────────────────────────────────
    query = (
        select(Match, participants_subquery.c.count)
        .outerjoin(participants_subquery, Match.id == participants_subquery.c.match_id)
    )

    # ── optional filters ────────────────────────────────────────────────────
    if sport and sport.lower() != "all":
        query = query.where(Match.sport_name == sport)

    if league:
        query = query.where(Match.league_name == league)

    if match_date:
        query = query.where(func.date(Match.match_time_start) == match_date)

    # ── tab filter (real-time aware) ────────────────────────────────────────
    tab_lc = tab.lower()
    if tab_lc == "upcoming":
        # Matches that haven't kicked off yet (closest to starting first)
        query = query.where(Match.status == MatchStatus.UPCOMING).order_by(Match.match_time_start.asc())
    elif tab_lc == "live":
        query = query.where(Match.status == MatchStatus.LIVE).order_by(Match.id.desc())
    elif tab_lc == "latest":
        # Live + upcoming together (closest to starting first)
        query = query.where(
            Match.status.in_([MatchStatus.LIVE, MatchStatus.UPCOMING])
        ).order_by(Match.match_time_start.asc())
    elif tab_lc == "completed":
        query = query.where(Match.status == MatchStatus.COMPLETED).order_by(Match.id.desc())
    else:
        # "All" tab or fallback: newly created matches first
        query = query.order_by(Match.id.desc())

    # ── count query (mirrors filters) ───────────────────────────────────────
    count_query = select(func.count(Match.id))
    if sport and sport.lower() != "all":
        count_query = count_query.where(Match.sport_name == sport)
    if league:
        count_query = count_query.where(Match.league_name == league)
    if match_date:
        count_query = count_query.where(func.date(Match.match_time_start) == match_date)

    if tab_lc == "upcoming":
        count_query = count_query.where(Match.status == MatchStatus.UPCOMING)
    elif tab_lc == "live":
        count_query = count_query.where(Match.status == MatchStatus.LIVE)
    elif tab_lc == "latest":
        count_query = count_query.where(
            Match.status.in_([MatchStatus.LIVE, MatchStatus.UPCOMING])
        )
    elif tab_lc == "completed":
        count_query = count_query.where(Match.status == MatchStatus.COMPLETED)

    total_records = await db.scalar(count_query)
    total_pages = (total_records + page_size - 1) // page_size if total_records else 0

    # ── pagination ──────────────────────────────────────────────────────────
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    matches_data = result.all()

    # ── format response ─────────────────────────────────────────────────────
    response_list = []
    for match, count in matches_data:
        participants_count = count or 0
        gross_pool = Decimal(match.entry_fee) * participants_count
        fee_amount = gross_pool * (Decimal(match.platform_fee_percent) / 100)
        prize_pool = gross_pool - fee_amount

        # Expose the live-computed status to clients (already synced above)
        computed_status = compute_match_status(match, now_utc)

        match_dict = {k: v for k, v in match.__dict__.items() if k not in ("_sa_instance_state", "status")}

        match_response = MatchResponse(
            **match_dict,
            participants_count=participants_count,
            prize_pool=round(prize_pool, 2),
            status=computed_status,          # always send real-time status
        )
        response_list.append(match_response)

    return {
        "page": page,
        "page_size": page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "data": response_list,
    }


# ---------------------------------------------------------------------------
# PREDICTION ENDPOINTS (JOIN & HISTORY)
# ---------------------------------------------------------------------------

@router.post("/join")
async def join_contest(
    prediction_in: PredictionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """'Predict Now' Button Logic – only allowed while status == upcoming"""
    match = await db.get(Match, prediction_in.match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Real-time status check
    now_utc = datetime.now(timezone.utc)
    live_status = compute_match_status(match, now_utc)
    if live_status != "upcoming":
        raise HTTPException(status_code=400, detail="Prediction locked. Match has started or already ended.")

    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    if not wallet or wallet.balance < match.entry_fee:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    existing = await db.scalar(
        select(Prediction).where(
            Prediction.user_id == user.id,
            Prediction.match_id == match.id,
        )
    )
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
        status="PENDING",
    )
    db.add(prediction)

    # Log Transaction
    tx = Transaction(
        user_id=user.id,
        amount=-match.entry_fee,
        type="Entry Fee",
        status="Completed",
        reference=f"Match: {match.id}",
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
    user: User = Depends(get_current_user),
):
    """
    'All Predictions' Screen API.
    Tabs: All | Latest (Pending) | Won | Lose
    """
    query = (
        select(Prediction)
        .options(joinedload(Prediction.match))
        .where(Prediction.user_id == user.id)
        .order_by(Prediction.created_at.desc())
    )

    filter_lc = filter.lower()
    if filter_lc == "won":
        query = query.where(Prediction.status == "WON")
    elif filter_lc in ("lose", "lost"):
        query = query.where(Prediction.status == "LOST")
    elif filter_lc == "latest":
        query = query.where(Prediction.status == "PENDING")

    count_query = select(func.count(Prediction.id)).where(Prediction.user_id == user.id)
    if filter_lc == "won":
        count_query = count_query.where(Prediction.status == "WON")
    elif filter_lc in ("lose", "lost"):
        count_query = count_query.where(Prediction.status == "LOST")
    elif filter_lc == "latest":
        count_query = count_query.where(Prediction.status == "PENDING")

    total_records = await db.scalar(count_query)
    total_pages = (total_records + page_size - 1) // page_size if total_records else 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    predictions = result.scalars().all()

    response = []
    for p in predictions:
        response.append(
            MyPredictionResponse(
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
                prize_amount=p.prize_amount,
            )
        )

    return {
        "page": page,
        "page_size": page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "data": response,
    }


@router.get("/{match_id}", response_model=MatchResponse)
async def get_match_detail(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get single match details by ID with real-time computed status"""
    participants_subquery = (
        select(Prediction.match_id, func.count(Prediction.id).label("count"))
        .where(Prediction.match_id == match_id)
        .group_by(Prediction.match_id)
        .subquery()
    )

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

    gross_pool = Decimal(match.entry_fee) * participants_count
    fee_amount = gross_pool * (Decimal(match.platform_fee_percent) / 100)
    prize_pool = gross_pool - fee_amount

    now_utc = datetime.now(timezone.utc)
    computed_status = compute_match_status(match, now_utc)

    match_dict = {k: v for k, v in match.__dict__.items() if k not in ("_sa_instance_state", "status")}

    return MatchResponse(
        **match_dict,
        participants_count=participants_count,
        prize_pool=round(prize_pool, 2),
        status=computed_status,
    )


# ---------------------------------------------------------------------------
# Leaderboard Screen Endpoint
# ---------------------------------------------------------------------------

@router.get("/{match_id}/leaderboard", response_model=dict)
async def get_match_leaderboard(
    match_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetches the detailed leaderboard for a specific match, paginated."""
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    total_records = await db.scalar(
        select(func.count(Prediction.id)).where(Prediction.match_id == match_id)
    )
    total_pages = (total_records + page_size - 1) // page_size if total_records else 0

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

    leaderboard_entries = []
    for p in predictions:
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
            status=p.status,
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
            leaderboard=leaderboard_entries,
        ),
    }