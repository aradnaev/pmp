from dataclasses import is_dataclass, asdict

from django.shortcuts import render
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.shortcuts import redirect
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response

from jira_issue import create_jira_issue_from_json
from .celery_tracking import send_celery_task_with_tracking
from etabotapp.TMSlib.JIRA_API import update_available_projects_for_TMS
from .serializers import UserSerializer, ProjectSerializer, TMSSerializer
from .models import OAuth1Token, OAuth2Token, OAuth2CodeRequest
from .models import atlassian_redirect_uri
from .models import TMS, Project
from .models import oauth
from .permissions import IsOwnerOrReadOnly, IsOwner
from etabotapp.TMSlib.JIRA_API import JIRA_wrapper
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
import networkx as nx
import pandas as pd

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
        resp = oauth.atlassian.authorize_redirect(
            request, atlassian_redirect_uri,
            state=state,
            scope=scope)

        logger.debug(resp)
        logger.debug(vars(resp))
        oa2cr = OAuth2CodeRequest(
            owner=request.user,
            name=oauth_name,
            timestamp=timestamp,
            state=state)
        oa2cr.save()

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
            token = oauth.atlassian.authorize_access_token(
                request, redirect_uri=atlassian_redirect_uri)

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
        logger.info('CriticalPathsViewJIRAplugin started.')
        params = {}
        post_data = {}
        if request.body:
            logger.debug('request.body: {}'.format(request.body))
            post_data = json.loads(request.body)
            params = post_data.get('params', {})
            logger.debug('CriticalPathView call global_params: {}'.format(params))
        if 'final_nodes' in post_data:
            final_nodes = post_data['final_nodes']
            logger.debug(f'got final_nodes: {final_nodes}')
        else:
            return Response(
                {
                    "error": "No final_nodes passed."
                },
                status=status.HTTP_400_BAD_REQUEST)

        if 'start_date_field_name' not in post_data:
            return Response(
                {
                    "error": "No start_date_field_name passed."
                },
                status=status.HTTP_400_BAD_REQUEST)
        else:
            start_date_field_name = post_data['start_date_field_name']

        if 'issues' in post_data:
            issues_dict = post_data['issues']
        else:
            return Response(
                {
                    "error": "No tasks aka issues passed."
                },
                status=status.HTTP_400_BAD_REQUEST)
        tasks = []
        for issue_dict in issues_dict:
            try:
                issue = create_jira_issue_from_json(issue_dict)
                tasks.append(issue)
                start_date = issue.get_field(start_date_field_name)
                if start_date is None:
                    logger.warning(f'start_date is None for issue {issue.key}.'
                                   f'dict {start_date_field_name}: {issue_dict["fields"].get(start_date_field_name)}.'
                                   f'issue fields {issue.fields}.'
                                   f'issue_dict {issue_dict}')
            except Exception as e:
                return Response(
                    {
                        "error": f"Cannot parse this issue due to {e}: {issue_dict}."
                    },
                    status=status.HTTP_400_BAD_REQUEST)

        eta_date_field_name = post_data.get('eta_date_field_name')
        cpg, critical_paths_for_nodes = TMSlib.cp.generate_critical_paths_report_for_tasks(
            tasks=tasks, start_date_field_name=start_date_field_name, eta_date_field_name=eta_date_field_name,
            final_nodes=final_nodes, params=params)

        critical_paths_for_nodes["cpg_data"] = {
            "slack_tolerance_for_crit_path_s": cpg.slack_tolerance_for_crit_path_s,
            "action_items_per_assignee": cpg.action_items_per_assignee,
            "action_items_for_pm": cpg.action_items_for_pm,
        }

        def json_serial(obj):
            if is_dataclass(obj):
                return asdict(obj)
            elif isinstance(obj, datetime.datetime):
                return obj.isoformat()
            elif isinstance(obj, datetime.timedelta):
                return obj.total_seconds()
            elif isinstance(obj, pd.DataFrame):
                return obj.to_dict(orient="records")
            elif isinstance(obj, nx.Graph):
                return None
            raise TypeError(f"Type {type(obj)} not serializable")

        # using replace is hackish, but could not figure out how to do robustly in json_serial
        json_response = json.dumps(critical_paths_for_nodes, indent=4, default=json_serial).replace('NaN', 'null')

        return Response(
            data=json_response,
            status=status.HTTP_200_OK)


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
        logger.debug('task status: {}'.format(
            celery.AsyncResult(task_id).status))
        response_dict = {
            task_id: celery.AsyncResult(task_id).status,
            '{}_result'.format(task_id): str(celery.AsyncResult(task_id).result)
        }
        logger.debug('CeleryTaskStatusView GET returning {}'.format(response_dict))
        return Response(
            data=response_dict,
            status=status.HTTP_200_OK)
