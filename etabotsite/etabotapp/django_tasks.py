"""Django tasks for celery."""

from celery import shared_task
import celery as clry
from .models import Project, TMS, CeleryTask
from .models import parse_projects_for_TMS
from django.contrib.auth.models import User
import logging
import etabotapp.eta_tasks as eta_tasks
import datetime
from typing import Union, List
from .celery_tracking import *
from etabotapp import email_toolbox, email_reports
import etabotapp.TMSlib.TMS as TMSlib

celery = clry.Celery()
celery.config_from_object('django.conf:settings')
logger = logging.getLogger('django')


@shared_task
def estimate_all(task_id=None, **kwargs):  # Put kwargs into a decorator
    """Estimate ETA for all tasks for all users."""

    tms_set = TMS.objects.all()
    logger.info('starting generating ETAs for the following TMS entries ({}): {}, task_id={}'.format(
        len(tms_set), tms_set, task_id))
    global_params = {
        'push_updates_to_tms': True
    }
    results = []
    tmss_str = []
    for tms in tms_set:
        projects = Project.objects.all().filter(project_tms_id=tms.id)
        projects_ids = [p.id for p in projects]
        result = send_celery_task_with_tracking(
            'etabotapp.django_tasks.estimate_ETA_for_TMS_project_set_ids',
            (tms.id, projects_ids, global_params),
            owner=tms.owner,
            parent_task_id=task_id)
        logger.info('submitted celery job {} for tms {}, projects {}'.format(result.task_id, tms, projects))
        results.append(result)
        tmss_str.append(str(tms))

    email_toolbox.EmailWorker.send_email(email_toolbox.EmailWorker.format_email_msg(
        'no-reply@etabot.ai', 'hello@etabot.ai', 'sent celery tasks for Qty {} tmss'.format(len(tmss_str)),
        'sent celery tasks for tmss:\n{}'.format('\n'.join(
            ['{} {}'.format(tms_str, result.task_id) for tms_str, result in zip(tmss_str, results)]))))

    return True


def get_tms_by_id(tms_id) -> Union[TMS, None]:
    logger.info('searching for TMS with id: {}'.format(tms_id))
    tms_list = TMS.objects.all().filter(
            pk=tms_id)
    logger.info('found TMSs: {}'.format(tms_list))
    if len(tms_list) > 1:
        raise NameError('TMS id "{}" is not unique'.format(tms_id))
    elif tms_list is None or len(tms_list) == 0:
        logger.warning('no TMS found with id {}'.format(tms_id))
        return None
    else:
        tms = tms_list[0]
    return tms


@shared_task
@celery_task_update
def generate_critical_path(
        tms_id: int,
        final_nodes: List[str],
        params: dict,
        task_id=None):
    """Generate critical path and send email report."""
    logging.info('generate_critical_path started task_id = {}'.format(task_id))
    logging.debug('tms_id = {}, final_nodes="{}", params={}'.format(tms_id, final_nodes, params))
    tms = get_tms_by_id(tms_id)
    logs = []
    tms_wrapper = TMSlib.TMSWrapper(tms, logs=logs)
    email_msg = TMSlib.cp.generate_critical_paths_email_report_for_tms(
        tms_wrapper=tms_wrapper, final_nodes=final_nodes, params=params)
    email_reports.EmailReportProcess.send_email(email_msg)
    logging.info('generate_critical_path finished task_id = {}'.format(task_id))


@shared_task
@celery_task_update
def estimate_ETA_for_TMS_project_set_ids(
        tms_id,
        projects_set_ids,
        params,
        task_id=None,
        parent_task_id=None):
    """Generate ETAs for a given TMS and set of projects."""
    logger.info('estimate_ETA_for_TMS_project_set_ids celery task_id={}, parent_task_id={} started'.format(
        task_id, parent_task_id))
    tms = get_tms_by_id(tms_id)
    if tms is None:
        raise NameError('cannot find TMS with id {}'.format(tms_id))

    projects_set = Project.objects.all().filter(pk__in=projects_set_ids)
    logger.info('found projects_set: {}'.format(projects_set))
    if 'simulate_failure' in params:
        logger.error('Simulating failure: estimate_ETA_for_TMS_project_set_ids')
        raise NameError('Simulating failure')

    eta_tasks.estimate_ETA_for_TMS(tms, projects_set, **params)
    logger.info('estimate_ETA_for_TMS_project_set_ids celery task_id={}, parent_task_id={} finished'.format(
        task_id, parent_task_id))


@shared_task
@celery_task_update
def parse_projects_for_tms_id(
        tms_id,
        params,
        task_id=None):
    """Parse projects for the given TMS id."""
    tms = get_tms_by_id(tms_id)
    if tms is None:
        raise NameError('cannot find TMS with id {}'.format(tms_id))
    result = parse_projects_for_TMS(tms, **params)
    tms.connectivity_status['description'] = '{} Import projects result: {}. \n {}'.format(
        datetime.datetime.utcnow().isoformat(),
        result,
        tms.connectivity_status.get('description', ''))
    tms.save()


@shared_task
@celery_task_update
def send_daily_project_report(task_id=None, **kwargs):
    """Generate Daily Email Reports for all Users"""
    logger.info("Sending Emails to all users for Daily Reports!")
    userlist = User.objects.all()
    for user in userlist:
        tms_list = TMS.objects.all().filter(owner=user)
        logger.debug("TMS: {}".format(len(tms_list)))
        for tms in tms_list:
            project_set = Project.objects.all().filter(project_tms_id=tms.id)
            if project_set:
                eta_tasks.estimate_ETA_for_TMS(tms, project_set, **kwargs)
