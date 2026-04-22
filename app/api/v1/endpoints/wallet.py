from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.api.deps import get_db, get_current_user
from app.models.user import User, Wallet
from app.models.transaction import Transaction
from app.schemas.wallet import WalletResponse, TransactionResponse, DepositRequest, WithdrawRequest
from app.models.user import Notification
from decimal import Decimal
import uuid
from app.services.moncash_service import create_moncash_payment
from app.services.natcash_service import create_natcash_payment

router = APIRouter()

@router.get("/me", response_model=WalletResponse)
async def get_my_wallet(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current balance, total won, and total deposited"""
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet

@router.get("/transactions", response_model=List[TransactionResponse])
async def get_my_transactions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get history for the Wallet screen"""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
    )
    return result.scalars().all()

# @router.post("/deposit")
# async def request_deposit(
#     request: DepositRequest,
#     user: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     Mock Deposit: Instantly adds money for testing.
#     Later, this will connect to MonCash/NatCash Webhooks.
#     """
#     if request.amount <= 0:
#         raise HTTPException(status_code=400, detail="Amount must be greater than zero")

#     wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    
#     # 1. Add money to wallet
#     wallet.balance += request.amount
#     wallet.total_deposited += request.amount

#     # 2. Record Transaction
#     tx = Transaction(
#         user_id=user.id,
#         amount=request.amount,
#         type="Deposit",
#         status="Completed",
#         reference=f"{request.method} - {request.phone_number}"
#     )
    
#     db.add(wallet)
#     db.add(tx)
#     await db.commit()
    
#     return {"message": "Deposit successful", "new_balance": wallet.balance}

# @router.post("/withdraw")
# async def request_withdrawal(
#     request: WithdrawRequest,
#     user: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db)
# ):
#     """Submit a withdrawal request (Goes to Pending status)"""
#     if request.amount <= 0:
#         raise HTTPException(status_code=400, detail="Amount must be greater than zero")

#     wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    
#     if wallet.balance < request.amount:
#         raise HTTPException(status_code=400, detail="Insufficient balance")

#     # 1. Deduct immediately to prevent user from spending it while pending
#     wallet.balance -= request.amount
    
#     # 2. Record Transaction as 'Pending'
#     tx = Transaction(
#         user_id=user.id,
#         amount=-request.amount, # Negative because it's a deduction
#         type="Withdraw",
#         status="Pending",
#         reference=f"{request.method} - {request.phone_number}"
#     )
    
#     db.add(wallet)
#     db.add(tx)
#     await db.commit()
    
#     return {"message": "Withdrawal request submitted successfully. Waiting for admin approval."}

@router.post("/withdraw")
async def request_withdrawal(
    request: WithdrawRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit a withdrawal request and Notify Admins"""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user.id))
    
    if wallet.balance < request.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # 1. Deduct immediately
    wallet.balance -= request.amount
    
    # 2. Record Transaction
    tx = Transaction(
        user_id=user.id,
        amount=-request.amount,
        type="Withdraw",
        status="Pending",
        reference=f"{request.method} - {request.phone_number}" # Saves "Moncash - 1234"
    )
    
    db.add(wallet)
    db.add(tx)
    await db.flush() # Flush to generate the tx.id without committing yet

    # 3. Create a Notification for ALL Admins
    admins = await db.scalars(select(User).where(User.role == "admin"))
    for admin in admins:
        notification = Notification(
            user_id=admin.id,
            title="New withdrawal request",
            message=f"{user.full_name or 'A user'} wants to withdraw",
            type="WITHDRAWAL_REQUEST",
            reference_id=tx.id # Links the notification to this exact transaction!
        )
        db.add(notification)

    await db.commit()
    
    return {"message": "Withdrawal request submitted successfully. Waiting for admin approval."}

@router.post("/deposit")
async def request_deposit(
    request: DepositRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    order_id = f"DEP-{user.id}-{uuid.uuid4().hex[:8]}"

    tx = Transaction(
        user_id=user.id,
        amount=request.amount,
        type="Deposit",
        status="Pending",
        reference=order_id 
    )
    db.add(tx)
    await db.commit()

    # --- MONCASH ---
    if request.method.lower() == "moncash":
        try:
            payment_data = await create_moncash_payment(order_id=order_id, amount=float(request.amount))
            
            redirect_url = payment_data.get("redirect_url")
            
            if not redirect_url:
                raise Exception("MonCash did not return a valid redirect URL.")

            # 👇 FIX: Return an auto-submitting HTML form to handle the 405 error
            html_content = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Redirecting to MonCash...</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                </head>
                <body onload="document.forms[0].submit()" style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <form action="{redirect_url}" method="post">
                        <p>Redirecting you to MonCash to complete your payment...</p>
                        <p>If you are not redirected automatically, please click the button below.</p>
                        <input type="submit" value="Proceed to MonCash" style="padding: 10px 20px; font-size: 16px;">
                    </form>
                </body>
            </html>
            """
            return HTMLResponse(content=html_content)

        except Exception as e:
            tx.status = "Failed"
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to initialize MonCash payment: {str(e)}")
            
    # --- NATCASH ---
    elif request.method.lower() == "natcash":
        try:
            payment_data = await create_natcash_payment(
                order_id=order_id, 
                amount=float(request.amount), 
                phone_number=request.phone_number
            )
            # NatCash returns a URL that the frontend should open
            return {
                "status": "success",
                "message": "Please complete the payment in the browser.",
                "payment_url": payment_data["redirect_url"]
            }
        except Exception as e:
            tx.status = "Failed"
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to initialize NatCash payment: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Unsupported payment method.")