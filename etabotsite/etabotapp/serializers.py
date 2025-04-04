from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework.validators import UniqueTogetherValidator
from django.contrib.auth.models import User

from .constants import PROJECTS_AVAILABLE
from .models import Project, TMS
from .models import oauth
from django.conf import settings
import logging
import etabotapp.TMSlib.TMS as TMSlib
from etabotapp.TMSlib.JIRA_API import update_available_projects_for_TMS
from copy import copy
import etabotapp.response_regex as rr

LOCAL_MODE = getattr(settings, "LOCAL_MODE", False)
logger = logging.getLogger('django')


class UserSerializer(serializers.ModelSerializer):
    """Serializer to map the Model instance into JSON format."""
    email_validators = []
    if not LOCAL_MODE:
        email_validators.append(UniqueValidator(queryset=User.objects.all()))

    email = serializers.EmailField(
        required=True,
        validators=email_validators
    )
    username = serializers.CharField(
        validators=[UniqueValidator(queryset=User.objects.all())]
    )
    password = serializers.CharField(min_length=8, write_only=True)
    projects = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Project.objects.all()
    )
    TMSAccounts = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=TMS.objects.all()
    )
    is_active = serializers.BooleanField(
        required=False
    )

    def create(self, validated_data):
        user = User.objects.create_user(validated_data['username'],
                                        validated_data['email'],
                                        validated_data['password'])
        user.is_active = False
        return user

    class Meta:
        """Meta class to map serializer's fields with the model fields."""
        model = User
        fields = (
            'id', 'username', 'password',
            'email', 'is_active', 'projects', 'TMSAccounts')
        write_only_fields = ('password',)
        read_only_fields = ('id',)


class OAuth2TokenSerializer(serializers.ModelSerializer):
    """Serializer to map the model instance into json format."""
    owner = serializers.ReadOnlyField(source='owner.username')

#     class Meta:
#         """Map this serializer to a model and their fields."""
#         model = OAuth2Token
#         fields = (
#             'id',
#             'owner',
#             'name',
#             'token_type',
#             'access_token',
#             'refresh_token',
#             'expires_at')

#     # def create(self, validated_data):
#     #     token = OAuth2Token.objects.create_token(
#     #         validated_data['username'],
#     #         validated_data['email'],
#     #         validated_data['password'])
#     #     user.is_active = False
#     #     return user


class TMSSerializer(serializers.ModelSerializer):
    """Serializer to map the model instance into json format."""
    owner = serializers.ReadOnlyField(source='owner.username')
    connectivity_status = serializers.JSONField()
    logger.debug('TMSSerializer owner: {}'.format(owner))

    class Meta:
        """Map this serializer to a model and their fields."""
        model = TMS
        fields = (
            'id',
            'owner',
            'endpoint',
            'username',
            'password',
            'type',
            'params',
            'name',
            'connectivity_status')

    def validate(self, val_input):
        """Validate credentials and endpoint result in successful login.
        self.initial_data - only subset of parameters defined in API call
        """

        logger.info('validate_tms_credential started')
        logger.debug('self.initial_data: {}'.format(self.initial_data))
        # logger.debug('val_input: {}'.format(val_input))
        logger.debug('context: {}'.format(self.context))
        owner = self.context['request'].user
        logger.debug('owner: {}, type: {}'.format(
            owner, type(owner)))
        logger.debug('self.initial_data[owner]="{}"'.format(
            self.initial_data.get('owner')))
        logger.debug('request method: {}'.format(
            self.context['request'].method))
        if self.context['request'].method == 'POST':
            endpoint = self.initial_data['endpoint']
            if TMS.objects.filter(
                        endpoint=endpoint,
                        owner=owner).exists():
                raise serializers.ValidationError(
                        'Combination {}@{} already exists for this user'.format(
                            owner, endpoint))
            logger.debug(
                'validated username/endpoint combination uniqueness current user')
            tms_params = copy(self.initial_data)
            if 'owner' in tms_params:
                # tests using API client that posts different initial data
                # when it comes to owner
                tms_params['owner'] = owner
            instance = TMS(**tms_params)
            self.validate_credentials_and_update_projects_available(instance)
            if 'params' not in self.initial_data:
                self.initial_data['params'] = {}
            self.initial_data['params'][PROJECTS_AVAILABLE] = instance.params[PROJECTS_AVAILABLE]
            if val_input.get('params') is None:
                val_input['params'] = {}
            val_input['params'][PROJECTS_AVAILABLE] = instance.params[PROJECTS_AVAILABLE]
        elif self.context['request'].method == 'PATCH':
            for k, v in self.initial_data.items():
                setattr(self.instance, k, v)
                logger.debug('patching TMS attribute "{}"'.format(k))
            self.validate_credentials_and_update_projects_available(self.instance)
        else:
            raise serializers.ValidationError('unsupported method {}'.format(
                self.context['request'].method))

        logger.info('validate_tms_credential finished')
        return val_input

    def validate_credentials_and_update_projects_available(self, instance):
        logger.info('validate_Atlassian_API_key started.')
        logger.debug('TMS instance: {}, params: {}'.format(instance, instance.params))
        TMS_w1 = TMSlib.TMSWrapper(instance)
        error = TMS_w1.connect_to_TMS(update_tms=False)
        if error is not None:
            logger.debug('Error in validation: {}'.format(error))
            if 'Unauthorized (401)' in error:
                raise serializers.ValidationError('Unable to log in due to "Unauthorized (401)"\
 error - please check username/email and password')
            elif 'cannot connect to TMS JIRA' in error:
                logger.debug('cannot connect to TMS JIRA error.')
                captcha_sig = \
                    "'X-Authentication-Denied-Reason': 'CAPTCHA_CHALLENGE"
                if captcha_sig in error:
                    message = 'Need to pass CAPTCHA challenge first. '
                    login_urls = rr.get_login_url(error)
                    if len(login_urls) > 0:
                        login_url = login_urls[0]
                        logger.debug('login_url: {}'.format(login_url))
                    else:
                        logger.debug(
                            'No login url detected, using TMS endpoint.')
                        login_url = instance.endpoint
                    message += 'Please login at <a href="{login_url}">{login_url}</a> \
first and then try again. '.format(login_url=login_url)
                    message += 'If the issue persists, please ask your \
administrator to disable CAPTCHA.'
                    raise serializers.ValidationError(message)
                else:
                    logger.debug('generic connectivity issue.')
                    raise serializers.ValidationError('cannot connect to TMS JIRA - please check\
     inputs and try again. If the issue persists, please report the issue to \
    hello@etabot.ai')
            else:
                raise serializers.ValidationError('Unrecognized error has occurred - please check\
inputs and try again. If the issue persists, please report the issue to \
hello@etabot.ai')
        update_available_projects_for_TMS(instance, TMS_w1.jira)
        logger.info('validate_Atlassian_API_key finished.')


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer to map the model instance into json format."""
    owner = serializers.ReadOnlyField(source='owner.username')
    work_hours = serializers.JSONField()
    vacation_days = serializers.JSONField()
    velocities = serializers.JSONField()
    project_settings = serializers.JSONField()

    class Meta:
        """Map this serializer to a model and their fields."""
        model = Project
        fields = (
            'id',
            'project_tms',
            'name',
            'owner',
            'mode',
            'open_status',
            'grace_period',
            'work_hours',
            'vacation_days',
            'velocities',
            'project_settings')
        # read_only_fields = ('mode', 'name')
