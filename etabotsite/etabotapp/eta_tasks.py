"""Collection of tasks for updating ETAs."""

import TMSlib.data_conversion as dc
import TMSlib.TMS as TMSlib
import logging


def estimate_ETA_for_TMS(tms, projects_set, **kwargs):
    """Estimates ETA for a given TMS and projects_set.

    Arguments:
        tms - Django model of TMS. 

    Todo:
    add an option not to refresh velocities
    https://etabot.atlassian.net/browse/ET-521
    """

    logging.debug(
        'estimate_ETA_for_TMS started for TMS {}, projects: {}'.format(
            tms, projects_set))
    tms_wrapper = TMSlib.TMSWrapper(tms)
    tms_wrapper.init_ETApredict(projects_set)
    projects_dict = tms_wrapper.ETApredict_obj.eta_engine.projects
    project_names = []
    for project in projects_set:
        project.velocities = dc.get_velocity_json(
            tms_wrapper.ETApredict_obj.user_velocity_per_project,
            project.name)
        project_settings = projects_dict.get(project.name, {}).get(
                    'project_settings', {})
        logging.debug(
            'project.project_settings {} before update with {}:'.format(
                project.project_settings,
                project_settings))
        project.project_settings = project_settings
        project.save()
        logging.debug('project.project_settings after save: {}'.format(
            project.project_settings))

        project_names.append(project.name)

    tms_wrapper.estimate_tasks(
        project_names=project_names,
        **kwargs)
    logging.debug('estimate_ETA_for_TMS finished')
