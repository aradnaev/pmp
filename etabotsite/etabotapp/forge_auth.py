"""
Forge Invocation Token (FIT) validation utilities.

This module provides utilities to validate Forge Invocation Tokens (FIT)
as required by Atlassian Forge Remote API security requirements.

Reference: https://developer.atlassian.com/platform/forge/remote/essentials/#verifying-remote-requests
"""
import logging
import jwt
import requests
from typing import Optional, Dict, Any
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger('django')

# JWKS endpoint for Forge
FORGE_JWKS_URL = 'https://forge.cdn.prod.atlassian-dev.net/.well-known/jwks.json'
FORGE_ISSUER = 'forge/invocation-token'

# Cache for JWKS keys (to avoid fetching on every request)
_jwks_cache = None
_jwks_cache_time = None
JWKS_CACHE_TTL = 3600  # Cache for 1 hour


def get_jwks() -> Dict[str, Any]:
    """
    Fetch JWKS from Forge CDN with caching.
    
    Returns:
        Dictionary containing JWKS keys
    """
    global _jwks_cache, _jwks_cache_time
    import time
    
    current_time = time.time()
    
    # Return cached JWKS if still valid
    if _jwks_cache is not None and _jwks_cache_time is not None:
        if current_time - _jwks_cache_time < JWKS_CACHE_TTL:
            logger.debug('Using cached JWKS')
            return _jwks_cache
    
    # Fetch fresh JWKS
    try:
        logger.debug(f'Fetching JWKS from {FORGE_JWKS_URL}')
        response = requests.get(FORGE_JWKS_URL, timeout=10)
        response.raise_for_status()
        jwks = response.json()
        _jwks_cache = jwks
        _jwks_cache_time = current_time
        logger.info('Successfully fetched and cached JWKS')
        return jwks
    except requests.RequestException as e:
        logger.error(f'Failed to fetch JWKS: {e}')
        # If we have a cached version, use it even if expired
        if _jwks_cache is not None:
            logger.warning('Using expired JWKS cache due to fetch failure')
            return _jwks_cache
        raise AuthenticationFailed('Unable to verify authentication token: JWKS unavailable')


def get_public_key_from_jwks(jwks: Dict[str, Any], kid: str) -> Optional[Any]:
    """
    Extract the public key from JWKS for a given key ID.
    
    Args:
        jwks: JWKS dictionary
        kid: Key ID from JWT header
        
    Returns:
        Public key object or None if not found
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        import base64
        
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                # Extract RSA components
                n = base64.urlsafe_b64decode(key['n'] + '==')
                e = base64.urlsafe_b64decode(key['e'] + '==')
                
                # Convert to integers
                n_int = int.from_bytes(n, 'big')
                e_int = int.from_bytes(e, 'big')
                
                # Create RSA public key
                public_key = rsa.RSAPublicNumbers(e_int, n_int).public_key(default_backend())
                
                return public_key
    except Exception as e:
        logger.error(f'Error extracting public key from JWKS: {e}')
        return None
    
    logger.warning(f'Key ID {kid} not found in JWKS')
    return None


def validate_forge_invocation_token(invocation_token: str, app_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate a Forge Invocation Token (FIT) against JWKS.
    
    Args:
        invocation_token: The JWT token from Authorization header
        app_id: Expected audience (Application ID). If None, reads from settings.
        
    Returns:
        Decoded JWT payload if valid
        
    Raises:
        AuthenticationFailed: If token validation fails
    """
    if not invocation_token:
        raise AuthenticationFailed('No authentication token provided')
    
    # Get app_id from settings if not provided
    if app_id is None:
        app_id = getattr(settings, 'FORGE_APP_ID', None)
        if not app_id:
            logger.warning('FORGE_APP_ID not configured in settings. Token validation may fail.')
    
    try:
        # Decode JWT header to get key ID (kid)
        unverified_header = jwt.get_unverified_header(invocation_token)
        kid = unverified_header.get('kid')
        
        if not kid:
            raise AuthenticationFailed('Token missing key ID (kid) in header')
        
        # Get JWKS
        jwks = get_jwks()
        
        # Get public key for this kid
        public_key = get_public_key_from_jwks(jwks, kid)
        
        if not public_key:
            raise AuthenticationFailed(f'Unable to find public key for key ID: {kid}')
        
        # Verify and decode the token
        try:
            payload = jwt.decode(
                invocation_token,
                public_key,
                algorithms=['RS256'],
                audience=app_id,
                issuer=FORGE_ISSUER,
                options={
                    'verify_signature': True,
                    'verify_exp': True,
                    'verify_nbf': True,
                    'verify_aud': True,
                    'verify_iss': True,
                }
            )
            logger.debug('FIT token validated successfully')
            return payload
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidAudienceError:
            raise AuthenticationFailed(f'Token audience does not match expected app ID: {app_id}')
        except jwt.InvalidIssuerError:
            raise AuthenticationFailed(f'Token issuer does not match expected issuer: {FORGE_ISSUER}')
        except jwt.InvalidSignatureError:
            raise AuthenticationFailed('Token signature is invalid')
        except jwt.DecodeError as e:
            raise AuthenticationFailed(f'Token decode error: {str(e)}')
            
    except AuthenticationFailed:
        raise
    except Exception as e:
        logger.error(f'Unexpected error during FIT validation: {e}')
        raise AuthenticationFailed(f'Token validation failed: {str(e)}')


def extract_fit_token_from_request(request) -> Optional[str]:
    """
    Extract Forge Invocation Token from request Authorization header.
    
    Args:
        request: Django request object
        
    Returns:
        Token string or None if not found
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    
    if not auth_header:
        return None
    
    # Support both "Bearer <token>" and just "<token>" formats
    if auth_header.startswith('Bearer '):
        return auth_header[7:].strip()
    else:
        return auth_header.strip()

