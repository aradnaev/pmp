import json
from unittest.mock import patch

import factory
import logging
from django.test import TestCase
from django.db.models import signals
from django.contrib.auth.models import User

from etabotapp.TMSlib.Atlassian_API import AtlassianAPI
from etabotapp.TMSlib.interface import HierarchicalReportNode, BasicReport
from etabotapp.models import Project, TMS, parse_projects_for_TMS, PROJECTS_USER_SELECTED, OAuth2Token
from rest_framework.test import APIClient
from rest_framework.test import APITestCase
from rest_framework import status
from django.conf import settings
from copy import copy
import pandas as pd
import numpy as np
import datetime

from etabotapp.views import AtlassianOAuthCallback

test_tms_data = getattr(settings, "TEST_TMS_DATA", None)
if test_tms_data['username'] == '':
    logging.warning('test_tms_data username is an empty string. Some tests will not run.')


def create_test_user():
    return User.objects.create_user(
    'testuser',
    'test@example.com',
    'testpassword')


class UserTest(APITestCase):
    def setUp(self):
        # We want to go ahead and originally create a user.
        self.test_user = create_test_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.test_user)

    def test_create_user(self):
        """
        Ensure we can create a new user and a valid token is created with it.
        """
        data = {
            'username': 'foobar',
            'email': 'foobar@example.com',
            'password': 'somepassword'
        }

        response = self.client.post('/api/users/', data, format='json')

        # We want to make sure we have two users in the database..
        self.assertEqual(User.objects.count(), 2)
        # And that we're returning a 201 created code.
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Additionally, we want to return the username and email upon
        # successful creation.
        self.assertEqual(response.data['username'], data['username'])
        self.assertEqual(response.data['email'], data['email'])
        self.assertFalse('password' in response.data)

def mock_up_TMS(user):
    return TMS(**(create_tms_data_for_user(user)))


def create_tms_data_for_user(user, **kwargs):
    tms_data = copy(test_tms_data)
    tms_data['owner'] = user
    for kw, arg in kwargs.items():
        tms_data[kw] = arg
    return tms_data


class TMSModelTestCase(TestCase):
    """This class defines the test suite for the tms model."""

    def setUp(self):
        """Define the test client and other test variables."""
        user = create_test_user()
        self.tms = mock_up_TMS(user)

    @factory.django.mute_signals(signals.pre_save, signals.post_save)
    def test_model_can_create_a_tms(self):
        """Test the user model can create a tms."""
        old_count = TMS.objects.count()
        self.tms.save()
        new_count = TMS.objects.count()
        self.assertNotEqual(old_count, new_count)


class TMSViewTestCase(TestCase):
    """Test suite for the api TMS views."""

    @factory.django.mute_signals(signals.pre_save, signals.post_save)
    def setUp(self):
        """Define the TMS test client and other test variables."""
        user = create_test_user()

        self.client = APIClient()
        self.client.force_authenticate(user=user)

        self.tms_data = create_tms_data_for_user(
            user.id, name="test_TMS_name")
        self.response = self.client.post(
            '/api/tms/',
            self.tms_data,
            format="json")
        logging.debug(self.response)
        logging.debug(self.response.__dict__)

    def test_api_can_create_a_tms(self):
        """Test the api has tms creation capability."""
        self.assertEqual(self.response.status_code, status.HTTP_201_CREATED)

    def test_authorization_is_enforced(self):
        """Test that the tms api has user authorization."""
        new_client = APIClient()
        res = new_client.get('/api/tms/', kwargs={'pk': 0}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_can_get_a_tms(self):
        """Test the api can get a given tms."""
        tms = TMS.objects.get()
        logging.debug(tms)        
        response = self.client.get(
            '/api/tms/',
            kwargs={'pk': tms.id}, format="json")
        logging.debug(response)
        logging.debug(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['id'], tms.id)

    def test_api_can_update_tms(self):
        """Test the api can update a given tms."""
        tms = TMS.objects.get()
        change_tms = {'password': 'newpassword'}
        url = '{}{}{}'.format('/api/tms/update/', tms.id, '/')
        res = self.client.patch(
            url,
            change_tms, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_api_can_delete_tms(self):
        """Test the api can delete a tms."""
        tms = TMS.objects.get()
        url = '{}{}{}'.format('/api/tms/', tms.id, '/')
        response = self.client.delete(
            url,
            format='json',
            follow=True)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_parse_projects_for_TMS(self):
        tms = TMS.objects.get()
        if tms.params is None:
            tms.params = {}
        tms.params[PROJECTS_USER_SELECTED] = ['ETAbot-Demo']
        parse_projects_for_TMS(tms)
        projects = Project.objects.all().filter(project_tms=tms.id)
        assert len(projects) == 1
        assert projects[0].name == 'ETAbot-Demo'
        del tms.params[PROJECTS_USER_SELECTED]  # this should switch to selecting all available projects
        parse_projects_for_TMS(tms)
        projects = Project.objects.all().filter(project_tms=tms.id)
        assert len(projects) >= 3


class ProjectModelTestCase(TestCase):
    """This class defines the test suite for the project model."""

    def setUp(self):
        """Define the test client and other test variables."""
        user = create_test_user()
        self.tms = mock_up_TMS(user)
        self.tms.save()
        self.project_name = "etabot"
        self.project_mode = "scrum"
        self.project_open_status = "ToDo"
        self.project_grace_period = "24"
        self.project_work_hours = {1:(10,14),2:(16,20), 3:(10,14), 4:(16,18), 5:(20,21), 6:(23,23), 0:(9,10)}
        self.project_vacation_days = {1:('2017-04-21', '2017-04-30'), 2:('2017-05-16', '2017-05-19'), 3:('2017-05-24', '2017-05-24'), 4:('2017-05-29', '2017-05-29')}
        self.project = Project(
            owner=user,
            project_tms=self.tms,
            name=self.project_name,
            mode=self.project_mode,
            open_status=self.project_open_status,
            grace_period=self.project_grace_period,
            work_hours=self.project_work_hours,
            vacation_days=self.project_vacation_days)
        
    def test_model_can_create_a_project(self):
        """Test the user model can create a project."""
        old_count = Project.objects.count()
        self.project.save()
        new_count = Project.objects.count()
        self.assertNotEqual(old_count, new_count)


class ProjectViewTestCase(APITestCase):
    """Test suite for the api views."""

    def setUp(self):
        """Define the test client and other test variables."""
        user = create_test_user()

        self.client = APIClient()
        res = self.client.force_authenticate(user=user)
        logging.debug('force_authenticate result: {}'.format(res))

        self.tms = mock_up_TMS(user)
        self.tms.save()
         
        logging.debug('TMS:')
        logging.debug(self.tms)
        logging.debug(self.tms.id)
        hn = HierarchicalReportNode(BasicReport.empty_report('Test'), 'entity')
        hn.report.velocity_report.df_sprint_stats = pd.DataFrame(
            {'t': [datetime.datetime(2020, 3, 15), np.datetime64('2020')], 'd': [np.nan, None]})

        self.project_data = {
            'owner': user.id,
            'project_tms': self.tms.id,
            'name': 'etabot',
            'mode': 'scrum',
            'open_status': 'ToDo',
            'grace_period': '24',
            'work_hours': '1:(10,14)',
            'vacation_days': '(2017-04-21, 2017-04-30)',
            'velocities': {},
            'project_settings': {'hierarchical_report': json.dumps(hn.to_dict())}}
        logging.debug('POST {}'.format(self.project_data))
        self.response = self.client.post('/api/projects/',
                                         self.project_data,
                                         format="json")
        logging.debug('client project post response:')
        logging.debug(self.response)
        logging.debug(self.response.__dict__)        
        # django.db.utils.IntegrityError: null value in column "project_tms_id" violates not-null constraint        
        self.assertEqual(Project.objects.count(), 1)
        # And that we're returning a 201 created code.
        self.assertEqual(self.response.status_code, status.HTTP_201_CREATED)
        all_projects = Project.objects.all()
        logging.debug(all_projects)

    def test_api_can_create_a_project(self):
        """Test the api has user creation capability."""
        self.assertEqual(self.response.status_code, status.HTTP_201_CREATED)

    def test_authorization_is_enforced(self):
        """Test that the api has user authorization."""
        new_client = APIClient()
        res = new_client.get('/api/projects/', kwargs={'pk': 0}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_can_get_a_project(self):
        """Test the api can get a given project."""
        logging.info('test_api_can_get_a_project')
        logging.debug(Project.objects.all())
        logging.debug(Project.objects.get())
        project = Project.objects.get()
        response = self.client.get(
            '/api/projects/',
            kwargs={'pk': project.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, project)

    def test_api_can_update_project(self):
        """Test the api can update a given project."""
        project = Project.objects.get()
        change_project = {'mode': 'kanban'}
        url = '{}{}{}'.format('/api/projects/', project.id, '/')
        res = self.client.patch(url, change_project, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_api_can_delete_project(self):
        """Test the api can delete a project."""
        project = Project.objects.get()
        url = '{}{}{}'.format('/api/projects/', project.id, '/')
        response = self.client.delete(url, format='json', follow=True)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class CriticalPathsViewTestCase(APITestCase):
    """Test suite for user communication view."""

    def setUp(self):
        """Define and authenticate test client."""

        # Create authorized user
        user = create_test_user()
        self.client = APIClient()
        self.client.force_authenticate(user=user)
        self.tms = mock_up_TMS(user)
        self.tms.save()

        logging.debug('TMS: {}, id: {}'.format(self.tms, self.tms.id))

    def test_api_can_send_critical_path_email_report(self):
        """Test the api can send an email."""
        path = '/api/critical_paths?tms={}'.format(self.tms.id)
        logging.debug('path={}'.format(path))
        response = self.client.post(
            path,
            {'params': {
                'start_date_field_name': 'customfield_10206',
                'slack_tolerance_for_crit_path_days': 14,
                'final_nodes': ['ED-127', 'ED-132'],
                'jql_query': 'project = "ETAbot-Demo" and status != "Done"'}},
             format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# TODO: Implement test to check that email worker was called with correct arguments.
class UserCommunicationViewTestCase(APITestCase):
    """Test suite for user communication view."""

    def setUp(self):
        """Define and authenticate test client."""

        # Create authorized user
        user = create_test_user()
        self.client = APIClient()
        self.client.force_authenticate(user=user)
        # Create unauthorized user
        self.badClient = APIClient()

    def test_api_can_send_email(self):
        """Test the api can send an email."""
        response = self.client.post('/api/user_communication/', {'subject': 'Email subject', 'body': 'Email body'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_api_can_catch_bad_json(self):
        """Test the api can handle bad input."""
        response = self.client.post('/api/user_communication/', {'subject': 'There is no body'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_can_catch_unauthenticated_user(self):
        """Test the api can handle unauthorized users"""
        response = self.badClient.post('/api/user_communication/', {'subject': 'Email subject', 'body': 'Email body'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TestAtlassianOAuthCallback(APITestCase):
    def setUp(self):
        """Define and authenticate test client."""

        # Create authorized user
        self.user = create_test_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_AtlassianOAuthCallback(self):
        token = {
            'token_type': 'mock type',
            'access_token': 'mock token',
            'refresh_token': 'mock refresh_token',
            'expires_at': 123
        }

        token_item = OAuth2Token(
            owner=self.user,
            name='atlassian',
            token_type=token['token_type'],
            access_token=token['access_token'],
            refresh_token=token['refresh_token'],
            expires_at=token['expires_at'])
        token_item.save()
        # todo: mock apis to test the flow
        # new_tms_ids = AtlassianOAuthCallback.add_update_atlassian_tms(
        #     owner=self.user, token_item=token_item)

        # with patch.object(
        #     AtlassianAPI, 'get_accessible_resources', AtlassianAPI.mock_get_accessible_resources):
        #     new_tms_ids = AtlassianOAuthCallback.add_update_atlassian_tms(
        #         owner=self.user, token_item=token_item)
        # assert len(new_tms_ids) == 1

