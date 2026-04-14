from fastapi import APIRouter, HTTPException, Request, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db
from app.models.transaction import Transaction
from app.models.user import Wallet, Notification
import hashlib
import hmac
from app.core.config import settings

router = APIRouter()

@router.post("/moncash")
async def webhook_moncash(request: Request, db: AsyncSession = Depends(get_db)):
    """MonCash Alert URL: Called when a deposit is successful."""
    # MonCash sends data as form-data in Webhooks, not JSON!
    form_data = await request.form()
    
    # MonCash typically sends 'transaction_id' and 'orderId' (Check your PDF for exact keys)
    order_id = form_data.get("orderId") 
    
    print(f"🔔 Received MonCash Webhook for Order: {order_id}")

    if not order_id:
        return {"status": "ignored"}

    # 1. Find the pending transaction
    transaction = await db.scalar(select(Transaction).where(Transaction.reference == order_id))
    
    if not transaction or transaction.status != "Pending":
        return {"status": "ignored"}

    # 2. Add the money to the user's wallet
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == transaction.user_id))
    
    if wallet:
        transaction.status = "Completed"
        wallet.balance += transaction.amount
        wallet.total_deposited += transaction.amount
        
        # 3. Notify the user
        notification = Notification(
            user_id=transaction.user_id,
            title="Deposit Successful!",
            message=f"Your deposit of {transaction.amount} HTG has been credited to your wallet.",
            type="DEPOSIT_COMPLETED"
        )
        
        db.add(wallet)
        db.add(transaction)
        db.add(notification)
        await db.commit()
        print(f"✅ Successfully credited {transaction.amount} HTG to User {transaction.user_id}")

    return {"status": "success"}

@router.get("/natcash") # Depending on NatCash, callbacks are often GET requests with query params. We will support both GET and POST to be safe.
@router.post("/natcash")
async def webhook_natcash(request: Request, db: AsyncSession = Depends(get_db)):
    """NatCash Callback URL: Triggered when user completes transaction"""
    
    # 1. Extract parameters (Could be JSON body or URL query params)
    if request.method == "POST":
        try:
            data = await request.json()
        except:
            data = dict(await request.form())
    else:
        data = dict(request.query_params)

    print(f"🔔 Received NatCash Webhook: {data}")

    code = str(data.get("code"))
    trans_id = data.get("transId")
    order_id = data.get("orderNumber")
    received_signature = data.get("signature")

    if not order_id or not received_signature:
        return {"status": "ignored", "message": "Missing parameters"}

    # 2. Verify Security Signature (PDF Page 6)
    # accessKey = SHA256(function_code + orderNumber)
    access_key_raw = f"{settings.NATCASH_FUNCTION_CODE}{order_id}"
    access_key = hashlib.sha256(access_key_raw.encode('utf-8')).hexdigest()

    # 2. signature = HMAC-SHA256(function_code, accessKey + orderNumber + code)
    sign_data = f"{access_key}{order_id}{code}"
    expected_signature = hmac.new(
        settings.NATCASH_FUNCTION_CODE.encode('utf-8'),
        sign_data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # 3. Check if they match
    if expected_signature != received_signature:
        print("❌ SECURITY ALERT: NatCash Webhook Signature Mismatch!")
        return {"status": "error", "message": "Invalid signature"}

    # 3. Find the transaction in DB
    transaction = await db.scalar(select(Transaction).where(Transaction.reference == order_id))
    if not transaction or transaction.status != "Pending":
        return {"status": "ignored"}

    # 4. Process Status (PDF Page 6 says: 1 = Success, -1 = Failed)
    if code == "1":
        wallet = await db.scalar(select(Wallet).where(Wallet.user_id == transaction.user_id))
        if wallet:
            transaction.status = "Completed"
            wallet.balance += transaction.amount
            wallet.total_deposited += transaction.amount
            
            notification = Notification(
                user_id=transaction.user_id,
                title="NatCash Deposit Successful!",
                message=f"Your deposit of {transaction.amount} HTG has been credited.",
                type="DEPOSIT_COMPLETED"
            )
            
            db.add(wallet)
            db.add(transaction)
            db.add(notification)
            await db.commit()
            print(f"✅ Successfully credited {transaction.amount} HTG via NatCash!")
    
    elif code == "-1":
        transaction.status = "Failed"
        db.add(transaction)
        await db.commit()
        print(f"❌ NatCash Deposit Failed by User.")

    # NatCash callback expects a success HTTP 200 response to stop retrying
    return {"status": "success"}