from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.match import Match, MatchStatus, Prediction
from app.models.user import Wallet
from app.models.transaction import Transaction
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class ContestEngine:
    
    @staticmethod
    def calculate_score_diff(pred_a, pred_b, actual_a, actual_b):
        """
        Formula from Screenshot:
        (|Predicted A - Actual A| + |Predicted B - Actual B|)
        Smallest total difference gives the best rank.
        """
        diff = abs(pred_a - actual_a) + abs(pred_b - actual_b)
        return diff

    async def process_match_results(self, db: AsyncSession, match_id: int):
        # 1. Get Match Data
        result = await db.execute(select(Match).where(Match.id == match_id))
        match = result.scalars().first()
        
        if not match or match.status != MatchStatus.COMPLETED:
            raise ValueError("Match not completed or not found")

        # 2. Get All Predictions for this match
        result = await db.execute(select(Prediction).where(Prediction.match_id == match_id))
        predictions = result.scalars().all()

        if not predictions:
            return

        # 3. Calculate Rankings
        scored_predictions = []
        for p in predictions:
            # Check if predicted winner is correct (Prerequisite for high rank)
            actual_winner = "A" if match.score_a > match.score_b else "B"
            if match.score_a == match.score_b: actual_winner = "Draw"
            
            is_winner_correct = p.predicted_winner == actual_winner
            
            # Calculate Difference Score
            diff_score = self.calculate_score_diff(
                p.predicted_score_a, p.predicted_score_b,
                match.score_a, match.score_b
            )
            
            # Custom sorting tuple: (Correct Winner? (0=True, 1=False), Difference Score)
            # We want Correct Winner first, then lowest Difference.
            sort_key = (0 if is_winner_correct else 1, diff_score)
            
            scored_predictions.append({
                "prediction": p,
                "sort_key": sort_key
            })

        # Sort: Primary key is Correct Winner, Secondary is Lowest Diff
        scored_predictions.sort(key=lambda x: x["sort_key"])

        # 4. Calculate Prize Pool
        total_participants = len(predictions)
        gross_pool = Decimal(match.entry_fee) * total_participants
        platform_fee = gross_pool * (Decimal(match.platform_fee_percent) / 100)
        net_prize_pool = gross_pool - platform_fee

        # 5. Distribute Prizes (Example: Top 5 Logic)
        # 1st: 50%, 2nd: 25%, 3rd: 10%, 4th: 10%, 5th: 5% (Adjustable)
        distribution_ratios = [0.50, 0.25, 0.10, 0.10, 0.05]
        
        for index, item in enumerate(scored_predictions):
            pred = item["prediction"]
            rank = index + 1
            pred.rank = rank
            
            prize = Decimal(0)
            if index < len(distribution_ratios):
                prize = net_prize_pool * Decimal(distribution_ratios[index])
                pred.status = "WON"
                pred.prize_amount = prize
                
                # Credit Wallet
                await self.credit_winner(db, pred.user_id, prize, match_id)
            else:
                pred.status = "LOST"
                pred.prize_amount = 0

            db.add(pred)

        await db.commit()

    async def credit_winner(self, db: AsyncSession, user_id: int, amount: Decimal, match_id: int):
        # Atomic Update
        await db.execute(
            update(Wallet)
            .where(Wallet.user_id == user_id)
            .values(
                balance=Wallet.balance + amount,
                total_won=Wallet.total_won + amount
            )
        )
        
        # Log Transaction
        tx = Transaction(
            user_id=user_id,
            amount=amount,
            type="WINNING_PAYOUT",
            status="COMPLETED",
            reference=f"Match Result: {match_id}"
        )
        db.add(tx)