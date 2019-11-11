import sys
import os
import logging

logging.getLogger().setLevel(logging.DEBUG)
logging.info('models import started.')
sys.path.append(os.path.abspath('etabotapp'))
import TMSlib.TMS as TMSlib
import TMSlib.data_conversion as dc

sys.path.pop(0)

from django.db import models
from jsonfield import JSONField

from django.db.models.signals import post_save, pre_save
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from user_activation import ActivationProcessor

from encrypted_model_fields.fields import EncryptedCharField
from django.utils.translation import gettext as _
import datetime
import time
import pytz

class OAuth1Token(models.Model):
    owner = models.ForeignKey('auth.User', related_name='OAuth1Tokens',
                              on_delete=models.CASCADE)    
    name = models.CharField(max_length=40)
    oauth_token = models.CharField(max_length=200)
    oauth_token_secret = models.CharField(max_length=200)
    

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
    refresh_token = models.CharField(max_length=200, null=True)
    expires_at = models.PositiveIntegerField(null=True)

    def is_expired(self):

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
            logging.warning('search params {} found more than one of tokens: {}'.format(
                kwargs, res))
            return res[len(res)]
        else:
            return None

def fetch_oauth_token(name, request):
    """Authlib support function."""
    OAUTH1_SERVICES = []
    if name in OAUTH1_SERVICES:
        model = OAuth1Token
    else:
        model = OAuth2Token
    logging.info('authlib fetch_token searching for token in model {}'.format(
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
    logging.info('updating token')
    if refresh_token:
        logging.info('searching for token by refresh_token')
        item = OAuth2Token.find(name=name, refresh_token=refresh_token)
    elif access_token:
        item = OAuth2Token.find(name=name, access_token=access_token)
    else:
        return

    # update old token
    item.access_token = token['access_token']
    item.refresh_token = token.get('refresh_token')
    item.expires_at = token['expires_at']
    logging.info('saving token')
    item.save()
    logging.info('token saved')

class TMS(models.Model):
    """This class represents the TMS account model."""
    owner = models.ForeignKey(
        'auth.User',
        related_name='TMSAccounts',
        on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=60)
    username = models.CharField(max_length=60, null=True)
    password = EncryptedCharField(max_length=60, null=True)
    oauth2_token = models.ForeignKey(OAuth2Token, on_delete=models.CASCADE, null=True)
    type = models.CharField(max_length=20, choices=TMSlib.TMS_TYPES)
    connectivity_status = JSONField(null=True)
    name = models.CharField(max_length=60, null=True)
    params = JSONField(null=True)

    def __str__(self):
        return "{}@{}".format(self.username, self.endpoint)


class Project(models.Model):
    """This class represents the project model."""
    # jiraacount = models.ForeignKey(JIRAAccount, on_delete=models.CASCADE)
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


# This receiver handles token creation immediately a new user is created.
@receiver(post_save, sender=User)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)
        user = User.objects.get(pk=instance.id)
        user.is_active = False
        user.save()

        ActivationProcessor.email_token(user)

@receiver(post_save, sender=TMS)
def parse_tms(sender, instance, created, **kwargs):
    if created:
        logging.debug('new TMS instance created - parsing projects')
        parse_projects_for_TMS(instance, **kwargs)
    else:
        logging.debug('saving existing TMS - no need to parse projects')


def parse_projects_for_TMS(instance, **kwargs):
    """Parse projects for the given TMS.

    Creates new Django model projects objects with parsed data.

    Arguments:
        instance - Django TMS object instance
    """
    logging.debug('parse_tms started with kwargs: {}'.format(kwargs))
    existing_projects = Project.objects.filter(project_tms=instance.id)
    TMS_w1 = TMSlib.TMSWrapper(
        instance,
        projects=existing_projects,
        oauth_obj=oauth)
    TMS_w1.init_ETApredict([])

    projects_dict = TMS_w1.ETApredict_obj.eta_engine.projects
    velocities = TMS_w1.ETApredict_obj.user_velocity_per_project
    logging.debug('parse_tms: velocities found: {}'.format(velocities))

    existing_projects_dict = {}
    for p in existing_projects:
        existing_projects_dict[p.name] = p

    new_projects = []
    updted_projects = []
    if projects_dict is not None:
        for project_name, attrs in projects_dict.items():
            velocity_json = dc.get_velocity_json(
                velocities, project_name)

            if project_name not in existing_projects_dict:
                new_django_project = Project(
                    owner=instance.owner,
                    project_tms=instance,
                    name=project_name,
                    mode=attrs.get('mode', 'unknown mode'),
                    open_status=attrs.get('open_status', ''),
                    velocities=velocity_json,
                    grace_period=attrs.get('grace_period', 12.0),
                    work_hours=attrs.get('work_hours', {}),
                    vacation_days=attrs.get('vacation_days', {}),
                    project_settings=attrs.get('project_settings', {}))
                new_django_project.save()
                new_projects.append(project_name)
            else:
                p.velocities = velocity_json
                p.project_settings = attrs.get(
                    'project_settings', p.project_settings)
                p.mode = attrs.get('mode', p.mode)
                p.save()
                updted_projects.append(project_name)
    logging.debug('parse_tms has finished')
    return "New projects found and parsed: {}. \
 Updated existing projects: {}".format(
        ', '.join(new_projects),
        ', '.join(updted_projects))


from django.conf import settings
from authlib.django.client import OAuth

PROD_HOST_URL = getattr(settings, "PROD_HOST_URL", "http://localhost:8000")
atlassian_redirect_uri = PROD_HOST_URL + '/atlassian_callback'
logging.debug('atlassian_redirect_uri: "{}"'.format(atlassian_redirect_uri))

oauth = OAuth(fetch_token=fetch_oauth_token, update_token=update_oauth_token)
oauth.register(name='atlassian')
logging.debug('oauth registered: {}'.format(oauth.atlassian))




logging.info('models import finished.')
