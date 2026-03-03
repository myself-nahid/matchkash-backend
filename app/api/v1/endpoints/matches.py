from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.api.deps import get_db, get_current_user
from app.models.match import Match, Prediction, MatchStatus
from app.models.user import Wallet, User
from app.models.transaction import Transaction
from app.schemas.match import PredictionCreate
from sqlalchemy import select, update

router = APIRouter()

@router.post("/join")
async def join_contest(
    prediction_in: PredictionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 1. Fetch Match
    match = await db.get(Match, prediction_in.match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # 2. Server-Side Locking Logic
    if datetime.utcnow() >= match.start_time or match.status != MatchStatus.UPCOMING:
        raise HTTPException(status_code=400, detail="Prediction locked. Match has started.")

    # 3. Check Wallet Balance
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    if wallet.balance < match.entry_fee:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    # 4. Check if already joined
    existing = await db.scalar(select(Prediction).where(
        Prediction.user_id == user.id, 
        Prediction.match_id == match.id
    ))
    if existing:
        raise HTTPException(status_code=400, detail="You have already joined this contest")

    # 5. Process Entry Fee (Atomic)
    wallet.balance -= match.entry_fee
    db.add(wallet)

    # 6. Create Prediction
    prediction = Prediction(
        user_id=user.id,
        match_id=match.id,
        predicted_winner=prediction_in.predicted_winner,
        predicted_score_a=prediction_in.predicted_score_a,
        predicted_score_b=prediction_in.predicted_score_b,
        status="PENDING"
    )
    db.add(prediction)

    # 7. Log Transaction
    tx = Transaction(
        user_id=user.id,
        amount=-match.entry_fee,
        type="ENTRY_FEE",
        status="COMPLETED",
        reference=f"Match: {match.id}"
    )
    db.add(tx)

    await db.commit()
    return {"message": "Contest joined successfully"}