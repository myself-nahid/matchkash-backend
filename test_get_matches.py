import asyncio
from app.db.session import AsyncSessionLocal
from app.api.v1.endpoints.matches import get_matches
from app.models.user import User

async def run():
    async with AsyncSessionLocal() as db:
        user = User(id=1, phone="01725039612", role="admin")
        try:
            res = await get_matches(tab="All", sport=None, league=None, match_date=None, page=1, page_size=10, db=db, user=user)
            print(res)
        except Exception as e:
            import traceback
            traceback.print_exc()

asyncio.run(run())
