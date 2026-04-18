import re

def normalize_phone_number(phone: str) -> str:
    """
    Strips all non-digit characters from a phone number.
    
    Examples:
    - "+1 (917) 526-5373" -> "19175265373"
    - "9175265373" -> "9175265373"
    - "+509 44 48 6683" -> "50944486683"
    """
    if not phone:
        return ""
    return re.sub(r'\D', '', phone)

def find_user_by_unformatted_phone(session, unformatted_phone: str):
    """
    A helper to find a user by a phone number that might not have a country code.
    It checks for an exact match first, then checks if the number exists with any country code.
    """
    normalized_phone = normalize_phone_number(unformatted_phone)

    # This will be replaced by a direct DB query later
    # For now, this placeholder logic illustrates the goal.
    # The actual implementation will be in the endpoint.
    pass # Placeholder