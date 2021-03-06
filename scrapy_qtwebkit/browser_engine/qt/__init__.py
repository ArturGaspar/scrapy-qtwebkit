"""Browser process."""

from PyQt5.QtCore import QByteArray, QUrl
from PyQt5.QtNetwork import (QNetworkAccessManager, QNetworkReply,
                             QNetworkRequest)
from PyQt5.QtWebKit import QWebSettings
from PyQt5.QtWebKitWidgets import QWebPage, QWebView
from twisted.internet.defer import inlineCallbacks
from twisted.internet.error import (ConnectError, ConnectingCancelledError,
                                    ConnectionLost, ConnectionRefusedError,
                                    DNSLookupError, SSLError, TimeoutError)
from twisted.spread import pb

from ..._intermediaries import ScrapyNotSupported, RequestFromScrapy
from .http_methods import HTTP_METHOD_TO_QT_OPERATION
from .nam import ScrapyNetworkAccessManager
from .page import CustomQWebPage
from .utils import deferred_for_qt_signal
from .windows import window_types


_qapp = None


def _setup_pre_reactor():
    global _qapp

    import sys

    import qt5reactor
    from PyQt5.QtWidgets import QApplication

    _qapp = QApplication.instance()
    if not _qapp:
        _qapp = QApplication(sys.argv)
    qt5reactor.install()


class Browser(pb.Referenceable):
    def __init__(self, reactor, downloader, global_options):
        super().__init__()
        self._reactor = reactor
        self.downloader = downloader
        self.options = global_options
        QWebSettings.setObjectCacheCapacities(0, 0, 0)
        QWebSettings.setMaximumPagesInCache(0)
        self._windows = None

    def show_window(self, webpage):
        if self._windows is None:
            window_type = self.options.get('window_type', 'simple')
            self._windows = window_types[window_type]()
        webview = QWebView()
        webview.setPage(webpage)
        webpage.webview = webview
        self._windows.add_webview(webview)

    def remove_webview_window(self, webview):
        self._windows.remove_webview(webview)

    def remote_create_webpage(self, options: dict):
        qwebpage = CustomQWebPage()
        nam = ScrapyNetworkAccessManager(self.downloader, parent=qwebpage,
                                         **options)
        qwebpage.setNetworkAccessManager(nam)

        cookiejar = options.get('cookiejar')

        if self.options.get('show_windows', False):
            self.show_window(qwebpage)

        return WebPageRemoteControl(self, qwebpage, cookiejar)


class WebPageRemoteControl(pb.Referenceable):
    def __init__(self, browser: Browser, qwebpage: CustomQWebPage, cookiejar):
        super().__init__()
        self.browser = browser
        self._url = None
        # XXX: nothing else should keep a reference to the webpage.
        self._qwebpage = qwebpage
        self._cookiejar = cookiejar

    def _close(self):
        # Resetting the main frame URL prevents it from making further requests,
        # which would cause Qt errors after the webpage is deleted.
        self._qwebpage.mainFrame().setUrl(QUrl())

        if self._qwebpage.webview is not None:
            self.browser.remove_webview_window(self._qwebpage.webview)
            self._qwebpage.webview.setPage(None)
            self._qwebpage.webview = None

    def __del__(self):
        self._close()

    def remote_close(self):
        self._close()

    @staticmethod
    def _make_qt_request(request: RequestFromScrapy):
        """Build a QNetworkRequest from a RequestFromScrapy object."""
        qt_request = QNetworkRequest(QUrl(request.url))
        for header, values in request.headers.items():
            qt_request.setRawHeader(header, b', '.join(values))

        try:
            operation = HTTP_METHOD_TO_QT_OPERATION[request.method]
        except KeyError:
            operation = QNetworkAccessManager.CustomOperation
            qt_request.setAttribute(QNetworkRequest.CustomVerbAttribute,
                                    request.method)

        qt_request.setAttribute(QNetworkRequest.CacheSaveControlAttribute,
                                False)

        req_body = QByteArray(request.body)

        return qt_request, operation, req_body

    qt_error_exc_mapping = {
        QNetworkReply.ConnectionRefusedError: ConnectionRefusedError,
        QNetworkReply.RemoteHostClosedError: ConnectionLost,
        QNetworkReply.HostNotFoundError: DNSLookupError,
        QNetworkReply.TimeoutError: TimeoutError,
        QNetworkReply.OperationCanceledError: ConnectingCancelledError,
        QNetworkReply.SslHandshakeFailedError: SSLError,
        QNetworkReply.ProtocolUnknownError: ScrapyNotSupported
    }

    @inlineCallbacks
    def remote_load_request(self, request: RequestFromScrapy):
        if self._cookiejar:
            yield self._cookiejar.commit()

        d = deferred_for_qt_signal(self._qwebpage.loadFinishedWithError)
        self._qwebpage.mainFrame().load(*self._make_qt_request(request))

        ok, error = yield d
        exc = None

        self._url = error.url
        if error.domain == QWebPage.Http:
            ok = True
            status = error.error
            headers = getattr(error, 'headers', {})
        else:
            status = None
            headers = None
            if error.domain == QWebPage.QtNetwork:
                exc_cls = self.qt_error_exc_mapping.get(error.error,
                                                        ConnectError)
            else:
                exc_cls = Exception
            exc = exc_cls(error.errorString)

        if self._cookiejar:
            yield self._cookiejar.sync()

        return (ok, status, headers, exc)

    def remote_get_url(self):
        return self._qwebpage.mainFrame().url().toString()

    def remote_get_body(self):
        # TODO: use original page encoding.
        return ('utf-8', self._qwebpage.mainFrame().toHtml().encode('utf-8'))

    def remote_run_script(self, script):
        return self._qwebpage.mainFrame().evaluateJavaScript(script)

    def remote__sync_cookies(self):
        """Ensure all cookie updates were sent to remote."""
        if self._cookiejar:
            return self._cookiejar.sync()

    def remote__commit_cookies(self):
        """Commit all cookie updates received from remote."""
        if self._cookiejar:
            return self._cookiejar.commit()
