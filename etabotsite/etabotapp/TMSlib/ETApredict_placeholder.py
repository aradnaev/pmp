"""ETApredict placeholder."""
# uncomment for syntax error for ensuring placeholder is not used 

import logging
import time
# import TMSlib.TMS_project as TMS_project

class Measurement():
    def __init__(self, value):
        self.value = value

    def lower_estimate(self, confidence_level=0.95):
        return self.value / 1.2

    def higher_estimate(self, confidence_level=0.95):
        return self.value * 1.2


class ETAengine:
    def __init__(self):
        self.projects = {}
        self.user_velocity_per_project = {}


class ETApredict:
    def __init__(
            self,
            TMS_interface=None,
            logs=None):
        self.TMS_interface = TMS_interface
        if logs is None:
            self.logs = []
        else:
            self.logs = logs
        self.eta_engine = ETAengine()
        self.df_tasks_with_ETAs = None
        self.task_system_schema = {'projects': {}}
        logging.debug('ETApredict placeholder initialized')

    def init_with_Django_models(
            self,
            tms_config,
            projects,
            **kwargs):
        if projects is not None and len(projects) > 0:
            self.projects = projects
        else:
            self.get_projects()

    def generate_task_list_view_with_ETA(
            self,
            project_names=None,
            include_active_sprints=False,
            **extra_kwargs):
        self.TMS_interface.connect_to_TMS()
        time.sleep(5)
        logging.info('placeholder ETAs have been generated')

    def get_projects(self):
        logging.debug('get_projects started')
        self.TMS_interface.connect_to_TMS()

        self.eta_engine.projects['Project Buckwheat'] = {}
        self.eta_engine.projects['Project Buckwheat']['work_hours'] = {
                "Monday": [

                    {"end": 21, "start": 19}

                ],

                "Thursday": [

                    {"end": 21, "start": 19}

                ],

                "Time Zone": "GMT +8",

                "Tuesday": [

                    {"end": 21, "start": 19}

                ],
                "Wednesday": [

                    {"end": 20, "start": 19},
                    {"end": 23, "start": 22}

                ]}

        self.eta_engine.projects['Project Buckwheat']['mode'] = 'Scrum'
        self.eta_engine.projects['Project Buckwheat']['open_status'] = 'To Do'
        self.eta_engine.projects['Project Buckwheat']['grace_period'] = 4.0
        self.eta_engine.projects['Project Buckwheat']['vacation_days'] = [

            {"start": "2017-04-01", "end": "2017-05-02"},
            {"start": "2018-07-01", "end": "2018-07-02"},
            {"start": "2018-09-14", "end": "2018-09-21"}

        ]
        self.eta_engine.projects['Project Cheburashka'] = {}
        self.eta_engine.projects['Project Cheburashka']['work_hours'] = {
                "Sunday": [

                    {"end": 15, "start": 13}

                ],

                "Saturday": [

                    {"end": 15, "start": 13}

                ],

                "Time Zone": "GMT +7",

                }

        self.eta_engine.projects['Project Cheburashka']['mode'] = 'Kanban'
        self.eta_engine.projects['Project Cheburashka']['open_status'] = 'To Do'
        self.eta_engine.projects['Project Cheburashka']['grace_period'] = 8.0
        self.eta_engine.projects['Project Cheburashka']['vacation_days'] = [

            {"start": "2017-04-01", "end": "2017-05-02"},
            {"start": "2018-07-01", "end": "2018-07-02"},
            {"start": "2018-09-14", "end": "2018-09-21"}

        ]

        self.eta_engine.user_velocity_per_project = {
            'Project Cheburashka': Measurement(1.2),
            'Project Buckwheat': Measurement(2.3)
        }

        logging.debug('get_projects finished')
