"""
match_status_service.py
-----------------------
Handles real-time, timezone-aware match status computation and automatic DB sync.

Status lifecycle (like real Football/Basketball):
  upcoming  -> match hasn't started yet          (now < match_time_start)
  live      -> match is in progress              (match_time_start <= now < match_time_start + duration)
  completed -> match is over                     (now >= match_time_start + duration)  OR  manually set by admin
  cancelled -> cancelled by admin

Sport durations (minutes after kick-off until match considered "over"):
  Football   = 105 min  (90 min + 15 min stoppage/extra)
  Basketball = 50  min  (~48 min regulation + buffer)
  Cricket    = 480 min  (8 hours typical ODI buffer)
  default    = 120 min
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.match import Match, MatchStatus

# ---------------------------------------------------------------------------
# Sport-specific live window (minutes)
# ---------------------------------------------------------------------------
SPORT_LIVE_DURATION: dict[str, int] = {
    "football":   105,
    "basketball":  50,
    "cricket":    480,
    "tennis":     180,
    "baseball":   200,
}
DEFAULT_LIVE_DURATION = 120  # 2 hours for unknown sports


def get_live_duration_minutes(sport_name: str) -> int:
    """Return live window in minutes for a given sport."""
    return SPORT_LIVE_DURATION.get(sport_name.lower(), DEFAULT_LIVE_DURATION)


def compute_match_status(match: Match, now_utc: datetime) -> str:
    """
    Compute the real-time status of a match based on current UTC time.
    Never trusts Match.status for upcoming/live transitions — only admin-set
    'completed' or 'cancelled' are respected regardless of time.

    Returns: 'upcoming' | 'live' | 'completed' | 'cancelled'
    """
    # Admin-set terminal states are always respected
    if match.status in (MatchStatus.CANCELLED, MatchStatus.COMPLETED):
        return match.status.value if hasattr(match.status, 'value') else str(match.status)

    start: datetime = match.match_time_start
    # Ensure start is timezone-aware (treat naive as UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    duration = get_live_duration_minutes(match.sport_name or "")
    end_time = start + timedelta(minutes=duration)

    if now_utc < start:
        return "upcoming"
    elif start <= now_utc < end_time:
        return "live"
    else:
        return "completed"


async def sync_match_statuses(db: AsyncSession) -> None:
    """
    Background-safe: fetch all non-terminal matches and update their DB status
    based on real-time computation. Call this on each request or as a cron.
    Only updates matches whose computed status differs from their stored status.
    """
    now_utc = datetime.now(timezone.utc)

    # Only look at matches that are not already completed/cancelled
    result = await db.execute(
        select(Match).where(
            Match.status.notin_([MatchStatus.COMPLETED, MatchStatus.CANCELLED])
        )
    )
    matches = result.scalars().all()

    for match in matches:
        new_status_str = compute_match_status(match, now_utc)
        new_status = MatchStatus(new_status_str)
        current_status = match.status if isinstance(match.status, MatchStatus) else MatchStatus(match.status)
        
        if new_status != current_status:
            match.status = new_status
            db.add(match)

    await db.commit()
