"""
Forge Invocation Token (FIT) validation utility.

Validates JWT tokens from Atlassian Forge Remote requests according to:
https://developer.atlassian.com/platform/forge/remote/essentials/#verifying-remote-requests
"""

import logging
from typing import Optional, Dict, Any, Tuple
from jose import jwt, jwk
from jose.constants import ALGORITHMS
import requests
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger('django')

# JWKS endpoint for Forge tokens
FORGE_JWKS_URL = 'https://forge.cdn.prod.atlassian-dev.net/.well-known/jwks.json'

# Expected issuer for Forge Invocation Tokens
FORGE_ISSUER = 'forge/invocation-token'


class ForgeTokenValidationError(Exception):
    """Exception raised when FIT validation fails."""
    pass


def get_forge_app_id() -> Optional[str]:
    """
    Get the Forge application ID from Django settings.
    
    Returns:
        The Forge application ID, or None if not configured.
    """
    return getattr(settings, 'FORGE_APP_ID', None)


def get_jwks() -> Dict[str, Any]:
    """
    Fetch and return the JWKS (JSON Web Key Set) from Forge.
    
    Returns:
        Dictionary containing the JWKS.
        
    Raises:
        ForgeTokenValidationError: If JWKS cannot be fetched.
    """
    try:
        response = requests.get(FORGE_JWKS_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f'Failed to fetch JWKS from {FORGE_JWKS_URL}: {str(e)}')
        raise ForgeTokenValidationError(f'Failed to fetch JWKS: {str(e)}')


def validate_forge_invocation_token(
    invocation_token: str,
    app_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate a Forge Invocation Token (FIT) JWT.
    
    The token is a JWT that, when decoded, contains a JSON object with:
    - app: Information about the app and installation
    - context: Context about the invocation (for frontend calls)
    - principal: User identifier (for UI modules)
    - aud: Audience (should match FORGE_APP_ID)
    - iss: Issuer (should be "forge/invocation-token")
    - iat, nbf, exp: Timestamp claims
    - jti: JWT ID
    
    Args:
        invocation_token: The JWT token string from the Authorization header.
        app_id: The expected Forge application ID (audience). If None, will be
                retrieved from Django settings.
    
    Returns:
        Dictionary containing the decoded and validated token payload (the JSON object
        with app, context, jti, etc. as shown in the Forge documentation).
        
    Raises:
        ForgeTokenValidationError: If validation fails for any reason.
    """
    if not invocation_token:
        raise ForgeTokenValidationError('Invocation token is missing')
    
    # Get app_id from settings if not provided
    if app_id is None:
        app_id = get_forge_app_id()
        if not app_id:
            raise ForgeTokenValidationError(
                'FORGE_APP_ID not configured in Django settings'
            )
    
    try:
        # Fetch JWKS
        jwks = get_jwks()
        
        # Get the unverified header to find the key ID
        unverified_header = jwt.get_unverified_header(invocation_token)
        kid = unverified_header.get('kid')
        
        if not kid:
            raise ForgeTokenValidationError('Token header missing key ID (kid)')
        
        # Find the key in JWKS
        key = None
        for jwk_key in jwks.get('keys', []):
            if jwk_key.get('kid') == kid:
                key = jwk_key
                break
        
        if not key:
            raise ForgeTokenValidationError(
                f'Key with kid={kid} not found in JWKS'
            )
        
        # Construct the public key from JWK
        public_key = jwk.construct(key)
        
        # Verify and decode the token
        payload = jwt.decode(
            invocation_token,
            public_key,
            algorithms=[ALGORITHMS.RS256],
            audience=app_id,
            issuer=FORGE_ISSUER,
            options={
                'verify_signature': True,
                'verify_aud': True,
                'verify_iss': True,
                'verify_exp': True,
                'verify_nbf': True,
            }
        )
        logger.info(f'Payload: {payload}')
        logger.debug(f'Successfully validated FIT for app_id={app_id}')
        return payload
        
    except jwt.ExpiredSignatureError:
        raise ForgeTokenValidationError('Token has expired')
    except jwt.JWTClaimsError as e:
        raise ForgeTokenValidationError(f'Token claims validation failed: {str(e)}')
    except jwt.JWTError as e:
        raise ForgeTokenValidationError(f'Token validation failed: {str(e)}')
    except Exception as e:
        logger.error(f'Unexpected error during FIT validation: {str(e)}')
        raise ForgeTokenValidationError(f'Token validation error: {str(e)}')


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """
    Extract the JWT token string from the Authorization Bearer header.
    
    The Forge Invocation Token is sent as a JWT in the Authorization header:
    Authorization: Bearer <JWT_TOKEN_STRING>
    
    This function extracts the JWT token string. The actual JSON payload
    (with app, context, jti, etc.) is obtained by decoding the JWT in
    validate_forge_invocation_token().
    
    Args:
        authorization_header: The value of the Authorization header (e.g., "Bearer eyJ...")
    
    Returns:
        The JWT token string if found, None otherwise.
    """
    if not authorization_header:
        return None

    # Check if it's a Bearer token
    if authorization_header.startswith('Bearer '):
        return authorization_header[7:].strip()
    
    return None


def validate_forge_request(request) -> Dict[str, Any]:
    """
    Validate a Django REST Framework request containing a Forge Invocation Token.
    
    This function extracts the token from the Authorization header and validates it.
    
    Args:
        request: Django REST Framework request object.
    
    Returns:
        Dictionary containing the validated token payload.
        
    Raises:
        ForgeTokenValidationError: If validation fails.
    """
    # Extract Authorization header
    auth_header = request.META.get('HTTP_AUTHORIZATION') or request.META.get('Authorization')
    
    if not auth_header:
        raise ForgeTokenValidationError(
            'Missing Authorization header'
        )
    
    # Extract bearer token
    token = extract_bearer_token(auth_header)
    
    if not token:
        raise ForgeTokenValidationError(
            'Authorization header must be a Bearer token'
        )
    
    # Validate the token
    return validate_forge_invocation_token(token)


class ForgeInvocationTokenAuthentication(BaseAuthentication):
    """
    Django REST Framework authentication class for Forge Invocation Tokens.
    
    Validates JWT tokens from Atlassian Forge Remote requests and attaches
    the decoded payload to the request object.
    
    Usage in views:
        class MyView(APIView):
            authentication_classes = [ForgeInvocationTokenAuthentication]
            permission_classes = []
            
            def post(self, request):
                # Access the token payload
                app_id = request.forge_token_payload.get('app', {}).get('id')
                installation_id = request.forge_token_payload.get('app', {}).get('installationId')
                ...
    """
    
    def authenticate(self, request) -> Optional[Tuple[None, Dict[str, Any]]]:
        """
        Authenticate the request using Forge Invocation Token.
        
        Args:
            request: Django REST Framework request object.
        
        Returns:
            Tuple of (user, token_payload) if authentication succeeds.
            None if no token is provided (allows other auth methods).
            
        Raises:
            AuthenticationFailed: If token is provided but validation fails.
        """
        # Extract Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION') or request.META.get('Authorization')
        
        # If no Authorization header, return None to allow other auth methods
        if not auth_header:
            return None
        
        # Extract bearer token
        token = extract_bearer_token(auth_header)
        
        if not token:
            # If Authorization header exists but is not Bearer, raise error
            raise AuthenticationFailed(
                'Authorization header must be a Bearer token'
            )
        
        try:
            # Validate the token
            payload = validate_forge_invocation_token(token)
            
            # Attach payload to request for easy access in views
            request.forge_token_payload = payload
            
            # Return (user, token_payload) tuple
            # user is None since Forge tokens don't map to Django users
            return (None, payload)
            
        except ForgeTokenValidationError as e:
            logger.warning(f'FIT validation failed: {str(e)}')
            raise AuthenticationFailed(
                f'Forge Invocation Token validation failed: {str(e)}'
            )
    
    def authenticate_header(self, request) -> str:
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response.
        """
        return 'Bearer'


def forge_token_required(view_func):
    """
    Decorator to require and validate Forge Invocation Token for a view.
    
    Usage:
        @forge_token_required
        def my_view(request):
            # Token is validated, request.forge_token_payload contains the payload
            ...
    """
    def wrapper(request, *args, **kwargs):
        try:
            payload = validate_forge_request(request)
            # Attach payload to request for use in view
            request.forge_token_payload = payload
            return view_func(request, *args, **kwargs)
        except ForgeTokenValidationError as e:
            logger.warning(f'FIT validation failed: {str(e)}')
            return Response(
                {
                    'error': 'Authentication failed',
                    'message': str(e)
                },
                status=status.HTTP_401_UNAUTHORIZED
            )
    
    return wrapper

