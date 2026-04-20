
import asyncio
from sqlalchemy import text
from app.db.session import engine

async def fix_database():
    print("Checking database schema...")
    async with engine.begin() as conn:
        try:
            # Check if winning_team column exists
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='matches' AND column_name='winning_team'"
            ))
            if not result.fetchone():
                print("Adding missing 'winning_team' column to 'matches' table...")
                await conn.execute(text("ALTER TABLE matches ADD COLUMN winning_team VARCHAR(255)"))
                print("Column 'winning_team' added successfully.")
            else:
                print("Column 'winning_team' already exists.")
                
        except Exception as e:
            print(f"Error updating database: {e}")

if __name__ == "__main__":
    asyncio.run(fix_database())
