# -*- coding: utf-8 -*-

from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from django.conf import settings


def site_domain():
    return """
var SITE_DOMAIN = '{}';
    """.strip().format(settings.CUSTOM_DYN_SETTING)


def misc_data():
    return 'var MISC_DATA = {a: 100};'
