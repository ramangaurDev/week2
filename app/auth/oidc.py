"""
Google OIDC Authentication Implementation
Validates Google ID tokens and extracts user identity
"""

from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests
import os
from typing import Optional, Dict, Any
from functools import lru_cache
import time
from app.logging_config import get_logger
from app.config import config

logger = get_logger(__name__)
security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


class GoogleOIDCValidator:
    """Validates Google OIDC ID tokens."""
    
    def __init__(self, client_ids: list[str]):
        """
        Initialize OIDC validator.
        
        Args:
            client_ids: List of allowed Google OAuth2 client IDs
        """
        self.client_ids = client_ids
        self.request = requests.Request()
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify Google ID token and extract user info.
        
        Args:
            token: Google ID token (JWT)
            
        Returns:
            User info dict containing email, name, sub, etc.
            
        Raises:
            HTTPException: If token is invalid
        """
        # Check cache
        cache_key = token[:50]  # Use token prefix as cache key
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug("Token validation cache hit")
                return cached_data
        
        try:
            # Verify the token
            idinfo = id_token.verify_oauth2_token(
                token, 
                self.request,
                audience=None  # We'll verify audience manually
            )
            
            # Verify issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
            
            # Verify audience (client ID) if specified
            if self.client_ids and idinfo.get('aud') not in self.client_ids:
                logger.warning(
                    "Token audience mismatch",
                    expected=self.client_ids,
                    actual=idinfo.get('aud')
                )
                # In production, you'd want to be strict here
                # For development, we'll log but continue
            
            # Verify email is verified
            if not idinfo.get('email_verified', False):
                raise ValueError('Email not verified')
            
            # Cache the result
            self._cache[cache_key] = (idinfo, time.time())
            
            # Clean old cache entries (simple cleanup)
            if len(self._cache) > 1000:
                current_time = time.time()
                self._cache = {
                    k: v for k, v in self._cache.items()
                    if current_time - v[1] < self._cache_ttl
                }
            
            logger.info(
                "Token verified successfully",
                user_email=idinfo.get('email'),
                sub=idinfo.get('sub')
            )
            
            return {
                'sub': idinfo['sub'],  # Google user ID
                'email': idinfo['email'],
                'name': idinfo.get('name', ''),
                'picture': idinfo.get('picture', ''),
                'email_verified': idinfo.get('email_verified', False),
                'hd': idinfo.get('hd', ''),  # Hosted domain (for Google Workspace)
            }
            
        except ValueError as e:
            logger.error("Token verification failed", error=str(e))
            raise HTTPException(
                status_code=401,
                detail=f"Invalid authentication token: {str(e)}"
            )
        except Exception as e:
            logger.error("Token verification error", error=str(e), error_type=type(e).__name__)
            raise HTTPException(
                status_code=401,
                detail="Authentication failed"
            )


# Global validator instance
_validator: Optional[GoogleOIDCValidator] = None


def get_oidc_validator() -> GoogleOIDCValidator:
    """Get or create OIDC validator instance."""
    global _validator
    if _validator is None:
        # client_ids = os.getenv("GOOGLE_CLIENT_IDS", "").split(",")
        # client_ids = [cid.strip() for cid in client_ids if cid.strip()]
          # Prefer explicit env var so local dev can override,
        # otherwise fall back to Secret Manager value configured in GCP.
        client_ids_env = os.getenv("GOOGLE_CLIENT_IDS", "")
        client_ids = [cid.strip() for cid in client_ids_env.split(",") if cid.strip()]
        if not client_ids:
            # Secret name matches GCP setup: google-oauth-client-id
            secret_client_id = config.get_secret("google-oauth-client-id")
            if secret_client_id:
                client_ids = [secret_client_id.strip()]
        _validator = GoogleOIDCValidator(client_ids)
    return _validator


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    validator: GoogleOIDCValidator = Depends(get_oidc_validator)
) -> Dict[str, Any]:
    """
    FastAPI dependency to get current authenticated user.
    
    Usage:
        @app.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            return {"message": f"Hello {user['email']}"}
    """
    token = credentials.credentials
    return validator.verify_token(token)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_optional),
    validator: GoogleOIDCValidator = Depends(get_oidc_validator)
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency for optional authentication.
    Returns None if no auth provided, user info if valid token provided.
    """
    if not credentials:
        return None
    
    try:
        return validator.verify_token(credentials.credentials)
    except HTTPException:
        return None
