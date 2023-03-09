"""Task Management System (TMS) module abstract layer on TMSs (JIRA, Asana,..).

Author: Alex Radnaev (alexander.radnaev@gmail.com)

Status: Prototype

Python Version: 3.6
"""
import logging

logging.debug('loading TMSlib.TMS')
print('loading TMSlib.TMS')

import etabotapp.TMSlib.JIRA_API as JIRA_API
logging.debug('loading TMSlib.TMS: loaded JIRA_API')
print('loading TMSlib.TMS: loaded JIRA_API')
import sys
import datetime
from typing import List, Dict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import etabotapp.email_toolbox as email_toolbox
# from etabotapp.views import TMS
print('TMS main import complete.')

try:
    sys.path.append('etabot_algo/')
    logging.debug(sys.path)
    import etabot_algo.ETApredict as ETApredict
    import etabot_algo.ETAreport as ETAreport
    import etabot_algo.critical_path as cp
except Exception as e:
    logging.warning('cannot load ETApredict or ETAreport due to "{}"\
 Loading ETApredict_placeholder, ETAreport_placeholder instead'.format(e))
    import etabotapp.TMSlib.ETApredict_placeholder as ETApredict
    import etabotapp.TMSlib.ETAreport_placeholder as ETAreport
    import etabotapp.TMSlib.critical_path_placeholder as cp
logging.debug('loading TMSlib.TMS: done')
print('loading TMSlib.TMS: done')
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

TMS_TYPES = (
        ('JI', 'JIRA'),
    )


class ProtoTMS:
    """
        TMS = Task Management System
        prototype for any TMS class to standardize critical methods and properties
    """
    def __init__(self, server_end_point, username_login, task_system_schema: Dict, logs=None):
        """

        :param server_end_point: TMS API. TMS url is stored in task_system_schema
        :param username_login:
        :param task_system_schema: Dict['tms_url':<user facing tms url>, ...]

        # todo: refactor task_system_schema into a class
        """
        self.server_end_point = server_end_point
        self.username_login = username_login
        self.task_system_schema = task_system_schema
        self.logs = logs
        # self.connectivity_status = None

    def get_projects(self):
        raise NotImplementedError('default get_projects is not implemented')

    def connect_to_TMS(self):
        raise NotImplementedError('default connect_to_TMS is not implemented')

    def get_all_tasks(self, assignee):
        raise NotImplementedError('default get_all_tasks is not implemented')

    def get_all_open_tasks_ranked(self, assignee):
        raise NotImplementedError('default get_all_tasks is not implemented')

    def estimate_tasks(self):
        raise NotImplementedError(
            'default estimate task deadlines is not implemented')

    def generate_projects_status_report(self):
        raise NotImplementedError(
            'generate_projects_status_report is not implemented yet')


class TMS_JIRA(ProtoTMS):

    default_open_status_values = ['Open', 'To Do', 'Selected for Development']

    def __init__(
            self, *,
            server_end_point,
            task_system_schema,
            tms_config,
            logs=None):
        """

        :param server_end_point: api end point
            (same as jira_url for password auth, api.atlassian.net/... for OAuth)
        :param username_login:
        :param task_system_schema:
        :param tms_url: user facing url
        """

        if task_system_schema is None:
            task_system_schema = {
                'done_status_values': ['Done'],
                'open_status_values': self.default_open_status_values
            }

        username_login = tms_config.username
        ProtoTMS.__init__(
            self, server_end_point, username_login, task_system_schema, logs=logs)

        self.jira = None
        self.tms_config = tms_config  # Django TMS object
        self.tms_url = tms_config.endpoint
        logging.debug('TMS_JIRA initialized')

    def connect_to_TMS(self, update_tms=True):
        """Create self.jira object, Return None if connected or error string otherwise.

        TODO: move tms_config - Django model with credentials (password or token)
        from implicit access from child class to init params
        """
        logging.debug('connect_to_TMS started.')
        result = None
        try:
            self.jira = JIRA_API.JIRA_wrapper(
                self.server_end_point,
                self.username_login,
                password=self.tms_config.password,
                TMSconfig=self.tms_config,
                logs=self.logs)
            logging.debug('connect_to_TMS jira object: {}'.format(self.jira))
            self.tms_config.connectivity_status = {
                'status': 'connected',
                'description': 'connectivity last successful connection: {}\
'.format(datetime.datetime.utcnow().isoformat())}
        except Exception as e:
            logging.debug('error in creating JIRA object with \
JIRA_wrapper: {}'.format(e))
            self.tms_config.connectivity_status = {
                'status': 'error',
                'description': 'connectivity issue: {}'.format(e)}
            result = "cannot connect to TMS JIRA due to {}".format(e)
            if update_tms:
                logging.info(
                    'sending email about connectivity issue to: "{}".'.format(
                        self.username_login))
                if self.username_login is not None and '@' in self.username_login:
                    msg = MIMEMultipart()
                    msg['From'] = '"ETAbot" <no-reply@etabot.ai>'
                    msg['To'] = self.username_login  # TODO: user.email
                    msg['Subject'] = 'Account {} needs attention.'.format(
                        self.server_end_point)
                    msg_body = '<html><body><h3>Please log in to https://app.etabot.ai/login \
        and fix credentials for account {}</h3></body></html>'.format(
                        self.server_end_point)
                    msg.attach(MIMEText(msg_body, 'html'))
                    email_toolbox.EmailWorker.send_email(msg)
                else:
                    logging.warning('username is not email - \
cannot send connectivity issue email')
        if update_tms:
            logging.debug('saving connectivity status')
            self.tms_config.save()
            logging.debug('saved connectivity status')
#         if self.tms_config.owner_id:
#             logging.debug('saving connectivity status')
#             self.tms_config.save()
#             logging.debug('saved connectivity status')
#         else:
#             logging.debug('owner_id {} is null - \
# skipping saving connectivity status'.format(self.tms_config.owner_id))
        return result

    @staticmethod
    def construct_extra_filter(
            assignee: str = None,
            project_names: List[str] = None,
            recent_time_period: str = None):
        extra_filter = ' AND (type = "Task" OR type = "Story" OR type = "Bug" OR type = "Epic" OR type = "Initiative") '
        if assignee is not None:
            extra_filter += 'AND assignee = {assignee}'.format(assignee=assignee)

        project_filter_string = ''
        if project_names is not None and len(project_names) > 0:
            project_filter_string = ' AND project in ({})'.format(
                ', '.join(["'{}'".format(p) for p in project_names]))

        # open_status_values = self.task_system_schema.get(
        #         'open_status_values',
        #         self.default_open_status_values)
        # if len(open_status_values) == 0:
        #     open_status_values = self.default_open_status_values
        # open_status_vals_list = [
        #     '"{}"'.format(x)
        #     for x in open_status_values]
        # open_status_values_css = ', '.join(open_status_vals_list)
        extra_filter += project_filter_string
        if recent_time_period is not None:
            extra_filter += ' AND resolutiondate > -{}'.format(
                recent_time_period)

        return extra_filter

    def get_all_done_tasks_ranked(
            self, assignee=None,
            project_names=None,
            recent_time_period: str = None):
        extra_filter = self.construct_extra_filter(
            project_names=project_names,
            assignee=assignee,
            recent_time_period=recent_time_period)
        if self.jira is None:
            raise NameError('not connected to JIRA')

        done_issues = self.jira.get_jira_issues(
            'status in ({done_status_values}) \
{extra_filter} ORDER BY Rank ASC'.format(
                done_status_values=', '.join(
                    ['"{}"'.format(x) for x in self.task_system_schema.get(
                        'done_status_values', ['Done'])]),
                extra_filter=extra_filter))
        logging.debug('acquired done tasks count: {}'.format(
            len(done_issues)))

        return done_issues

    def prepare_for_get_tasks(self, assignee=None, project_names=None):
        if self.jira is None:
            raise NameError('not connected to JIRA')

        extra_filter = self.construct_extra_filter(project_names=project_names, assignee=assignee)

        return extra_filter

    def get_future_sprints_tasks_ranked(self, assignee=None, project_names=None, logs=None):
        """Get all open tasks sorted by rank from future sprints.

        Return list of tasks.
        """
        extra_filter = self.prepare_for_get_tasks(
            assignee=assignee, project_names=project_names)

        jql_query = 'status != "Done" \
AND sprint in futureSprints() {extra_filter} ORDER BY Sprint, Rank ASC'.format(
            extra_filter=extra_filter)
        future_sprints_tasks = self.jira.get_jira_issues(jql_query)
        logging.debug('get_future_sprints_tasks_ranked JQL query: "{}"'.format(jql_query))
        return future_sprints_tasks

    def get_all_open_tasks_ranked(self, assignee=None, project_names=None) -> List:
        """Get all open tasks sorted by rank.

        Sort buckets:
            In progress open sprint
            open in open sprint
            in progress not open sprint
            open not open sprint
            backlog
        """
        result = []
        extra_filter = self.prepare_for_get_tasks(
            assignee=assignee, project_names=project_names)

        in_progress_issues_current_sprint = self.jira.get_jira_issues(
            'status="In Progress" \
AND sprint in openSprints() {extra_filter} ORDER BY Sprint, Rank ASC'.format(
                extra_filter=extra_filter))
        result += in_progress_issues_current_sprint

        if len(in_progress_issues_current_sprint) > 0:
            logging.debug('task sample')
            logging.debug(in_progress_issues_current_sprint[0])
            logging.debug(in_progress_issues_current_sprint[0].fields.summary)

        open_issues_current_sprint = self.jira.get_jira_issues(
            'status not in ("In Progress", "Done") \
AND sprint in openSprints() {extra_filter} ORDER BY Sprint, Rank ASC'.format(
                extra_filter=extra_filter))

        result += open_issues_current_sprint

        open_issues_not_current_sprint = self.jira.get_jira_issues(
            'status not in ("Done") \
AND (sprint not in openSprints() OR sprint is EMPTY) {extra_filter} ORDER BY Sprint, Rank ASC'.format(
                extra_filter=extra_filter))
        result += open_issues_not_current_sprint

        logging.debug("""acquired open tasks counts:
in_progress_issues_current_sprint: {},
open_issues_current_sprint: {},
open_issues_not_current_sprint: {}""".format(
                            len(in_progress_issues_current_sprint),
                            len(open_issues_current_sprint),
                            len(open_issues_not_current_sprint)))
        return result


class TMSWrapper(TMS_JIRA):
    def __init__(
            self,
            tms_config: 'TMS',
            projects=None,
            logs=None):
        """
        Task Management System Wrapper - generalized TMS to
        support multiple platforms (JIRA, Asana, Trello, etc)

        Arguments:
            tms_config - Django model of TMS.
            projects - list of Django model projects to pre-populate open_status_values

        Todo:
            figure out how to subclass from ProtoTMS to
            support multiple TMS types
        """
        logging.debug('initializing TMSWrapper with tms_config "{}", \
projects: {}'.format(tms_config, projects))
        self.tms_config = tms_config
        self.TMS_type = tms_config.type
        logging.debug('tms_config.type: "{}" of type "{}"'.format(
            tms_config.type, type(tms_config.type)))
        self.ETApredict_obj = None
        if logs is None:
            logs = []

        task_system_schema = {}

        if projects is not None:
            open_status_values = []
            for project in projects:
                open_status_values.append(project.open_status)
            task_system_schema['open_status_values'] = list(
                set(open_status_values))
            logging.debug('detected open_status_values: "{}"'.format(
                task_system_schema['open_status_values']))

        logging.debug('allowed TMS types: "{}"'.format(TMS_TYPES))
        if self.TMS_type == TMS_TYPES[0][0]:
            logging.debug('initializing TMS JIRA class')
            cloudid = None
            if tms_config.params is not None:
                cloudid = tms_config.params.get('id')
            else:
                logger.warning('tms_config.params is None')
            if cloudid is not None:
                server = JIRA_API.JIRA_CLOUD_API + cloudid
            else:
                server = tms_config.endpoint
            logger.debug('TMSWrapper set server: {}'.format(server))
            TMS_JIRA.__init__(
                self,
                server_end_point=server,
                tms_config=tms_config,
                task_system_schema=task_system_schema,
                logs=logs)
        else:
            raise NameError(
                "TMS_type {} is not supported at this time".format(
                    self.TMS_type))

        logging.debug('TMSWrapper initialized with:\n\
server_end_point: {}, username_login: {}'.format(
            self.server_end_point, self.username_login))

    def init_ETApredict(self, projects, **kwargs):
        """Initializes ETApredict object: getting tasks, inferring TMS data schema."""
        logging.info('init_ETApredict started with kwargs {}'.format(kwargs))
        self.ETApredict_obj = ETApredict.ETApredict(TMS_interface=self, logs=self.logs)
        try:
            logging.debug('user_velocity_per_project: {}'.format(
                self.ETApredict_obj.eta_engine.user_velocity_per_project))
        except Exception as e:
            logging.warning('user_velocity_per_project error: {}'.format(e))

        self.ETApredict_obj.init_with_Django_models(self.tms_config, projects, **kwargs)

        logging.info('TMSwrapper: init_ETApredict finished. \
Connectivity status: {}'.format(self.tms_config.connectivity_status))
        logging.debug('self.ETApredict_obj.df_tasks_with_ETAs={}'.format(
            self.ETApredict_obj.df_tasks_with_ETAs))

    def estimate_tasks(self, project_names=None, logs=None, **kwargs):
        logging.info('Estimating tasks for TMS "{}", \
projects: "{}", hold tight!'.format(self, project_names))
        self.ETApredict_obj.generate_task_list_view_with_ETA(
            project_names, logs=logs, **kwargs)

    def generate_projects_status_report(self, **kwargs) -> Dict[str, 'HierarchicalReportNode']:
        """Generate list of report objects.

        To be reported periodically (e.g. daily) or on demand
        via email, dashboard, Slack, etc.

        """
        if self.ETApredict_obj.df_tasks_with_ETAs is None:
            logging.warning('self.ETApredict_obj.df_tasks_with_ETAs is None. starting self.estimate_tasks')
            self.estimate_tasks(**kwargs)
        rg = ETAreport.ReportGenerator()
        reports = rg.generate_status_reports(
            self.ETApredict_obj, **kwargs)
        return reports
