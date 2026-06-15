import jwt
from fastapi import Header, HTTPException, status
from typing import Dict, Any

# Shared Secret Key from Spring Boot application (JwtService.java)
SECRET_KEY = "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM0987654321"

def get_current_user(Token: str = Header(..., alias="Token")) -> Dict[str, Any]:
    """
    Dependency to validate JWT from HTTP 'Token' header.
    Returns:
        dict: {"username": email, "role": role_id}
    """
    try:
        # Decode using the shared key and HMAC SHA-256 (HS256)
        payload = jwt.decode(Token, SECRET_KEY, algorithms=["HS256", "HS384", "HS512"])
        username = payload.get("username")
        role = payload.get("role")
        
        if not username or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is invalid. Required fields 'username' and 'role' are missing."
            )
            
        return {"username": username, "role": int(role)}
        
    except jwt.ExpiredSignatureError as e:
        print(f"JWT Verification: Token has expired - {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again."
        )
    except jwt.InvalidTokenError as e:
        print(f"JWT Verification: Invalid token error - {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}"
        )
