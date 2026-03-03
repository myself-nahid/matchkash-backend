from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_admin_user
from app.schemas.match import MatchCreate, MatchUpdate
from app.models.match import Match, MatchStatus
from app.services.contest_engine import ContestEngine

router = APIRouter()

@router.post("/matches")
async def create_match(
    match_in: MatchCreate, 
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin_user)
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
    admin = Depends(get_current_admin_user)
):
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
        
    match.score_a = score_a
    match.score_b = score_b
    match.status = MatchStatus.COMPLETED
    
    db.add(match)
    await db.commit()

    # Trigger Engine in Background
    engine = ContestEngine()
    background_tasks.add_task(engine.process_match_results, db, match_id)
    
    return {"message": "Result updated, prize calculation queued."}