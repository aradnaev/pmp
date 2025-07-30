from .models import Project, TMS, CeleryTask
from kombu.utils.uuid import uuid
from django.utils import timezone
import datetime
import functools
import traceback
import logging
import celery as clry
from etabotapp.compression import compress_payload
from .exceptions import TaskFailedError
celery = clry.Celery()
celery.config_from_object('django.conf:settings')

logger = logging.getLogger('django')

def celery_task_record_creator(name, owner):
    unique_task_id = uuid()
    logger.info('celery_task_record_creator started for "{}" with owner "{}"'.format(name, owner))
    celery_task_record = CeleryTask.objects.create(
        task_id=unique_task_id,
        task_name=name,
        start_time=timezone.now(),
        end_time=None,
        status='PN',
        owner=owner,
        meta_data=None
    )
    logger.info('celery_task_record_creator finished for "{}" with owner "{}"'.format(name, owner))
    return celery_task_record


def send_celery_task_with_tracking(name, args, owner=None, compress=False, **kwargs):
    """Create a record for tracking celery task and submit the celery task.
    :param args:
    :param name: celery function name
    :param compress: gzip data to reduce payload size
    :param owner: owner object for the data (ForeignKey in DB)
    :args: tuple of positional arguments to pass to celery.send_task"""
    logger.info('send_celery_task_with_tracking started with owner "{}".'.format(owner))
    celery_task_record = celery_task_record_creator(name=name, owner=owner)
    kwargs['task_id'] = celery_task_record.task_id
    logger.debug('sending celery task {}, {}, {}, {}'.format(name, args, kwargs, celery_task_record.task_id))

    if compress:
        compressed_args = compress_payload(list(args), raise_sqs_max_size_error=True)
        compressed_kwargs = compress_payload(kwargs, raise_sqs_max_size_error=True)
        args_to_send = [compressed_args]
        kwargs_to_send = {'compressed_kwargs': compressed_kwargs}
    else:
        args_to_send = args
        kwargs_to_send = kwargs
    result = celery.send_task(name, args=args_to_send, kwargs=kwargs_to_send, task_id=celery_task_record.task_id)
    return result


def celery_task_update(raise_exceptions: bool = False):
    """Decorator for:
    Updating a job in the database (as CeleryTask) """
    def celery_task_update_with_exception(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            task_id = kwargs.get("task_id")
            error_str = ''
            try:
                logger.debug('celery_task_update decorator is starting celery function. ')
                result = func(*args, **kwargs)
                result_status = 'DN'
                logger.info('Celery task function executed.')
            except Exception as e:
                traceback_str = str(traceback.format_exc())
                logger.error('Celery task {} failed due to "{}"'.format(task_id, e))
                logger.error('Celery task {} failed due to "{}"'.format(task_id, traceback_str))
                error_str = str(e) + traceback_str
                result_status = 'FL'
                result = None

            # End timer
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

            if raise_exceptions and error_str:
                raise TaskFailedError('Celery task {} failed due to "{}"'.format(task_id, error_str))
            return result
        return inner
    return celery_task_update_with_exception