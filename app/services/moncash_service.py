import httpx
import base64
from app.core.config import settings
import asyncio

async def get_moncash_auth_token() -> str:
    """Authenticates with MonCash and returns a Bearer token."""
    auth_url = f"{settings.MONCASH_API_BASE_URL}/Api/oauth/token"
    credentials = f"{settings.MONCASH_CLIENT_ID}:{settings.MONCASH_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {encoded_credentials}"
    }
    body = {"scope": "read,write", "grant_type": "client_credentials"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(auth_url, headers=headers, data=body, timeout=30.0)
            response.raise_for_status() 
            return response.json().get("access_token")
    except Exception as e:
        print(f"❌ MonCash Auth Error: {str(e)}")
        raise

async def create_moncash_payment(order_id: str, amount: float) -> dict:
    """
    REAL FUNCTION: Requests a payment token from MonCash.
    """
    payment_url = f"{settings.MONCASH_API_BASE_URL}/Api/v1/CreatePayment"
    auth_token = await get_moncash_auth_token()
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    payload = {"amount": amount, "orderId": order_id}

    try:
        async with httpx.AsyncClient() as client:
            # 60.0 timeout just in case
            response = await client.post(payment_url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            
            token = data.get("payment_token", {}).get("token")
            redirect_url = f"https://sandbox.moncashbutton.digicelgroup.com/Moncash-middleware/Checkout/Payment?token={token}"
            
            print(f"✅ Successfully created real MonCash payment link: {redirect_url}")
            return {
                "token": token,
                "redirect_url": redirect_url
            }
    except Exception as e:
        print(f"❌ MonCash Create Payment Error: {str(e)}")
        raise

async def execute_moncash_payout(receiver_phone: str, amount: float, description: str) -> dict:
    """
    WITHDRAWAL: Sends money directly to the user's MonCash account.
    """
    payout_url = f"{settings.MONCASH_API_BASE_URL}/Api/v1/Transfert"
    auth_token = await get_moncash_auth_token()
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    payload = {"amount": amount, "receiver": receiver_phone, "desc": description}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(payout_url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"❌ MonCash Payout Error: {str(e)}")
        raise