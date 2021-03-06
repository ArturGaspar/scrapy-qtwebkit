from unittest.mock import patch

from twisted.internet.defer import fail, inlineCallbacks
from twisted.internet.error import ConnectError
from twisted.spread.pb import PBConnectionLost

from . import MiddlewareTest


class MiddlewareInitialisationTest(MiddlewareTest):
    def setUp(self):
        super().setUp()
        self._patcher_PBClientFactory = patch('twisted.spread.pb.'
                                              'PBClientFactory')
        self.mock_factorycls = self._patcher_PBClientFactory.start()
        self.mock_factory = self.mock_factorycls.return_value
        self.mock_root = self.mock_factory.getRootObject.return_value

    def tearDown(self):
        super().tearDown()
        self._patcher_PBClientFactory.stop()

    @inlineCallbacks
    def test_init_browser(self):
        test_options = {
            'foo': 'bar',
            'boo': 'far'
        }

        mw = self.make_middleware({
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000',
            'BROWSER_ENGINE_OPTIONS': test_options
        })

        yield mw._init_browser()

        self.mock_endpoint.connect.assert_called_with(self.mock_factory)

        self.mock_root.callRemote.assert_called_with(
            'open_browser',
            downloader=mw._downloader,
            options=test_options
        )

        mock_browser = self.mock_root.callRemote.return_value
        assert mw._browser == mock_browser

    @inlineCallbacks
    def test_init_browser_connection_failed(self):
        mw = self.make_middleware({
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000',
        })

        self.mock_endpoint.connect.return_value = fail(ConnectError())

        with self.assertRaises(ConnectError):
            yield mw._init_browser()

        assert mw._browser is None

    @inlineCallbacks
    def test_init_browser_connection_lost(self):
        mw = self.make_middleware({
            'BROWSER_ENGINE_SERVER': 'tcp:localhost:8000',
        })

        self.mock_root.callRemote.return_value = fail(PBConnectionLost())

        with self.assertRaises(PBConnectionLost):
            yield mw._init_browser()

        assert mw._browser is None
