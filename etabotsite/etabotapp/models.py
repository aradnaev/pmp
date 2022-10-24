import sys
import logging
import os

logging.debug('models import started.')
# sys.path.append(os.path.abspath('etabotapp'))
logging.debug('loading TMSlib')
print('loading TMSlib')
import etabotapp.TMSlib.TMS as TMSlib
logging.debug('loaded TMSlib')
print('loaded TMSlib')
import etabotapp.TMSlib.data_conversion as dc
import etabotapp.TMSlib.Atlassian_API as Atlassian_API
print('loaded TMSlib data_conversion, Atlassian_API ')

from django.db import models
from django.contrib.postgres.fields import JSONField
from django.db.models.signals import post_save, pre_save
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.dispatch import receiver
print('loaded django modules')
from etabotapp.user_activation import ActivationProcessor
print('loaded user_activation')
from encrypted_model_fields.fields import EncryptedCharField
import time

from django.conf import settings
from authlib.integrations.django_client import OAuth
from etabotapp.constants import PROJECTS_AVAILABLE
from etabotapp.constants import PROJECTS_USER_SELECTED

logger = logging.getLogger(__name__)

#from django.contrib.postgres.fields.jsonb import JSONField


class OAuth1Token(models.Model):
    owner = models.ForeignKey('auth.User', related_name='OAuth1Tokens',
                              on_delete=models.CASCADE)    
    name = models.CharField(max_length=40)
    oauth_token = models.CharField(max_length=2048)
    oauth_token_secret = models.CharField(max_length=2048)

    def to_token(self):
        return dict(
            oauth_token=self.access_token,
            oauth_token_secret=self.alt_token,
        )


class OAuth2CodeRequest(models.Model):
    """Model for Stracking OAuth2 states and users."""
    owner = models.ForeignKey('auth.User', related_name='OAuth2CodeRequests',
                              on_delete=models.CASCADE)    
    name = models.CharField(max_length=40)
    state = models.CharField(max_length=200)
    timestamp = models.DateTimeField(null=True)


class OAuth2Token(models.Model):
    """Model for Storing tokens from OAuth2."""
    owner = models.ForeignKey('auth.User', related_name='OAuth2Tokens',
                              on_delete=models.CASCADE)    
    name = models.CharField(max_length=40)
    token_type = models.CharField(max_length=20)
    access_token = models.CharField(max_length=2048)
    refresh_token = models.CharField(max_length=2048, null=True)
    expires_at = models.PositiveIntegerField(null=True)

    def is_expired(self):
        logger.debug('checking if Oauth2 token is expired.')
        return time.time() > self.expires_at

    def to_token(self):
        return dict(
            access_token=self.access_token,
            token_type=self.token_type,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
        )

    @classmethod
    def find(cls, **kwargs):
        res = cls.objects.all().filter(**kwargs)
        if len(res) == 1:
            return res[0]
        elif len(res) > 1:
            logger.warning('search params {} found more than one of tokens: {}'.format(
                kwargs, res))
            return res[len(res)]
        else:
            return None


def fetch_oauth_token(name, request):
    """Authlib support function."""
    logger.debug('fetching token {} {}'.format(name, request))
    OAUTH1_SERVICES = []
    if name in OAUTH1_SERVICES:
        model = OAuth1Token
    else:
        model = OAuth2Token
    logger.info('authlib fetch_token searching for token in model {}'.format(
        model))
    token = model.find(
        name=name,
        owner=request.user
    )
    if token is not None:
        return token.to_token()
    else:
        raise NameError('no token found for {} {}'.format(name, request.user))


def update_oauth_token(name, token, refresh_token=None, access_token=None):
    """Authlib support function.""" 
    logger.info('updating token')
    if refresh_token:
        logger.info('searching for token by refresh_token')
        item = OAuth2Token.find(name=name, refresh_token=refresh_token)
    elif access_token:
        item = OAuth2Token.find(name=name, access_token=access_token)
    else:
        return

    # update old token
    TMSs = TMS.objects.filter(oauth2_token=item.id)
    logger.debug('found TMSs with this oauth2 token: {}'.format(TMSs))
    for tms_instance in TMSs:
        logger.debug(vars(tms_instance))
        logger.debug(tms_instance.oauth2_token)        
        logger.debug(vars(tms_instance.oauth2_token))
    item.access_token = token['access_token']
    item.refresh_token = token.get('refresh_token')
    item.expires_at = token['expires_at']
    logger.info('saving token')
    item.save()
    logger.info('token saved')
    logger.debug('TMSs after saving token:')
    for tms_instance in TMSs:
        logger.debug(vars(tms_instance))
        logger.debug(tms_instance.oauth2_token)        
        logger.debug(vars(tms_instance.oauth2_token))
    TMSs = TMS.objects.filter(oauth2_token=item.id)
    logger.debug('TMSs after saving token and repeat search:')
    for tms_instance in TMSs:
        logger.debug(vars(tms_instance))
        logger.debug(tms_instance.oauth2_token)
        logger.debug(vars(tms_instance.oauth2_token))
    logger.info('update_oauth_token is done.')


class TMS(models.Model):
    """This class represents the TMS account model."""
    owner = models.ForeignKey(
        'auth.User',
        related_name='TMSAccounts',
        on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=60)
    username = models.CharField(max_length=60, null=True)
    password = EncryptedCharField(max_length=60, null=True)
    type = models.CharField(max_length=20, choices=TMSlib.TMS_TYPES)
    connectivity_status = JSONField(null=True)
    name = models.CharField(max_length=60, null=True)
    params = JSONField(null=True)
    oauth2_token = models.ForeignKey(OAuth2Token, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return "{}@{}".format(self.username, self.endpoint)

    def get_fresh_token(self):
        token = self.oauth2_token
        logger.debug('initial token: {}'.format(token))
        logger.debug('initial token vars: {}'.format(vars(token)))
        token_dict = token.to_token()
        logger.debug('initial token dict: {}'.format(token_dict))
        logger.info('priming TMS GET with oauth...')
        res = oauth.atlassian.get(
            Atlassian_API.ATLASSIAN_CLOUD_PROFILE, token=token_dict)
        logger.info('got oauth.atlassian result')
        logger.debug(res)
        logger.debug(vars(res))
        logger.debug('before TMS refresh from db self.oauth2_token: {}'.format(self.oauth2_token))
        logger.debug('before TMS refresh from db vars self.oauth2_token: {}'.format(vars(self.oauth2_token)))
        logger.debug('before TMS refresh from db token vars: {}'.format(vars(token)))

        logger.debug('refreshing TMS from db')
        self.refresh_from_db()
        logger.debug('after refreshing from db self.oauth2_token: {}'.format(self.oauth2_token))
        logger.debug('after refreshing from db vars self.oauth2_token: {}'.format(vars(self.oauth2_token)))
        logger.debug('after refreshing from db token vars: {}'.format(vars(token)))

        logger.debug('reassigning token to self.oauth2_token...')
        token = self.oauth2_token
        logger.debug('token vars: {}'.format(vars(token)))
        return token


class Project(models.Model):
    """This class represents the project model."""

    owner = models.ForeignKey('auth.User', related_name='projects',
                              on_delete=models.CASCADE)
    project_tms = models.ForeignKey(TMS, on_delete=models.CASCADE)
    name = models.CharField(max_length=60)
    mode = models.CharField(max_length=60)  # scrum or kanban
    open_status = models.CharField(max_length=60)
    grace_period = models.FloatField()
    work_hours = JSONField()
    vacation_days = JSONField()
    velocities = JSONField(null=True)
    project_settings = JSONField(null=True)
    # jobs = JSONField(null=True)

    def __str__(self):
        return self.name


class CeleryTask(models.Model):
    """This class represents the Celery Task (previously known as job) model."""
    task_id = models.CharField(max_length=100, primary_key=True)
    task_name = models.CharField(max_length=100)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True)

    # May need to add some more choices and/or specify 'other' option
    status = models.CharField(
        choices=[
            ('PN', 'Pending'),
            ('CN', 'Canceled'),
            ('DN', 'Done'),
            ('FL', 'Failed'),
            ('X', 'Other')
        ], max_length=100
    )

    owner = models.ForeignKey('auth.User', related_name='celeryTasks',
                              on_delete=models.CASCADE)

    meta_data = JSONField(null=True)

# This receiver handles token creation immediately a new user is created.
@receiver(post_save, sender=User)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)
        user = User.objects.get(pk=instance.id)
        user.is_active = False
        user.save()

        ActivationProcessor.email_token(user)

# @receiver(post_save, sender=TMS)
# def parse_tms(sender, instance, created, **kwargs):
#     if created:
#         logger.debug('new TMS instance created - parsing projects')
#         parse_projects_for_TMS(instance, **kwargs)
#     else:
#         logger.debug('saving existing TMS - no need to parse projects')


def parse_projects_for_TMS(instance: TMS, **kwargs) -> str:
    """Parse projects for the given TMS.

    Creates new Django model projects objects with parsed data.
    Returns response_message.
    Arguments:
        instance - Django TMS object instance
    """
    logger.info('parse_tms started')
    logger.debug('parse_projects_for_TMS kwargs: {}'.format(kwargs))
    existing_projects = list(Project.objects.filter(project_tms=instance.id))
    logger.info('existing_projects: {}'.format(existing_projects))
    existing_projects_dict = {}
    for p in existing_projects:
        existing_projects_dict[p.name] = p

    projects_names_user_selected = instance.params.get(
        PROJECTS_USER_SELECTED,
        instance.params.get(PROJECTS_AVAILABLE, []))
    logger.debug('projects_names_user_selected: {}'.format(projects_names_user_selected))
    new_projects_user_selected = {}
    for user_selected_project in projects_names_user_selected:
        if user_selected_project not in existing_projects_dict:
            new_django_project = Project(
                owner=instance.owner,
                project_tms=instance,
                name=user_selected_project,
                mode='unknown mode',
                open_status='',
                velocities={},
                grace_period=12.0,
                work_hours={},
                vacation_days={},
                project_settings={})
            new_django_project.save()
            new_projects_user_selected[user_selected_project] = new_django_project
    full_projects_list = existing_projects + list(new_projects_user_selected.values())
    TMS_w1 = TMSlib.TMSWrapper(
        instance,
        projects=full_projects_list)

    TMS_w1.init_ETApredict(full_projects_list)

    projects_dict = TMS_w1.ETApredict_obj.eta_engine.projects
    velocities = TMS_w1.ETApredict_obj.eta_engine.user_velocity_per_project
    logger.debug('parse_tms: velocities found: {}'.format(velocities))

    new_projects = []
    updated_projects = []

    logger.info('passing parsed projects info to Django models.')
    if projects_dict is not None:
        for project_name, attrs in projects_dict.items():
            p = None
            velocity_json = dc.get_velocity_json(
                velocities, project_name)

            if project_name not in existing_projects_dict:
                if project_name in new_projects_user_selected:
                    new_projects.append(project_name)
                    p = new_projects_user_selected[project_name]
                    p.open_status = attrs.get('open_status', '')
                    p.grace_period = attrs.get('grace_period', 12.0)
                    p.work_hours = attrs.get('work_hours', {})
                    p.vacation_days = attrs.get('vacation_days', [])
                else:
                    logger.warning('Found project "{}", but did not intent to find.'.format(project_name))
            else:
                p = existing_projects_dict[project_name]
                updated_projects.append(project_name)
            if p is not None:
                p.velocities = velocity_json
                p.project_settings = attrs.get(
                    'project_settings', p.project_settings)
                p.mode = attrs.get('mode', p.mode)
                p.save()

    else:
        logger.warning('projects_dict is None')
    logger.info('parse_tms has finished')
    response_message = ''
    if len(new_projects) > 0:
        response_message += "New projects found and parsed: {}.".format(
            ', '.join(new_projects))
    else:
        response_message += 'No new projects detected - please ensure there are done tasks assigned to you.'
    if len(updated_projects) > 0:
        response_message += " Updated existing projects: {}.".format(
            ', '.join(updated_projects))
    logger.info('parse_tms response: {}'.format(response_message))
    return response_message


PROD_HOST_URL = getattr(settings, "PROD_HOST_URL", "http://localhost:8000")
atlassian_redirect_uri = PROD_HOST_URL + '/atlassian_callback'
logger.debug('atlassian_redirect_uri: "{}"'.format(atlassian_redirect_uri))

oauth = OAuth(fetch_token=fetch_oauth_token, update_token=update_oauth_token)
oauth.register(name='atlassian')
logger.debug('oauth registered: {}'.format(oauth.atlassian))
logger.info('models import finished.')
