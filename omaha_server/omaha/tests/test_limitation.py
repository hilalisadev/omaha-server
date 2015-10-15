# coding: utf8

"""
This software is licensed under the Apache 2 license, quoted below.

Copyright 2014 Crystalnix Limited

Licensed under the Apache License, Version 2.0 (the "License"); you may not
use this file except in compliance with the License. You may obtain a copy of
the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations under
the License.
"""

from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.cache import cache

import moto

from crash.factories import CrashFactory
from feedback.factories import FeedbackFactory
from omaha.dynamic_preferences_registry import global_preferences_manager as gpm
from omaha.limitation import delete_older_than, delete_size_is_exceeded, delete_duplicate_crashes
from omaha.limitation import monitoring_size
from omaha_server.utils import is_private
from crash.models import Crash, Symbols
from feedback.models import Feedback

from omaha.factories import VersionFactory
from sparkle.factories import SparkleVersionFactory

class DeleteOldTest(TestCase):
    @is_private()
    def test_crashes(self):
        old_date = timezone.now() - timezone.timedelta(days=5)
        gpm['Crash__limit_storage_days'] = 2
        CrashFactory.create_batch(10, created=old_date)
        Crash.objects.update(created=old_date)
        self.assertEqual(Crash.objects.all().count(), 10)
        delete_older_than('crash', 'Crash')
        self.assertEqual(Crash.objects.all().count(), 0)

    @is_private()
    def test_feedbacks(self):
        old_date = timezone.now() - timezone.timedelta(days=5)
        gpm['Feedback__limit_storage_days'] = 2
        FeedbackFactory.create_batch(10, created=old_date)
        Feedback.objects.update(created=old_date)
        self.assertEqual(Feedback.objects.all().count(), 10)
        delete_older_than('feedback', 'Feedback')
        self.assertEqual(Feedback.objects.all().count(), 0)


class SizeExceedTest(TestCase):
    @is_private()
    def test_crashes(self):
        gpm['Crash__limit_size'] = 1
        Crash.objects.bulk_create([Crash(archive_size=10*1024*1023, minidump_size=0) for x in range(500)])
        self.assertEqual(Crash.objects.all().count(), 500)
        delete_size_is_exceeded('crash', 'Crash')
        self.assertEqual(Crash.objects.all().count(), 102)

    @is_private()
    def test_feedbacks(self):
        gpm['Feedback__limit_size'] = 1
        FeedbackFactory.create_batch(500, screenshot_size=10*1024*1023, system_logs_size=0, attached_file_size=0, blackbox_size=0)
        self.assertEqual(Feedback.objects.all().count(), 500)
        delete_size_is_exceeded('feedback', 'Feedback')
        self.assertEqual(Feedback.objects.all().count(), 102)


class DeleteDuplicateTest(TestCase):
    @is_private()
    def test_crashes(self):
        gpm['Crash__duplicate_number'] = 10
        CrashFactory.create_batch(20, signature='test1')
        self.assertEqual(Crash.objects.filter(signature='test1').count(), 20)
        CrashFactory.create_batch(9, signature='test2')
        self.assertEqual(Crash.objects.filter(signature='test2').count(), 9)
        delete_duplicate_crashes()
        self.assertEqual(Crash.objects.filter(signature='test1').count(), gpm['Crash__duplicate_number'])
        self.assertEqual(Crash.objects.filter(signature='test2').count(), 9)


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
})
class MonitoringTest(TestCase):
    cache_keys = ['omaha_version_size', 'sparkle_version_size', 'crashes_size', 'feedbacks_size', 'symbols_size']

    def setUp(self):
        for key in self.cache_keys:
            cache.delete(key)

    @is_private()
    def test_monitoring(self):
        for key in self.cache_keys:
            self.assertEqual(cache.get(key, 0), 0)

        VersionFactory.create(file_size=100)
        SparkleVersionFactory.create(file_size=100)
        Crash.objects.create(archive_size=80, minidump_size=20)
        Symbols.objects.create(file_size=100)
        Feedback.objects.create(screenshot_size=25, blackbox_size=25, attached_file_size=25, system_logs_size=25)

        monitoring_size()

        for key in self.cache_keys:
            self.assertEqual(cache.get(key), 100)