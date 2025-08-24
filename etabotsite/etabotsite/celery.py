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

def init():
    django.setup()

    app.config_from_object('django.conf:settings')
    # Load tasks from all registered apps
    app.autodiscover_tasks(related_name='django_tasks')

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
    logger.info("=" * 50)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))

init()
logging.info('celery.py finished')
