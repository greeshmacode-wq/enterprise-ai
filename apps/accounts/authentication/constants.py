"""
Authentication constants used across the accounts module.
"""
class SessionKeys:
    """
    Session key names used to store authentication data.
    """
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"
    USER_UUID = "user_uuid"
    USERNAME = "username"
    LOGIN_TYPE = "login_type"
    USER_ROLE = "user_role"

class TokenClaims:
    """
    Custom JWT claims.
    """
    USER_UUID = "uuid"
    USERNAME = "username"
    EMAIL = "email"
    ROLE = "role"
    DEPARTMENT = "department"
    DESIGNATION = "designation"