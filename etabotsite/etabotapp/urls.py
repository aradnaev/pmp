from django.urls import include, path
from django.urls import re_path
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
# from rest_framework_expiring_authtoken import views
from .views import (
    UserViewSet, ProjectViewSet, TMSViewSet, EstimateTMSView,
    CeleryTaskStatusView, CriticalPathsView, CriticalPathsViewJIRAplugin)
from .views import UserCommunicationView
from .views import ParseTMSprojects
from .views import index
from .views import activate
from .views import email_verification
from .views import AtlassianOAuthCallback
from .views import AtlassianOAuth
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
import logging

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='users')
router.register(r'projects', ProjectViewSet, basename='projects')
router.register(r'tms', TMSViewSet, basename='tms')

urlpatterns = staticfiles_urlpatterns() # this should be empty list when not in DEBUG mode by design
logging.debug('static urlpatterns: "{}"'.format(urlpatterns))

urlpatterns += [
    path('api/', include(router.urls)),
    re_path(r'^api/auth/',
        include('rest_framework.urls', namespace='rest_framework')),
    re_path(r'^api/get-token/', obtain_auth_token),
    re_path(r'^api/estimate/', EstimateTMSView.as_view(), name="estimate_tms"),
    re_path(r'^api/job-status/(?P<id>.+)/$',
        CeleryTaskStatusView.as_view(), name="job_status"),
    re_path(r'^api/parse_projects/', ParseTMSprojects.as_view(), name="estimate_tms"),
    re_path(r'^api/atlassian_oauth', AtlassianOAuth.as_view(), name='atlassian_oauth'),
    re_path(r'^api/user_communication/', UserCommunicationView.as_view(), name="user_communication"),
    re_path(r'^api/critical_paths_plugin', CriticalPathsViewJIRAplugin.as_view(), name="critical_paths_plugin"),
    re_path(r'^api/critical_paths', CriticalPathsView.as_view(), name="critical_paths"),
    re_path(r'^api/verification/activate/', activate, name='activate'),
    re_path(r'^api/verification/send-email/', email_verification, name='email_verification'),

    re_path(r'^api/activate/(?P<token>[0-9A-Za-z|=]+)/?',
        activate, name='activate'),
    # password reset
    re_path(r'^account/password_reset/$',
        auth_views.PasswordResetView.as_view(),
        {'post_reset_redirect': '/account/password_reset/done/'},
        name="password_reset"),
    # password reset done
    re_path(r'^account/password_reset/done/$',
        auth_views.PasswordResetDoneView.as_view(),
        name='password_reset_done'),
    # password reset confirm
    re_path(r'^account/password_reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.PasswordResetConfirmView.as_view(),
        {'post_reset_redirect': '/account/password_reset/complete/'},
        name="password_reset_confirm"),
    re_path(r'^account/password_reset/complete/$',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete'),
    
    re_path(r'^atlassian_callback', AtlassianOAuthCallback.as_view(), name='atlassian_callback'),
    # catch-all pattern for compatibility with the Angular routes
    re_path(r'^(?P<path>.*)$', index),
    re_path(r'^$', index)
]
