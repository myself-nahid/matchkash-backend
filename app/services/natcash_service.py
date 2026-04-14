import httpx
import time
import uuid
import hashlib
import hmac
from typing import Optional
from app.core.config import settings

class NatCashMerchantPayment:
    def __init__(self, signature_key: str, base_url: str):
        self.signature_key = signature_key
        # Ensure base URL doesn't have a trailing slash
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def generate_signature(partner_code: str, username: str, password: str,
                         request_id: str, order_number: str, amount: str,
                         access_key: str, timestamp: int, signature_key: str) -> str:
        # Exact string concatenation from NatCash SDK
        data = f"{access_key}{partner_code}{username}{password}{timestamp}{request_id}{order_number}{amount}"
        return hmac.new(
            signature_key.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def generate_access_key(input_str: str, trans_id: str) -> str:
        # Exact access key generation from NatCash SDK
        return hashlib.sha256((input_str + trans_id).encode('utf-8')).hexdigest()

    async def get_merchant_url(self, 
                        msisdn: str,
                        amount: str,
                        order_number: str,
                        partner_code: str,
                        username: str,
                        password: str,
                        callback_url: str) -> dict:
        
        request_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)  # Current timestamp in milliseconds
        
        access_key = self.generate_access_key(self.signature_key, request_id)

        signature = self.generate_signature(
            partner_code=partner_code,
            username=username,
            password=password,
            request_id=request_id,
            order_number=order_number,
            amount=amount,
            access_key=access_key,
            timestamp=timestamp,
            signature_key=self.signature_key
        )

        payload = {
            "requestId": request_id,
            "username": username,
            "password": password,
            "partnerCode": partner_code,
            "msisdn": msisdn,
            "amount": float(amount),  # Send as number in JSON
            "callbackUrl": callback_url,
            "timestamp": timestamp,
            "signature": signature,
            "orderNumber": order_number,
            "skipPhoneInput": True,
            "language": "en",
            "enableFee": False
        }

        # Make the async HTTP request to NatCash
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/online-payment/credential",
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                response_data = response.json()

                if str(response_data.get("code")) == "MSG_SUCCESS" or str(response_data.get("status")) == "0":
                    print(f"✅ Successfully created NatCash deposit link.")
                    return {"redirect_url": response_data["url"]}
                else:
                    # Capture exact NatCash error for debugging
                    error_msg = f"NatCash API Error: {response_data}"
                    print(f"❌ {error_msg}")
                    raise Exception(error_msg)

        except Exception as e:
            print(f"❌ NatCash Request Failed: {str(e)}")
            raise

# ==========================================
# Wrapper functions for your API endpoints
# ==========================================

async def create_natcash_payment(order_id: str, amount: float, phone_number: str) -> dict:
    """
    DEPOSIT: Uses the official NatCash class to generate the payment URL.
    """
    # Format amount as string without trailing decimals (e.g., "100" instead of "100.0")
    amount_str = str(int(amount)) if amount.is_integer() else str(amount)
    
    natcash_client = NatCashMerchantPayment(
        signature_key=settings.NATCASH_PRIVATE_KEY,
        base_url=settings.NATCASH_API_BASE_URL
    )
    
    return await natcash_client.get_merchant_url(
        msisdn=phone_number,
        amount=amount_str,
        order_number=order_id,
        partner_code=settings.NATCASH_PARTNER_CODE,
        username=settings.NATCASH_USERNAME,
        password=settings.NATCASH_PASSWORD,
        callback_url=settings.NATCASH_CALLBACK_URL
    )

async def execute_natcash_payout(receiver_phone: str, amount: float, description: str) -> dict:
    """
    WITHDRAWAL: (Pending Documentation from Client)
    """
    raise NotImplementedError("NatCash Payout API documentation has not been provided yet.")