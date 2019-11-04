from unittest.mock import patch

from scrapy.exceptions import NotConfigured
from twisted.internet import reactor
from twisted.internet.defer import DeferredSemaphore

from scrapy_qtwebkit.middleware.cookies import (
    RemotelyAccessibleCookiesMiddleware
)
from scrapy_qtwebkit.middleware.utils import DummySemaphore

from . import MiddlewareTest


class MiddlewareConstructionTest(MiddlewareTest):
    def test_settings_cookies(self):
        mw = self.make_middleware({
            'COOKIES_ENABLED': False,
            'BROWSER_ENGINE_COOKIES_ENABLED': True,
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000'
        })
        assert isinstance(mw.cookies_mw, RemotelyAccessibleCookiesMiddleware)

        mw = self.make_middleware({
            'COOKIES_ENABLED': True,
            'BROWSER_ENGINE_COOKIES_ENABLED': True,
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000'
        })
        assert isinstance(mw.cookies_mw, RemotelyAccessibleCookiesMiddleware)

        mw = self.make_middleware({
            'COOKIES_ENABLED': True,
            'BROWSER_ENGINE_COOKIES_ENABLED': False,
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000'
        })
        assert mw.cookies_mw is None

        mw = self.make_middleware({
            'COOKIES_ENABLED': False,
            'BROWSER_ENGINE_COOKIES_ENABLED': False,
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000'
        })
        assert mw.cookies_mw is None

    def test_settings_cookies_warning(self):
        with patch('scrapy_qtwebkit.middleware.logger') as mock_logger:
            self.make_middleware({
                'COOKIES_ENABLED': True,
                'BROWSER_ENGINE_COOKIES_ENABLED': True,
                'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000'
            })
            assert mock_logger.warning.called

            mock_logger.reset_mock()

            self.make_middleware({
                'COOKIES_ENABLED': False,
                'BROWSER_ENGINE_COOKIES_ENABLED': True,
                'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000'
            })
            assert not mock_logger.warning.called

            mock_logger.reset_mock()

            self.make_middleware({
                'COOKIES_ENABLED': True,
                'BROWSER_ENGINE_COOKIES_ENABLED': False,
                'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000'
            })
            assert not mock_logger.warning.called

    def test_settings_server_missing(self):
        with self.assertRaises(NotConfigured):
            self.make_middleware({})

    def test_settings_server_both(self):
        with self.assertRaises(NotConfigured):
            self.make_middleware({
                'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000',
                'BROWSER_ENGINE_START_SERVER': True
            })

    def test_settings_start_server(self):
        with self.patch_ProcessEndpoint() as mock_ProcessEndpoint:
            mw = self.make_middleware({
                'BROWSER_ENGINE_START_SERVER': True
            })
            assert not self.mock_clientFromString.called
            assert mock_ProcessEndpoint.called
            assert mw._client_endpoint == mock_ProcessEndpoint.return_value

    def test_settings_server(self):
        with self.patch_ProcessEndpoint() as mock_ProcessEndpoint:
            mw = self.make_middleware({
                'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000'
            })

            assert not mock_ProcessEndpoint.called
            self.mock_clientFromString.assert_called_with(reactor,
                                                          'tcp:localhost:8000')
            assert mw._client_endpoint == self.mock_endpoint

    def test_settings_page_limit(self):
        mw = self.make_middleware({
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000',
            'BROWSER_ENGINE_PAGE_LIMIT': 6
        })
        assert isinstance(mw._semaphore, DeferredSemaphore)
        assert mw._semaphore.tokens == 6

        mw = self.make_middleware({
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000',
            'BROWSER_ENGINE_PAGE_LIMIT': 0
        })
        assert isinstance(mw._semaphore, DummySemaphore)

    def test_settings_browser_options(self):
        test_options = {
            'option_one': 'value 1',
            'option_2': 'value two'
        }
        mw = self.make_middleware({
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000',
            'BROWSER_ENGINE_OPTIONS': test_options
        })
        assert mw.browser_options == test_options

    def test_settings_browser_options_none(self):
        mw = self.make_middleware({
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000',
            'BROWSER_ENGINE_OPTIONS': None
        })
        assert mw.browser_options == {}
