import misc_utils.ng2plus_dist2django as ng2django
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

ng2django.deploy_ng2plus(
    os.environ['ETABOT_UI_PATH'],
    'static',
    '../templates',
    'ng2_app/')
