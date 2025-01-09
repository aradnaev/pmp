from django.conf.urls import url, include
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
    url(r'^api/', include(router.urls)),
    url(r'^api/auth/',
        include('rest_framework.urls', namespace='rest_framework')),
    url(r'^api/get-token/', obtain_auth_token),
    url(r'^api/estimate/', EstimateTMSView.as_view(), name="estimate_tms"),
    url(r'^api/job-status/(?P<id>.+)/$',
        CeleryTaskStatusView.as_view(), name="job_status"),
    url(r'^api/parse_projects/', ParseTMSprojects.as_view(), name="estimate_tms"),
    url(r'^api/atlassian_oauth', AtlassianOAuth.as_view(), name='atlassian_oauth'),
    url(r'^api/user_communication/', UserCommunicationView.as_view(), name="user_communication"),
    url(r'^api/critical_paths_plugin', CriticalPathsViewJIRAplugin.as_view(), name="critical_paths_plugin"),
    url(r'^api/critical_paths', CriticalPathsView.as_view(), name="critical_paths"),
    url(r'^api/verification/activate/', activate, name='activate'),
    url(r'^api/verification/send-email/', email_verification, name='email_verification'),

    url(r'^api/activate/(?P<token>[0-9A-Za-z|=]+)/?',
        activate, name='activate'),
    # password reset
    url(r'^account/password_reset/$',
        auth_views.PasswordResetView.as_view(),
        {'post_reset_redirect': '/account/password_reset/done/'},
        name="password_reset"),
    # password reset done
    url(r'^account/password_reset/done/$',
        auth_views.PasswordResetDoneView.as_view(),
        name='password_reset_done'),
    # password reset confirm
    url(r'^account/password_reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.PasswordResetConfirmView.as_view(),
        {'post_reset_redirect': '/account/password_reset/complete/'},
        name="password_reset_confirm"),
    url(r'^account/password_reset/complete/$',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete'),
    
    url(r'^atlassian_callback', AtlassianOAuthCallback.as_view(), name='atlassian_callback'),
    # catch-all pattern for compatibility with the Angular routes
    url(r'^(?P<path>.*)$', index),
    url(r'^$', index)
]
