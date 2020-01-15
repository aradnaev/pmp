"""Task Management System (TMS) module abstract layer on TMSs (JIRA, Asana,..).

Author: Alex Radnaev (alexander.radnaev@gmail.com)

Status: Prototype

Python Version: 3.6
"""
import logging

logging.debug('loading TMSlib.TMS')
from enum import Enum
import TMSlib.JIRA_API as JIRA_API
logging.debug('loading TMSlib.TMS: loaded JIRA_API')
import sys
import datetime
import user_activation
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


try:
    sys.path.append('etabot_algo/')
    logging.debug(sys.path)
    import etabot_algo.ETApredict as ETApredict
    import etabot_algo.ETAreport as ETAreport
except Exception as e:
    logging.warning('cannot load ETApredict or ETAreport due to "{}"\
 Loading ETApredict_placeholder, ETAreport_placeholder instead'.format(e))
    import TMSlib.ETApredict_placeholder as ETApredict
    import TMSlib.ETAreport_placeholder as ETAreport
logging.debug('loading TMSlib.TMS: done')

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

TMS_TYPES = (
        ('JI', 'JIRA'),
    )


class ProtoTMS():
    """
        TMS = Task Management System
        prototype for any TMS class to standardize critical methods and proprties
    """
    def __init__(self, server_end_point, username_login, task_system_schema):
        self.server_end_point = server_end_point
        self.username_login = username_login
        self.task_system_schema = task_system_schema
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
            self,
            server_end_point,
            username_login,
            task_system_schema):

        if task_system_schema is None:
            task_system_schema = {
                'done_status_values': ['Done'],
                'open_status_values': default_open_status_values
            }

        ProtoTMS.__init__(
            self, server_end_point, username_login, task_system_schema)

        self.jira = None
        logging.debug('TMS_JIRA initalized')

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
                TMSconfig=self.tms_config)
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
            result = "cannot connnect to TMS JIRA due to {}".format(e)
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
                    user_activation.ActivationProcessor.send_email(msg)
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

    def construct_extra_filter(self, project_names=None):
        extra_filter = ' AND type != "Epic" '
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

        extra_filter = project_filter_string
        return extra_filter

    def get_all_done_tasks_ranked(self, assignee=None, project_names=None):
        extra_filter = self.construct_extra_filter(project_names=project_names)
        if self.jira is None:
            raise NameError('not connected to JIRA')

        if assignee is None:
            assignee = 'currentUser()'

        done_issues = self.jira.get_jira_issues(
            'assignee={assignee} AND status in ({done_status_values}) \
ORDER BY Rank ASC'.format(
                assignee=assignee,
                done_status_values=', '.join(
                    ['"{}"'.format(x) for x in self.task_system_schema.get(
                        'done_status_values', ['Done'])])))
        logging.debug('acquired done tasks count: {}'.format(
            len(done_issues)))
        return done_issues

    def prepare_for_get_tasks(self, assignee=None, project_names=None):
        if self.jira is None:
            raise NameError('not connected to JIRA')

        if assignee is None:
            assignee = 'currentUser()'
        extra_filter = self.construct_extra_filter(project_names=project_names)

        return (assignee, extra_filter)

    def get_future_sprints_tasks_ranked(self, assignee=None, project_names=None):
        """Get all open tasks sorted by rank from future sprints.

        Return list of tasks.
        """
        (assignee, extra_filter) = self.prepare_for_get_tasks(
            assignee=assignee, project_names=project_names)

        future_sprints_tasks = self.jira.get_jira_issues(
            'assignee={assignee} AND status != "Done" \
AND sprint in futureSprints() {extra_filter} ORDER BY Rank ASC'.format(
                assignee=assignee, extra_filter=extra_filter))
        return future_sprints_tasks

    def get_all_open_tasks_ranked(self, assignee=None, project_names=None):
        """Get all open tasks sorted by rank.

        Sort buckets:
            In progress open sprint
            open in open sprint
            in progress not open sprint
            open not open sprint
            backlog
        """
        (assignee, extra_filter) = self.prepare_for_get_tasks(
            assignee=assignee, project_names=project_names)

        in_progress_issues_current_sprint = self.jira.get_jira_issues(
            'assignee={assignee} AND status="In Progress" \
AND sprint in openSprints() {extra_filter} ORDER BY Rank ASC'.format(
                assignee=assignee, extra_filter=extra_filter))

        if len(in_progress_issues_current_sprint) > 0:
            logging.debug('task sample')
            logging.debug(in_progress_issues_current_sprint[0])
            logging.debug(in_progress_issues_current_sprint[0].fields.summary)

        open_issues_current_sprint = self.jira.get_jira_issues(
            'assignee={assignee} AND status not in ("In Progress", "Done") \
AND sprint in openSprints() {extra_filter} ORDER BY Rank ASC'.format(
                assignee=assignee,
                extra_filter=extra_filter))

        in_progress_issues = self.jira.get_jira_issues(
            'assignee={assignee} AND status="In Progress" \
AND sprint not in openSprints() {extra_filter} ORDER BY Rank ASC'.format(
                assignee=assignee, extra_filter=extra_filter))

        open_issues = self.jira.get_jira_issues(
            'assignee={assignee} AND status not in ("In Progress", "Done") \
AND sprint not in openSprints() {extra_filter} ORDER BY Rank ASC'.format(
                assignee=assignee,
                extra_filter=extra_filter))

        backlog_issues = self.jira.get_jira_issues(
            'assignee={assignee} AND sprint = null \
{extra_filter} ORDER BY Rank ASC'.format(
                assignee=assignee,
                extra_filter=extra_filter))

        # else:
        #     open_issues_current_sprint = []
        #     open_issues = []

        logging.debug("""acquired open tasks counts:
in_progress_issues_current_sprint: {},
open_issues_current_sprint: {},
in_progress_issues: {},
open_issues: {}
backlog_issues: {}""".format(
                    len(in_progress_issues_current_sprint),
                    len(open_issues_current_sprint),
                    len(in_progress_issues),
                    len(open_issues),
                    len(backlog_issues)))

        return in_progress_issues_current_sprint \
            + open_issues_current_sprint \
            + in_progress_issues \
            + open_issues \
            + backlog_issues


class TMSWrapper(TMS_JIRA):
    def __init__(
            self,
            tms_config,
            projects=None):
        """
        Task Management System Wrapper - generalized TMS to 
        support multiple platforms (JIRA, Asana, Trello, etc)

        Arguments:
            tms_config - Django model of TMS.

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
            logging.debug('initalizing TMS JIRA class')
            cloudid = None
            if tms_config.params is not None:
                cloudid = tms_config.params.get('id')
            if cloudid is not None:
                server = JIRA_API.JIRA_CLOUD_API + cloudid
            else:
                server = tms_config.endpoint
            TMS_JIRA.__init__(
                self,
                server,
                tms_config.username,
                task_system_schema)
            # self.TMS = TMS_JIRA()
        else:
            raise NameError(
                "TMS_type {} is not supported at this time".format(
                    self.TMS_type))

        logging.debug('TMSWrapper initialized with:\n\
server_end_point: {}, username_login: {}'.format(
            self.server_end_point, self.username_login))

    def init_ETApredict(self, projects):
        logging.info('init_ETApredict started')
        self.ETApredict_obj = ETApredict.ETApredict(TMS_interface=self)
        try:
            logging.debug('user_velocity_per_project: {}'.format(
                self.ETApredict_obj.user_velocity_per_project))
        except Exception as e:
            logging.warning('user_velocity_per_project error: {}'.format(e))
        self.ETApredict_obj.init_with_Django_models(self.tms_config, projects)
        logging.info('TMSwrapper: init_ETApredict finished. \
Connectivity status: {}'.format(self.tms_config.connectivity_status))

    def estimate_tasks(self, project_names=None, **kwargs):
        logging.info('Estimating tasks for TMS "{}", \
projects: "{}", hold tight!'.format(self, project_names))
        self.ETApredict_obj.generate_task_list_view_with_ETA(
            project_names, **kwargs)

    def generate_projects_status_report(self):
        """Generate JSON with a report.

        To be reported periodically (e.g. daily) or on demand
        via email, dashboard, Slack, etc.

        """
        report_json = ETAreport.generate_status_report(
            self.ETApredict_obj, **kwargs)
        return report_json
