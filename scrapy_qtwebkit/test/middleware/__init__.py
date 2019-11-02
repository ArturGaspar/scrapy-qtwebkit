from unittest.mock import patch

from twisted.trial import unittest

from scrapy.crawler import Crawler
from scrapy.settings import Settings
from scrapy.spiders import Spider

from scrapy_qtwebkit.middleware import BrowserMiddleware


class MiddlewareTest(unittest.TestCase):
    def setUp(self):
        self._patcher_clientFromString = patch('scrapy_qtwebkit.middleware.'
                                               'clientFromString')
        self.mock_clientFromString = self._patcher_clientFromString.start()
        self.mock_endpoint = self.mock_clientFromString.return_value

    def tearDown(self):
        self._patcher_clientFromString.stop()

    def patch_ProcessEndpoint(self, *args, **kwargs):
        return patch('scrapy_qtwebkit.middleware.ProcessEndpoint',
                     *args, **kwargs)

    @staticmethod
    def make_middleware(settings_dict):
        settings = Settings(settings_dict)
        return BrowserMiddleware.from_crawler(Crawler(Spider, settings))
