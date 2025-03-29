"""purpose: modifies index.html for django template
         by adding static files directives

Author: Alex Radnaev

date created: 2018-05-27

Copyright (C) 2018 Alex Radnaev

"""
import re
import logging


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def html_to_django_template(
        src_html,
        target_html,
        django_static_subpath):

    """src_html - filename with path to process
    target_html - filename with path to write
    django_static_subpath - path within Django static folder

    writes modified file to target_html
    """

    static_prefix = "{{% static '{}".format(django_static_subpath)
    static_suffix = "' %}"

    logging.info('replacing <filename> with pattern: ' + static_prefix +
                 '<filename>' + static_suffix)

    pattern = r'(src="|href=")((?!http)(?!\/).+?)(">)'
    logging.debug('loading: "{}"'.format(src_html))
    with open(src_html) as f:
        s = ''.join(f.readlines())

    s = re.sub(pattern, r'\1{}\2{}\3'.format(static_prefix, static_suffix), s)

    header = '{% load static %}\n'
    logging.info('prepending header: {}'.format(header))
    s = header + s

    with open(target_html, 'w+') as f:
        f.write(s)

    logging.info('{} is created'.format(target_html))
