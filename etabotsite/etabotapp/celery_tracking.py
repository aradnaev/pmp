import traceback

from .models import Project, TMS, CeleryTask
from kombu.utils.uuid import uuid
import datetime
import functools
from .views import *
import logging
import celery as clry
celery = clry.Celery()
celery.config_from_object('django.conf:settings')

logger = logging.getLogger('django')


def celery_task_record_creator(name, owner):
    unique_task_id = uuid()
    logger.info('celery_task_record_creator started for "{}" with owner "{}"'.format(name, owner))
    celery_task_record = CeleryTask.objects.create(
        task_id=unique_task_id,
        task_name=name,
        start_time=datetime.datetime.now(),
        end_time=None,
        status='PN',
        owner=owner,
        meta_data=None
    )

    return celery_task_record


def send_celery_task_with_tracking(name, args, owner=None, **kwargs):
    """Create a record for tracking celery task and submit the celery task.

    :args: tuple of positional arguments to ass to celery.send_task"""
    logger.info('send_celery_task_with_tracking started with owner "{}".'.format(owner))
    celery_task_record = celery_task_record_creator(name=name, owner=owner)
    kwargs['task_id'] = celery_task_record.task_id
    logger.debug('sending celery task {}, {}, {}, {}'.format(name, args, kwargs, celery_task_record.task_id))
    result = celery.send_task(name, args=args, kwargs=kwargs, task_id=celery_task_record.task_id)
    return result


def celery_task_update(func):
    """Decorator for:
    Updating a job in the database (as CeleryTask) """
    @functools.wraps(func)
    def inner(*args, **kwargs):
        error_str = None
        try:
            logger.debug('celery_task_update decorator is starting celery function. ')
            result = func(*args, **kwargs)
            result_status = 'DN'
            logger.info('Celery task function executed.')
        except Exception as e:
            logger.error('Celery task failed due to "{}". '.format(e))
            error_str = str(e) + str(traceback.format_exc())
            result_status = 'FL'
            result = None

        # End timer
        task_id = kwargs.get("task_id")
        if task_id is not None:
            celery_task_records = CeleryTask.objects.all().filter(pk=task_id)
            if len(celery_task_records) == 1:
                celery_task_record = celery_task_records[0]
                celery_task_record.end_time = datetime.datetime.now()
                celery_task_record.status = result_status
                meta_data = celery_task_record.meta_data
                if meta_data is None:
                    meta_data = {}
                meta_data['error_str'] = error_str
                celery_task_record.meta_data = meta_data
                celery_task_record.save()
                logger.info('updated celery task_id={} with status={}'.format(task_id, result_status))
            else:
                logger.error('not unique celery_task_record found, length={}'.format(len(celery_task_records)))
        else:
            logger.warning('no celery task id passed for tracking.')
        return result

    return inner

