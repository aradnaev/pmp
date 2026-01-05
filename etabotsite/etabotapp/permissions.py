import logging
from rest_framework import permissions
from rest_framework.exceptions import AuthenticationFailed
from .models import Project
from .models import TMS
from django.contrib.auth.models import User
from .forge_auth import validate_forge_invocation_token, extract_fit_token_from_request

logger = logging.getLogger('django')


class IsOwner(permissions.BasePermission):
    """Custom permission class to allow only bucketlist owners to edit them."""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # permissions are only allowed to the owner of the snippet.
        return obj.owner == request.user


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Custom permission class to allow only bucketlist owners to edit them."""

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the snippet.
        return obj.owner == request.user


class AnonCreateAndUpdateOwnerOnly(permissions.BasePermission):
    """
    Custom permission:
        - allow anonymous POST
        - allow authenticated GET and PUT on *own* record
        - allow all actions for staff
    """

    def has_permission(self, request, view):
        return view.action == 'create' or \
               request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return view.action in ['retrieve', 'update', 'partial_update',
                               'destroy'] and obj.id == request.user.id or \
               request.user.is_staff or obj.owner == request.user


class ListAdminOnly(permissions.BasePermission):
    """
    Custom permission to only allow access to lists for admins
    """

    def has_permission(self, request, view):
        return view.action != 'list' or request.user and request.user.is_staff


class ForgeInvocationTokenPermission(permissions.BasePermission):
    """
    Permission class to validate Forge Invocation Token (FIT) from Authorization header.
    
    This validates that requests contain a valid FIT token as required by
    Atlassian Forge Remote API security requirements.
    
    Reference: https://developer.atlassian.com/platform/forge/remote/essentials/#verifying-remote-requests
    """
    
    def has_permission(self, request, view):
        """
        Validate FIT token from Authorization header.
        
        Returns:
            True if token is valid, raises AuthenticationFailed otherwise
        """
        # Extract token from request
        invocation_token = extract_fit_token_from_request(request)
        
        if not invocation_token:
            # Log available headers for debugging
            auth_headers = {
                'HTTP_AUTHORIZATION': request.META.get('HTTP_AUTHORIZATION', 'NOT_FOUND'),
                'Authorization': request.META.get('Authorization', 'NOT_FOUND'),
            }
            logger.warning(f'No FIT token found. Available auth headers: {auth_headers}, request {request}')
            raise AuthenticationFailed(
                'Missing Forge Invocation Token. '
                'Please provide a valid token in the Authorization header as: "Authorization: Bearer <token>".'
            )
        
        # Validate the token
        try:
            payload = validate_forge_invocation_token(invocation_token)
            # Store validated payload in request for potential use in views
            request.forge_token_payload = payload
            logger.debug('FIT token validated successfully')
            return True
        except AuthenticationFailed:
            raise
        except Exception as e:
            logger.error(f'Unexpected error during FIT validation in permission class: {e}', exc_info=True)
            raise AuthenticationFailed(f'Token validation error: {str(e)}')
