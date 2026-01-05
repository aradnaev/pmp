from django.shortcuts import render
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.shortcuts import redirect

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response

from .celery_tracking import send_celery_task_with_tracking
from etabotapp.TMSlib.JIRA_API import update_available_projects_for_TMS
from .serializers import UserSerializer, ProjectSerializer, TMSSerializer
from .models import OAuth1Token, OAuth2Token, OAuth2CodeRequest
from .models import atlassian_redirect_uri
from .models import TMS, Project
from .models import oauth
from .permissions import IsOwnerOrReadOnly, IsOwner
from etabotapp.TMSlib.JIRA_API import JIRA_wrapper
from .exceptions import TaskFailedError
import etabotapp.TMSlib.TMS as TMSlib
# import etabotapp.TMSlib.data_conversion as dc
from .user_activation import ActivationProcessor, ResponseCode
import etabotapp.email_toolbox as email_toolbox
# import threading
import json
# import mimetypes
import logging
import celery as clry
# import os

from django.conf import settings
import datetime
import pytz
import hashlib
import etabotapp.TMSlib.Atlassian_API as Atlassian_API
from .forge_token_validator import validate_forge_request, ForgeTokenValidationError


# import oauth_support

logger = logging.getLogger('django')

AUTHLIB_OAUTH_CLIENTS = getattr(settings, "AUTHLIB_OAUTH_CLIENTS", False)

LOCAL_MODE = getattr(settings, "LOCAL_MODE", False)
if LOCAL_MODE:
    logger.setLevel(logging.DEBUG)
    print('LOCAL_MODE views set logger to DEBUG.')
else:
    logger.setLevel(logging.INFO)
    print('not LOCAL_MODE views set logger to INFO.')

print('logger test')
logger.debug('views logger DEBUG level test')
logger.info('views logger INFO level test')
logger.warning('views logger WARNING level test')
logger.debug('views loggerDEBUG level test')
logger.info('views  loggerINFO level test')
logger.warning('views logger WARNING level test')
print('DEBUG INFO WARNING levels test done')

celery = clry.Celery()
celery.config_from_object('django.conf:settings')



@ensure_csrf_cookie
def index(request, path='', format=None):
    """
    Renders the Angular2 SPA
    """
    logger.debug('format = "{}"'.format(format))
    logger.debug('path = "{}"'.format(path))
    logger.debug('request = "{}"'.format(request))
    response = render(request, 'index.html')
    logger.debug('response: {}'.format(response))
    return response


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def activate(request):
    logger.debug('activate API started')
    post_data = json.loads(request.body)
    logger.debug('user activate post_data: "{}"'.format(post_data))
    code = ActivationProcessor.activate_user(post_data['token'])
    body = dict()
    status_code = 500

    if code == ResponseCode.DECRYPTION_ERROR:
        body['message'] = 'Token is invalid. Please contact ETAbot.'
        body['status'] = 1
    elif code == ResponseCode.EXPIRATION_ERROR:
        body['message'] = (
            'Account confirmation link has expired, we have sent a new '
            'activation link, please check your email!')
        body['status'] = 2
    elif code == ResponseCode.EXPIRATION_RESEND_ERROR:
        body['message'] = (
            'Account confirmation link has expired, activation email resend '
            'failed, please try register again!')
        body['status'] = 6
    elif code == ResponseCode.ALREADY_ACTIVATE_ERROR:
        body['message'] = 'You were already activated. Please login with your account!'
        body['status'] = 3
    elif code == ResponseCode.NOT_EXIST_ERROR:
        body['message'] = 'The user does not exist!'
        body['status'] = 4
    elif code == ResponseCode.SUCCESS:
        body['message'] = 'Thank you for your confirmation. Please login with your account!'
        body['status'] = 5
        status_code = 200

    return HttpResponse(json.dumps(body), content_type='application/json', status=status_code)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def email_verification(request):
    logger.debug('activate API started')
    post_data = json.loads(request.body)
    user = User.objects.get(pk=post_data['uid'])
    body = dict()

    try:
        ActivationProcessor.email_token(user)
        body['message'] = 'Successfully sent activation email to User {}'.format(user.username)
        return HttpResponse(json.dumps(body), content_type='application/json', status=200)
    except Exception as ex:
        logger.error('Failed to send activation email to User %s: %s' % (user.username, str(ex)))
        body['message'] = 'Failed to send activation email to User {}'.format(user.username)
        return HttpResponse(json.dumps(body), content_type='application/json', status=500)


class UserViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list` and `detail` actions.
    """
    serializer_class = UserSerializer
    permission_classes = (permissions.AllowAny(),)

    def get_queryset(self):
        if self.request.user.is_superuser:
            return User.objects.all()
        return User.objects.filter(owner=self.request.user)

    def get_permissions(self):
        # allow non-authenticated user to create via POST
        return (permissions.AllowAny() if self.request.method == 'POST'
                else IsOwnerOrReadOnly()),


class ProjectViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions.

    Additionally we also provide an extra `highlight` action.
    """
    serializer_class = ProjectSerializer
    permission_classes = (permissions.IsAuthenticated,
                          IsOwner,)

    def get_queryset(self):
        objects2return = Project.objects.filter(owner=self.request.user)
        logger.debug('ProjectViewSet get_queryset:{}'.format(objects2return))
        for o in objects2return:
            logger.debug('{}: project_tms_id="{}"'.format(
                o, o.project_tms_id))
        return objects2return

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class TMSViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions.
    """
    serializer_class = TMSSerializer
    permission_classes = (permissions.IsAuthenticated,
                          IsOwner,)

    def get_queryset(self):
        return TMS.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        res = serializer.save(owner=self.request.user)


class ParseTMSprojects(APIView):

    def get(self, request, format=None):
        logger.debug('request.query_params: "{}"'.format(
            request.query_params))
        response_message = ''
        celery_task_ids = []
        try:
            tms_set = get_tms_set_by_id(request)
        except Exception as e:
            response_message = 'Failed to parse tms id due to "{}"'.format(e)
            logger.error(response_message)
            return Response(
                response_message,
                status=status.HTTP_400_BAD_REQUEST)
        logger.debug('starting projects parsing for tms_set: {}'.format(
            tms_set))
        try:
            res_messages = []
            for tms in tms_set:
                parse_tms_kwargs = {}
                celery_task = send_celery_task_with_tracking(
                    'etabotapp.django_tasks.parse_projects_for_tms_id',
                    (tms.id, parse_tms_kwargs), owner=tms.owner)
                logger.info('celery task sent, celery id ={}'.format(celery_task))
                celery_task_ids.append(celery_task.task_id)
                res_messages.append('stared celery task id {} for tms id {}'.format(
                    celery_task.task_id, tms.id))
            response_message = '\n'.join(res_messages)
        except Exception as e:
            logger.debug('parse_projects_for_TMS failed due to {}'.format(e))
            if 'not connected to JIRA' in str(e):
                response_message = 'Issue with connecting to JIRA. \
Please update your login credentials.'
            else:
                response_message = 'unknown error. If the issue persists, \
please contact us at hello@etabot.ai.'
            logger.error(response_message)
            logger.error(e)
            return Response(
                response_message,
                status=status.HTTP_400_BAD_REQUEST)

        return Response(
            json.dumps({
                'result': response_message,
                'celery_task_ids': celery_task_ids}),
            status=status.HTTP_200_OK)


class AtlassianOAuth(APIView):
    def get(self, request):
        """Redirect to Atlassian for granting access to user data."""
        # logger.debug(vars(request))
        oauth_name = 'atlassian'

        jira_permissions = request.GET.get('permissions')
        logger.debug(jira_permissions)

        scope = AUTHLIB_OAUTH_CLIENTS.get(oauth_name, {}).get('client_kwargs', {}).get('scope')
        if jira_permissions == 'in ETAbot only':
            scope = scope.replace('write:jira-work ', '')

        timestamp = pytz.utc.localize(datetime.datetime.utcnow())
        state = hashlib.sha256(('{}{}'.format(request.user, timestamp)).encode('utf-8')).hexdigest()
        logger.debug('state={}'.format(state))
        logger.info('oauth.atlassian.authorize_redirect')
        resp = oauth.atlassian.authorize_redirect(
            request, atlassian_redirect_uri,
            state=state,
            scope=scope)
        logger.info('oauth.atlassian.authorize_redirect response received')
        logger.debug(resp)
        logger.debug(vars(resp))
        oa2cr = OAuth2CodeRequest(
            owner=request.user,
            name=oauth_name,
            timestamp=timestamp,
            state=state)
        oa2cr.save()
        logger.info('AtlassianOAuth GET finished')
        return Response(
            json.dumps({'redirect_url': resp.url}),
            status=status.HTTP_200_OK)


class AtlassianOAuthCallback(APIView):
    """API for Atlassian to callback after consent screen."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """Receive authorization code from JIRA OAuth."""
        """Provided as a query parameter called code. This code can be
        exchanged for an access token.

        TODO: setup framework for getting access token and storing it."""
        logger.info(request.GET)
        # logger.info(request.GET.get('code'))
        logger.debug(oauth.atlassian.__dict__)
        state = request.GET.get('state')
        logger.debug('state={}'.format(state))
        try:
            logger.info('getting token = oauth.atlassian.authorize_access_token(request)')
            token = oauth.atlassian.authorize_access_token(request)
            logger.info('got token')
            logger.debug('token={}'.format(token))
        except Exception as e:
            logger.error('cannot get token due to: "{}"'.format(e))
            return redirect('/error_page')
        if token.get('expires_in') is not None:
            try:
                token['expires_in'] = int(token['expires_in'])
            except Exception as e:
                token['expires_in'] = 3600 * 24 * 30
        else:
            token['expires_in'] = 3600 * 24 * 365

        users_set = OAuth2CodeRequest.objects.all().filter(
            state=state)

        if len(users_set) == 0:
            error_message = 'no user found with such auth code request. please try again.'
            logger.warning(error_message)
            return Response(
                error_message,
                status=status.HTTP_400_BAD_REQUEST)
        elif len(users_set) > 1:
            error_message = 'Auth code request collision. please try again.'
            logger.warning(error_message)
            return Response(
                error_message,
                status=status.HTTP_400_BAD_REQUEST)
        else:
            pass
        user = users_set[0].owner
        logger.debug('user: {}, username {}'.format(
            user, user.username))
        token_item = OAuth2Token(
            owner=user,
            name='atlassian',
            token_type=token['token_type'],
            access_token=token['access_token'],
            refresh_token=token['refresh_token'],
            expires_at=token['expires_at'])

        token_item.save()
        logger.debug('token saved: {}'.format(vars(token_item)))

        new_tms_ids = self.add_update_atlassian_tms(user, token_item)
        tms_ids_list_string = construct_new_tms_ids_query_params(new_tms_ids)
        return redirect('/tmss' + tms_ids_list_string)

    @staticmethod
    def add_update_atlassian_tms(owner, token_item):
        """Get all available systems for the token and pass to Django models.

        Return list of ids for newly created TMS Django models
        """
        atlassian = Atlassian_API.AtlassianAPI(token_item)
        resources = atlassian.get_accessible_resources()
        logger.debug(resources)
        new_tms_ids = []
        for resource in resources:
            try:
                TMSs = TMS.objects.all().filter(
                    endpoint=resource['url'],
                    owner=owner)
                logger.debug('found TMSs with endpoint {}: {}'.format(
                    resource['url'], TMSs))
                if len(TMSs) == 0:
                    logger.info('creating new TMS for {}'.format(resource['url']))
                    new_TMS = TMS(
                        owner=owner,
                        endpoint=resource['url'],
                        type='JI',
                        name=resource.get('name'),
                        params=resource,
                        oauth2_token=token_item)
                    logger.debug('created new_TMS {}'.format(new_TMS))
                    new_TMS.save()
                    new_tms_ids.append(new_TMS.id)
                    logger.debug('created new TMS {}'.format(new_TMS))
                else:
                    for existing_TMS in TMSs:
                        logger.debug('updating {}'.format(existing_TMS))
                        existing_TMS.params = resource
                        existing_TMS.endpoint = resource['url']
                        existing_TMS.name = resource.get('name')
                        existing_TMS.oauth2_token = token_item
                        existing_TMS.save()
                        logger.debug('updated {}'.format(existing_TMS))
            except Exception as e:
                logger.error('Cannot parse resource "{}" due to "{}"'.format(
                    resource, e
                ))

            logger.debug('add_update_atlassian_tms is done')

        return new_tms_ids


def construct_new_tms_ids_query_params(new_tms_ids):
    tms_ids_list_string = ''
    if len(new_tms_ids) > 0:
        tms_ids_list_string = '?' + '&'.join([
            'new_tms_ids={}'.format(tms_id) for tms_id in new_tms_ids])
    return tms_ids_list_string


def get_tms_set_by_id(request):
    """Return tms_set on success or request Response."""
    logger.debug('get_tms_set_by_id started for user {}'.format(request.user))
    tms_id = request.query_params.get('tms')

    tms_id = int(tms_id)
    logger.debug('int tms_id: "{}"'.format(tms_id))
    tms_set = TMS.objects.all().filter(
        owner=request.user,
        id=tms_id)
    if len(tms_set) == 0:
        raise NameError('No TMS found with tms_id={} for user {}'.format(
            tms_id, request.user))

    return tms_set


def get_projects_by_tms(user, tms_id):
    return [
        pj.id for pj in Project.objects.all().filter(
            owner=user,
            project_tms_id=tms_id)
    ]


def check_celery_worker_available():
    logger.debug('checking celery workers availability')
    # result = celery_app.control.ping(timeout=0.5)
    # logger.debug('checking celery workers availability: {}'.format(result))
    # if len(result) == 0:
    #     raise NameError('no celery workers available')


def estimate_tms(user, tms, global_params, project_id=None):
    if project_id:
        projects = [int(project_id)]
    else:
        projects = get_projects_by_tms(
            user, tms.id
        )
    logger.debug('projects: "{}"'.format(projects))
    check_celery_worker_available()
    # Want to use send task helper here instead
    result = send_celery_task_with_tracking(
        'etabotapp.django_tasks.estimate_ETA_for_TMS_project_set_ids',
        (tms.id, projects, global_params), owner=tms.owner)

    # todo: stores task_id in database for this user
    return result.task_id


class CriticalPathsView(APIView):

    def post(self, request):
        """Generate critical path for a given JQL and parameters.

        """
        try:
            tms_set = get_tms_set_by_id(request)
        except Exception as e:
            return Response(
                {
                    "error":
                        "No TMS found with tms_id=\"{}\" for user {} due "
                        "to: {}".format(
                            request.query_params.get('tms'),
                            self.request.user, e)
                },
                status=status.HTTP_400_BAD_REQUEST)
        post_data = {}
        tms = tms_set[0]
        if request.body:
            logger.debug('request.body: {}'.format(request.body))
            post_data = json.loads(request.body)
        params = post_data.get('params', {})
        logger.debug('CriticalPathView call global_params: {}'.format(params))
        if 'final_nodes' in params:
            final_nodes = params['final_nodes']
        else:
            return Response(
                {
                    "error": "No final_nodes in params."
                },
                status=status.HTTP_400_BAD_REQUEST)
        result = send_celery_task_with_tracking(
            'etabotapp.django_tasks.generate_critical_path',
            (tms.id, final_nodes, params), owner=tms.owner)

        return Response(
            data=result.task_id,
            status=status.HTTP_200_OK)


class CriticalPathsViewJIRAplugin(APIView):

    def post(self, request):
        """Generate critical path for a given JQL and explicit list of JIRA tasks rather than TMS data source.

        """
        # Validate Forge Invocation Token
        try:
            forge_token_payload = validate_forge_request(request)
            logger.debug(f'FIT validated for CriticalPathsViewJIRAplugin: app_id={forge_token_payload.get("app", {}).get("id")}')
        except ForgeTokenValidationError as e:
            logger.warning(f'FIT validation failed for CriticalPathsViewJIRAplugin: {str(e)}')
            return Response(
                {
                    "error": "Authentication failed",
                    "message": str(e)
                },
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        prep_celery_task_id = str(hashlib.sha256(request.body).hexdigest())

        logger.info(f'CriticalPathsViewJIRAplugin started prep_celery_task_id={prep_celery_task_id}.')
        try:
            params = {}
            post_data = {}
            if request.body:
                logger.debug('request.body: {}'.format(request.body))
                post_data = json.loads(request.body)
                params = post_data.get('params', {})
                logger.debug('CriticalPathView call global_params: {}'.format(params))
                params['slack_tolerance_for_crit_path_days'] = post_data.get('slack_tolerance_days', 0.)
            if 'final_nodes' in post_data:
                final_nodes = post_data['final_nodes']
                logger.debug(f'got final_nodes: {final_nodes}')
            else:
                error_message = "No final_nodes passed."
                logger.warning(error_message)
                return Response(
                    {
                        "error": error_message
                    },
                    status=status.HTTP_400_BAD_REQUEST)

            if 'start_date_field_name' not in post_data:
                error_message = "No start_date_field_name passed."
                logger.warning(error_message)
                return Response(
                    {
                        "error": error_message
                    },
                    status=status.HTTP_400_BAD_REQUEST)
            else:
                start_date_field_name = post_data['start_date_field_name']

            if 'issues' in post_data:
                issues_dict = post_data['issues']
            else:
                error_message = "No tasks aka issues passed."
                logger.warning(error_message)
                return Response(
                    {
                        "error": error_message
                    },
                    status=status.HTTP_400_BAD_REQUEST)

            eta_date_field_name = post_data.get('eta_date_field_name')
            celery_task_id = None
            task_path = 'etabotapp.django_tasks.generate_critical_path_jira'
            if start_date_field_name == 'trigger_prep_celery_task_error':
                raise NameError(f"Test error for prep celery task {prep_celery_task_id} triggered by "
                                f"start_date_field_name='{start_date_field_name}'.")
        except Exception as e:
            logger.warning("Celery task submission failed. task ID {}".format(prep_celery_task_id))
            logger.error(str(e))
            return Response(
                {
                    "error": f"Error code: {prep_celery_task_id}: "
                             f"An internal server error has occurred during preparation stage. ",
                    "error_id": prep_celery_task_id,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            result = send_celery_task_with_tracking(
                task_path,
                (issues_dict, start_date_field_name, eta_date_field_name, final_nodes, params),
                owner=self.request.user,
                compress=True)
            celery_task_id = result.task_id
            json_response = {'task_id': celery_task_id}
            
            return Response(
                data=json_response,
                status=status.HTTP_200_OK)

        except Exception as e:
            logger.warning("Celery task submission failed. task ID {}".format(celery_task_id))
            logger.error(str(e))
            return Response(
                {
                    "error": f"An internal server error has occurred during execution stage. "
                             f"Error code: {celery_task_id}",
                    "error_details": str(e),
                    "error_type": e.__class__.__name__,
                    "error_id": celery_task_id,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EstimateTMSView(APIView):

    def post(self, request, format=None):
        """Triggers ETA updates for a particular tms_id or all.

        TODO: implement params per project."""

        logger.debug('request.user: {}, username {}'.format(
            request.user, request.user.username))

        logger.debug('self.request.user: {}, self.username {}'.format(
            self.request.user, self.request.user.username))

        post_data = {}
        if request.body:
            logger.debug('request.body: {}'.format(request.body))
            post_data = json.loads(request.body)

        logger.debug('post_data: {}'.format(post_data))
        logger.debug('request.query_params: "{}"'.format(
            request.query_params))

        if request.query_params.get('tms') is None:
            # no tms id given, estimate for all TMS for this user
            tms_set = TMS.objects.all().filter(owner=self.request.user)
        else:
            try:
                tms_set = get_tms_set_by_id(request)
            except Exception as e:
                return Response(
                    {
                        "error":
                            "No TMS found with tms_id=\"{}\" for user {} due "
                            "to: {}".format(
                                request.query_params.get('tms'),
                                self.request.user, e)
                    },
                    status=status.HTTP_400_BAD_REQUEST)

        logger.debug('found tms: {}'.format(tms_set))
        if len(tms_set) == 0:
            return Response(
                'No TMS found for user {}'.format(self.request.user),
                status=status.HTTP_400_BAD_REQUEST)
        # here we need to call an estimate method that takes TMS object which
        # includes TMS credentials
        # threads = []
        global_params = post_data.get('params', {})
        logger.debug('estimate call global_params: {}'.format(global_params))

        tms_id_to_celery_task_id = {
            tms.id: estimate_tms(
                self.request.user, tms, global_params,
                request.query_params.get('project_id', None))
            for tms in tms_set
        }

        response_message = 'TMS account to estimate:{}. \
Number of tasks sent: {}'.format(tms_set, len(tms_id_to_celery_task_id))
        return Response(
            data=tms_id_to_celery_task_id,
            status=status.HTTP_200_OK)


class UserCommunicationView(APIView):
    """
    Communication with user via email.
     - 400: Missing subject and/or body
    """

    def post(self, request):
        logger.debug('User Communication View POST Started')
        error = False

        # Check for good data
        post_data = {}
        if request.body:
            logger.debug('Request.body: {}'.format(request.body))
            post_data = json.loads(request.body)
        else:
            logger.debug('No request body')
            error = True

        if post_data.get('subject') is None or post_data.get('body') is None:
            error = True

        # Return error, and send email if necessary
        if error:
            if post_data.get('send_confirmation'):
                logger.debug('Sending error email')
                subject = 'ETABot | Feedback Error'
                body = 'Thank you for taking the time to provide feedback.' \
                       '<br><br> Unfortunately there was an issue ' \
                       'sending your feedback, please try again. ' \
                       'If the issue persists let us know at hello@etabot.ai ' \
                       '<br><br> -The ETABot Team '
                sender = 'no-reply@etabot.ai'
                msg = email_toolbox.EmailWorker.format_email_msg(sender, str(request.user), subject, body)
                email_toolbox.EmailWorker.send_email(msg)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Format and send communication to ETAbot
        user = request.user
        subject = post_data.get('subject')
        body = 'Message:<br><br> {} <br><br> From: {}'.format(post_data.get('body'), user)
        sender = post_data.get('from') if post_data.get('from') else 'no-reply@etabot.ai'
        receiver = post_data.get('to') if post_data.get('to') else 'hello@etabot.ai'

        msg = email_toolbox.EmailWorker.format_email_msg(sender, receiver, subject, body)
        email_toolbox.EmailWorker.send_email(msg)

        # Format and send success email to user
        if post_data.get('send_confirmation'):
            logger.debug('Sending confirmation email')
            subject = '[ETAbot] Feedback received!'
            body = 'Thanks for the feedback! <br><br> Subject: {} <br> Comments: {} ' \
                   '<br><br> We\'ll review it shortly. <br><br> -The ETABot Team'.format(
                    post_data.get('subject'), post_data.get('body')
                    )
            sender = 'no-reply@etabot.ai'
            msg = email_toolbox.EmailWorker.format_email_msg(sender, str(user), subject, body)
            email_toolbox.EmailWorker.send_email(msg)

        logger.debug('User Communication POST Finished')

        return Response(status=status.HTTP_200_OK)


class CeleryTaskStatusView(APIView):

    def get(self, request, id):
        """
        Get celery task status for a particular celery task id.
        """
        # Validate Forge Invocation Token
        try:
            forge_token_payload = validate_forge_request(request)
            logger.debug(f'FIT validated for CeleryTaskStatusView: app_id={forge_token_payload.get("app", {}).get("id")}')
        except ForgeTokenValidationError as e:
            logger.warning(f'FIT validation failed for CeleryTaskStatusView: {str(e)}')
            return Response(
                {
                    "error": "Authentication failed",
                    "message": str(e)
                },
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # https://stackoverflow.com/questions/9034091/how-to-check-task-status-in-celery
        logger.debug('CeleryTaskStatusView GET started')
        task_id = id
        logger.debug('CeleryTaskStatusView GET started with id={}'.format(id))
        if not task_id:
            response_dict = {'error': 'Celery task id not provided!'}
            logger.debug('CeleryTaskStatusView GET returning {}'.format(response_dict))
            return Response(
                response_dict,
                status=status.HTTP_400_BAD_REQUEST)
        result = celery.AsyncResult(task_id)
        logger.debug('task status: {}'.format(
            result.status))

        response_dict = {
            task_id: celery.AsyncResult(task_id).status,
            '{}_result'.format(task_id): str(result.result)
        }
        logger.debug('CeleryTaskStatusView GET returning {}'.format(response_dict))
        return Response(
            data=response_dict,
            status=status.HTTP_200_OK)



class CeleryTaskResultView(APIView):

    def get(self, request, id):
        """
        Get celery task status for a particular celery task id.
        """
        # Validate Forge Invocation Token
        try:
            forge_token_payload = validate_forge_request(request)
            logger.debug(f'FIT validated for CeleryTaskResultView: app_id={forge_token_payload.get("app", {}).get("id")}')
        except ForgeTokenValidationError as e:
            logger.warning(f'FIT validation failed for CeleryTaskResultView: {str(e)}')
            return Response(
                {
                    "error": "Authentication failed",
                    "message": str(e)
                },
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # https://stackoverflow.com/questions/9034091/how-to-check-task-status-in-celery
        # todo: create decorator to check for task id instead of copy paste check
        logger.debug('CeleryTaskStatusView GET started')
        task_id = id
        logger.info('CeleryTaskStatusView GET started with id={}'.format(id))
        if not task_id:
            response_dict = {'error': 'Celery task id not provided!'}
            logger.debug('CeleryTaskStatusView GET returning {}'.format(response_dict))
            return Response(
                response_dict,
                status=status.HTTP_400_BAD_REQUEST)
        result = celery.AsyncResult(task_id)
        logger.info('task status: {}'.format(
            result.status))

        response_dict = {
            'task_id': task_id,
            'status': celery.AsyncResult(task_id).status
        }
        if result.ready():
            # Handle case where result might be an exception
            if result.failed():
                logger.warning(f'Task {task_id} failed with result: {result.result}')
                response_dict['result'] = str(result.result)
                response_dict['error'] = f'Calculation failed with error code: {task_id}'
            else:
                response_dict['result'] = result.result
            logger.info('result is ready')
        logger.debug('CeleryTaskStatusView GET returning {}'.format(response_dict))
        return Response(
            data=response_dict,
            status=status.HTTP_200_OK)

class CeleryCriticalPathHeartbeatView(APIView):
    """
    Heartbeat endpoint for AWS monitoring of Critical Path API service.
    Submits a test job to the real production server and polls for results with exponential backoff.
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """
        System-level health check for critical path API.
        
        Workflow:
        1. Submit test request to critical_paths_plugin endpoint on production server
        2. Get job_id back
        3. Poll job-result endpoint with exponential backoff
        4. Return 200 if result received within 5 seconds
        5. Return 503 if timeout exceeded
        """
        import time
        import requests
        
        logger.info('CeleryCriticalPathHeartbeatView GET started')
        
        # Get the production server URL from Django settings
        host_url = getattr(settings, 'HOST_URL', 'http://127.0.0.1:8000')
        logger.info(f'Testing against server: {host_url}')
        
        # Get authentication token from Django settings
        auth_token = getattr(settings, 'HEARTBEAT_AUTH_TOKEN', None)
        if not auth_token:
            logger.warning('HEARTBEAT_AUTH_TOKEN not configured. Requests will be unauthenticated.')
        
        # Prepare authentication headers
        headers = {}
        if auth_token:
            headers['Authorization'] = f'Token {auth_token}'
            logger.debug('Authorization header added to requests')
        
        test_payload = {
            "final_nodes": ["SDEPM-24"],
            "start_date_field_name": "customfield_10208",
            "slack_tolerance_days": 7,
            "issues": [
                {
                "key": "SDEPM-24",
                
                "fields": {
                    "summary": "Deployment to Production",
                    "customfield_10208": "2025-04-25",
                    "issuelinks": [
                    {
                        "id": "12761",
                        "self": "https://etabot.atlassian.net/rest/api/3/issueLink/12761",
                        "type": {
                        "id": "10000",
                        "name": "Blocks",
                        "inward": "is blocked by",
                        "outward": "blocks",
                        "self": "https://etabot.atlassian.net/rest/api/3/issueLinkType/10000"
                        },
                    }
                    ],
                    "issuetype": {"name": "Task"},
                    "duedate": "2025-04-29",
                    "assignee": {"displayName":"assignee_test", "accountId": "test"},
                    "key": "SDEPM-24",
                    "status": {
                    "self": "https://etabot.atlassian.net/rest/api/3/status/10128",
                    "name": "To Do",
                    "id": "10128",
                    "statusCategory": {
                        "id": 2,
                        "key": "new",
                        "colorName": "blue-gray",
                        "name": "To Do"
                    }
                    }
                }
                }
            ]
            }

        
        timeout_seconds = 30
        start_time = time.time()
        
        try:
            # Step 1: Submit request to critical_paths_plugin endpoint
            submit_url = f'{host_url}/api/critical_paths_plugin'
            logger.debug(f'Submitting test job to {submit_url}')
            
            try:
                response = requests.post(
                    submit_url,
                    json=test_payload,
                    headers=headers,
                    timeout=timeout_seconds,
                    verify=True  # Enable SSL verification for production
                )
            except requests.exceptions.RequestException as e:
                logger.error(f'Failed to submit heartbeat job due to request exception: {str(e)}')
                return Response(
                    {
                        "status": "error",
                        "message": "Failed to connect to critical_paths_plugin endpoint",
                        "details": str(e),
                        "target_url": submit_url
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            if response.status_code != 200:
                logger.error(f'Failed to submit heartbeat job. Status: {response.status_code}')
                return Response(
                    {
                        "status": "error",
                        "message": "Failed to submit test job to critical_paths_plugin",
                        "status_code": response.status_code,
                        "details": response.text,
                        "target_url": submit_url
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            # Step 2: Extract job_id from response
            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f'Failed to parse JSON response: {str(e)}')
                return Response(
                    {
                        "status": "error",
                        "message": "Invalid JSON response from critical_paths_plugin",
                        "details": response.text
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            job_id = response_data.get('task_id')
            
            if not job_id:
                logger.error('No task_id returned from critical_paths_plugin')
                return Response(
                    {
                        "status": "error",
                        "message": "No task_id returned from critical_paths_plugin",
                        "response": response_data
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            logger.info(f'Test job submitted with task_id: {job_id}')
            
            # Step 3: Poll job-result endpoint with exponential backoff
            poll_interval = 1.0  # Start with 100ms
            max_interval = 16.0
            
            while True:
                elapsed = time.time() - start_time
                
                if elapsed >= timeout_seconds:
                    logger.warning(f'Heartbeat check timed out after {elapsed:.2f} seconds')
                    return Response(
                        {
                            "status": "timeout",
                            "message": f"Job did not complete within {timeout_seconds} seconds",
                            "task_id": job_id,
                            "elapsed_seconds": elapsed,
                            "target_url": host_url
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
                
                # Check job status
                result_url = f'{host_url}/api/job-result/{job_id}/'
                logger.debug(f'Polling job result at {result_url}')
                
                try:
                    result_response = requests.get(
                        result_url,
                        headers=headers,
                        timeout=min(timeout_seconds - elapsed, 10)  # Don't let individual request exceed remaining time
                    )
                except requests.exceptions.RequestException as e:
                    logger.error(f'Failed to poll job result: {str(e)}')
                    return Response(
                        {
                            "status": "error",
                            "message": "Failed to poll job-result endpoint",
                            "task_id": job_id,
                            "details": str(e),
                            "target_url": result_url
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
                
                if result_response.status_code == 200:
                    try:
                        result_data = result_response.json()
                    except json.JSONDecodeError:
                        logger.warning('Failed to parse job result JSON, continuing to poll')
                        time.sleep(poll_interval)
                        poll_interval = min(poll_interval * 2, max_interval)
                        continue
                    
                    job_status = result_data.get('status')
                    
                    logger.debug(f'Job status: {job_status}')

                    if job_status == 'SUCCESS':
                        elapsed = time.time() - start_time
                        logger.info(f'Heartbeat check successful in {elapsed:.2f} seconds')
                        return Response(
                            {
                                "status": "healthy",
                                "message": "Critical path API is functioning correctly",
                                "task_id": job_id,
                                "elapsed_seconds": round(elapsed, 2),
                                "target_url": host_url
                            },
                            status=status.HTTP_200_OK
                        )
                    elif job_status == 'FAILURE':
                        logger.error(f'Test job failed: {result_data}')
                        return Response(
                            {
                                "status": "error",
                                "message": "Test job failed",
                                "task_id": job_id,
                                "details": result_data,
                                "target_url": host_url
                            },
                            status=status.HTTP_503_SERVICE_UNAVAILABLE
                        )
                    # Job is still pending, continue polling
                
                # Wait before next poll with exponential backoff
                time.sleep(poll_interval)
                poll_interval = min(poll_interval * 2, max_interval)
                
        except Exception as e:
            logger.error(f'Heartbeat check failed with exception: {str(e)}')
            import traceback
            logger.error(traceback.format_exc())
            return Response(
                {
                    "status": "error",
                    "message": "Heartbeat check encountered an error",
                    "details": str(e),
                    "target_url": host_url
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

