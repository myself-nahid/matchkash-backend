from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db
from app.models.transaction import Transaction
from app.models.user import Wallet, Notification

router = APIRouter()

@router.post("/moncash")
async def webhook_moncash(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Listens for incoming webhook notifications from MonCash.
    This is where we confirm a deposit and credit the user's wallet.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    print(f"Received MonCash Webhook: {data}")

    # --- SECURITY (IMPORTANT) ---
    # In a real application, you would verify a signature from MonCash here
    # to ensure the request is not from a hacker.
    # For example:
    # signature = request.headers.get("moncash-signature")
    # if not verify_moncash_signature(signature, data):
    #     raise HTTPException(status_code=403, detail="Invalid signature")
    
    # 1. Extract crucial information from the webhook payload
    # NOTE: The exact keys ('transactionId', 'payment_token', etc.) will depend on
    # the REAL MonCash API documentation. These are placeholders.
    
    # This should be the internal ID you sent, e.g., "MATCHKASH-TX-123"
    internal_transaction_id = data.get("payment_token") 
    moncash_status = data.get("status") # e.g., "SUCCESS" or "FAILED"
    
    if not internal_transaction_id or not moncash_status:
        raise HTTPException(status_code=400, detail="Missing required fields in webhook payload")

    # 2. Find the original "Pending" transaction in your database
    transaction = await db.scalar(
        select(Transaction).where(Transaction.reference == internal_transaction_id)
    )

    if not transaction:
        # MonCash sent a notification for a transaction we don't recognize.
        # Log this for investigation, but don't crash.
        print(f"Warning: Received webhook for unknown transaction ID: {internal_transaction_id}")
        return {"status": "error", "message": "Transaction not found"}

    # 3. If transaction is already completed, do nothing to prevent double-crediting
    if transaction.status == "Completed":
        return {"status": "ok", "message": "Transaction already processed"}

    # 4. Process based on status
    if moncash_status.upper() == "SUCCESS":
        # Find the user's wallet
        wallet = await db.scalar(select(Wallet).where(Wallet.user_id == transaction.user_id))
        if wallet:
            # Update transaction and credit the user
            transaction.status = "Completed"
            wallet.balance += abs(transaction.amount)
            wallet.total_deposited += abs(transaction.amount)
            db.add(wallet)

            # Notify user of successful deposit
            notification = Notification(
                user_id=transaction.user_id,
                title="Deposit Successful",
                message=f"Your deposit of {abs(transaction.amount)} HTG was successful.",
                type="DEPOSIT_COMPLETED"
            )
            db.add(notification)

    else: # FAILED, CANCELLED, etc.
        transaction.status = "Failed"

    db.add(transaction)
    await db.commit()

    return {"status": "ok", "message": "Webhook processed"}