"""
Author: Chad Lewis
September 2020

This script handles the email logger for email admins.

We are required to repeat the email_toolbox to ensure that it can be used
without a looping import.
"""

import base64
import logging
import smtplib
import time

from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum

logger = logging.getLogger('django')


class EmailAlertWorker(object):
    @staticmethod
    def send_email(msg, EMAIL_HOST, EMAIL_PORT, SYS_EMAIL, SYS_EMAIL_PWD):
        try:
            logger.debug('starting send_email.')
            server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
            server.set_debuglevel(1)
            server.ehlo()
            server.starttls()
            server.login(SYS_EMAIL, SYS_EMAIL_PWD)

            server.send_message(msg)
            del server

            logger.info('Successfully sent email')
        except Exception as ex:
            logger.error('Failed to send email')

    @staticmethod
    def format_email_msg(
            from_field,
            to_field,
            subject_field,
            msg_body):

        msg = MIMEMultipart()
        msg['From'] = from_field
        msg['To'] = to_field
        msg['Subject'] = subject_field
        msg_body = msg_body
        msg.attach(MIMEText(msg_body, 'html'))
        return msg


class SendEmailAlert(logging.Handler):
    """ Send Email Alerts on Errors and above

        SendEmailAlert is a subclass of logging.Handler
        It is used in the custom logger outlined in settings.py
        It will use the EmailAlertWorker to send emails to listed admins.

        All variables are defined in custom_settings.json.
    """
    def __init__(
            self, SYS_DOMAIN,
            SYS_EMAIL,
            SYS_EMAIL_PWD,
            EMAIL_HOST,
            EMAIL_PORT,
            ADMINS,
            alertWorker=EmailAlertWorker()):
        logging.Handler.__init__(self)
        self.SYS_DOMAIN = SYS_DOMAIN
        self.SYS_EMAIL = SYS_EMAIL
        self.SYS_EMAIL_PWD = SYS_EMAIL_PWD
        self.EMAIL_HOST = EMAIL_HOST
        self.EMAIL_PORT = EMAIL_PORT
        self.ADMINS = ADMINS
        self._emailAlertWorker = alertWorker
        self.email_from = '"ETAbot" <no-reply@etabot.ai>'
        self.email_subject = "Email Alert for Django Error"

    def emit(self, record):
        """This method is called automatically when handling a log"""
        try:
            for emailTo in self.ADMINS:
                msg = self._emailAlertWorker.format_email_msg(
                    self.email_from, emailTo, self.email_subject, self.format(record))
                self._emailAlertWorker.send_email(
                    msg, self.EMAIL_HOST, self.EMAIL_PORT, self.SYS_EMAIL, self.SYS_EMAIL_PWD)
        except Exception as e:
            # Log the error but don't let it break the logging system
            import sys
            sys.stderr.write(f'Failed to send admin email alert: {e}\n')
