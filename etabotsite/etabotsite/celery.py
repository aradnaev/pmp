from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab
import logging
import django
from django.db import connections
from django.conf import settings
from django.apps import apps
import datetime
from celery.signals import worker_shutting_down, worker_process_init, worker_process_shutdown

logger = logging.getLogger('celery')
logger.info('celery logger info.')
# Set default Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'etabotsite.settings')
app = Celery('etabotapp')
app.conf.update(
    worker_proc_alive_timeout=60
)
logger.info(f'init app.conf.worker_proc_alive_timeout: {app.conf.worker_proc_alive_timeout} seconds')
app.conf.worker_proc_alive_timeout = 60
logger.info(f'changed app.conf.worker_proc_alive_timeout: {app.conf.worker_proc_alive_timeout} seconds')

def init():
    logger.info('init started.')
    django.setup()
    logger.info(f'before django.conf:settings app.conf.worker_proc_alive_timeout: {app.conf.worker_proc_alive_timeout} seconds')
    app.config_from_object('django.conf:settings')
    logger.info(f'after django.conf:settings app.conf.worker_proc_alive_timeout: {app.conf.worker_proc_alive_timeout} seconds')
    app.conf.update(
        worker_proc_alive_timeout=60
    )
    logger.info(f'after update app.conf.worker_proc_alive_timeout: {app.conf.worker_proc_alive_timeout} seconds')
    # Load tasks from all registered apps
    app.autodiscover_tasks(related_name='django_tasks')
    logger.info(f'after autodiscover_tasks app.conf.worker_proc_alive_timeout: {app.conf.worker_proc_alive_timeout} seconds')
    # Load tasks from all registered apps

    crontab_args = settings.CUSTOM_SETTINGS.get(
        'eta_crontab_args',
        {'hour': 8})  # Midnight Pacific time is 8am UTC

    app.conf.beat_schedule = settings.CUSTOM_SETTINGS.get(
        'eta_beat_schedule',
        {'estimate-at-midnight': {
            'task': 'etabotapp.django_tasks.estimate_all',
            'kwargs': {'task_id': 'periodic_update_{}'.format(
                datetime.datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S'))},
            'schedule': crontab(**crontab_args)
        }})
    logger.info(
        f'after beat_schedule app.conf.worker_proc_alive_timeout: {app.conf.worker_proc_alive_timeout} seconds')
    logger.info('init is done.')

@worker_process_init.connect
def init_worker(**kwargs):
    """
    Initialize worker process with logging setup.
    This runs once per worker process when it starts.
    """
    # Set up logging for this worker process
    logger.info("=" * 50)
    logger.info("Worker process starting up")
    logger.info(f"Process ID: {os.getpid()}")
    logger.info(f"Parent Process ID: {os.getppid()}")

    # Log any additional initialization info
    logger.info("Initializing worker-specific resources...")
    init()

    logger.info("Worker process initialization complete")
    logger.info("=" * 50)


@worker_shutting_down.connect
def worker_shutting_down_handler(sender=None, headers=None, body=None, **kwargs):
    logger.info("=" * 50)
    logger.info(f"Worker {sender} is shutting down - SIGTERM received")


@worker_process_shutdown.connect
def worker_process_shutdown_handler(sender=None, headers=None, body=None, **kwargs):
    logger.info("-" * 50)
    logger.info('worker_process_shutdown')
    logger.info('Shutting down db connections...')
    connections.close_all()
    logger.info('Done shutting down db connections...')
    logger.info('closing connection to broker')
    app.connection().clone()
    logger.info('Done closing connection to broker')
    logger.info("=" * 50)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))

init()
logger.info(f'app.conf.worker_proc_alive_timeout: {app.conf.worker_proc_alive_timeout} seconds')
logging.info('celery.py finished')
