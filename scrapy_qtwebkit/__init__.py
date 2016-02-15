import weakref
from functools import partial

from scrapy import signals
from scrapy.downloadermiddlewares.cookies import CookiesMiddleware
from scrapy.exceptions import NotSupported
from scrapy.http import HtmlResponse, Request
from scrapy.utils.misc import arg_to_iter
from twisted.internet.task import LoopingCall
from twisted.internet.defer import (DeferredSemaphore, inlineCallbacks,
                                    maybeDeferred, returnValue, succeed)
from twisted.internet.error import (ConnectError, ConnectingCancelledError,
                                    ConnectionLost, ConnectionRefusedError,
                                    DNSLookupError, SSLError, TimeoutError)
from twisted.python.failure import Failure

from .qt.QtCore import QByteArray, QUrl
from .qt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from .qt.QtWidgets import QApplication, QMdiArea
from .qt.QtWebKit import QWebSettings
from .qt.QtWebKitWidgets import QWebPage, QWebView

from .cookies import ScrapyAwareCookieJar
from .utils import deferred_for_signal


__all__ = ['QtWebKitMiddleware', 'QtWebKitRequest']


HTTP_METHOD_TO_QT_OPERATION = {"HEAD": QNetworkAccessManager.HeadOperation,
                               "GET": QNetworkAccessManager.GetOperation,
                               "PUT": QNetworkAccessManager.PutOperation,
                               "POST": QNetworkAccessManager.PostOperation,
                               "DELETE": QNetworkAccessManager.DeleteOperation}

QT_OPERATION_TO_HTTP_METHOD = dict(map(reversed,
                                       HTTP_METHOD_TO_QT_OPERATION.items()))
QT_OPERATION_TO_HTTP_METHOD[QNetworkAccessManager.CustomOperation] = None


from .nam import ScrapyNetworkAccessManager
from .page import WebPage


class DummySemaphore(object):
    def acquire(self):
        return succeed(self)

    def release(self):
        pass


class QtWebKitRequest(Request):
    """

    A request to be handled by Qt WebKit. May be provided either an URL to
    open a new webpage for, or an existing webpage to continue with.

    """

    def __init__(self, url=None, webpage=None, *args, **kwargs):
        if webpage:
            if url:
                raise TypeError("must not provide both url and webpage")
            url = "about:blank"
        elif not url:
            raise TypeError("must provide either url or webpage")
        self.webpage = webpage
        # kwargs.setdefault('dont_filter', True)
        self.actual_requests = 0
        super(QtWebKitRequest, self).__init__(url, *args, **kwargs)

    def __repr__(self):
        return ("<Qt WebKit page {} (with {} requests)>"
                ).format(self.url, self.actual_requests)

    def __str__(self):
        return repr(self)

    def replace(self, *args, **kwargs):
        webpage = kwargs.setdefault('webpage', self.webpage)
        if webpage is not None:
            kwargs['url'] = None

        return super(QtWebKitRequest, self).replace(*args, **kwargs)


class _QApplicationStopper(object):
    def __init__(self, signal_manager, app):
        super(_QApplicationStopper, self).__init__()
        self._qapplication = weakref.ref(app)
        self.signals = signal_manager
        self.signals.connect(self, signal=signals.engine_stopped, weak=False)

    def __call__(self):
        self.signals.disconnect(self, signals.engine_stopped)
        app = self._qapplication()
        if app is not None:
            app.quit()


class BaseQtWebKitMiddleware(object):
    nam_cls = ScrapyNetworkAccessManager

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings

        if crawler.settings.getbool('QTWEBKIT_COOKIES_ENABLED', False):
            cookies_middleware = CookiesMiddleware(
                crawler.settings.getbool('COOKIES_DEBUG')
            )
        else:
            cookies_middleware = None

        qt_platform = settings.get("QTWEBKIT_QT_PLATFORM", "minimal")
        if qt_platform == "default":
            qt_platform = None

        ext = cls(
            crawler,
            show_window=settings.getbool("QTWEBKIT_SHOW_WINDOW", False),
            qt_platform=qt_platform,
            enable_webkit_dev_tools=settings.get("QTWEBKIT_ENABLE_DEV_TOOLS",
                                                 False),
            page_limit=settings.getint("QTWEBKIT_PAGE_LIMIT", 4),
            cookies_middleware=cookies_middleware
        )

        return ext

    @staticmethod
    def engine_stopped():
        if QApplication.instance():
            QApplication.instance().quit()

    def __init__(self, crawler, show_window=False, qt_platform="minimal",
                 enable_webkit_dev_tools=False, page_limit=4,
                 cookies_middleware=None):
        super(BaseQtWebKitMiddleware, self).__init__()
        self._crawler = crawler
        self.show_window = show_window
        self.qt_platform = qt_platform
        self.enable_webkit_dev_tools = enable_webkit_dev_tools
        if page_limit != 1:
            if QWebSettings is not None:
                QWebSettings.setObjectCacheCapacities(0, 0, 0)
        if page_limit is None:
            self.semaphore = DummySemaphore()
        else:
            self.semaphore = DeferredSemaphore(page_limit)
        self.cookies_middleware = cookies_middleware
        self._references = set()

    @staticmethod
    def _schedule_qt_event_loop(app):
        """

        Schedule a QApplication's event loop within Twisted. Should be called
        at most once per QApplication.

        """
        # XXX: This is ugly but I don't know another way to do it.
        call = LoopingCall(app.processEvents)
        call.start(0.02, False)
        app.aboutToQuit.connect(call.stop)

    def _setup_page(self, page, extra_settings):
        settings = page.settings()
        settings.setAttribute(QWebSettings.JavaEnabled, False)
        settings.setAttribute(QWebSettings.PluginsEnabled, False)
        settings.setAttribute(QWebSettings.PrivateBrowsingEnabled, True)
        settings.setAttribute(QWebSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebSettings.LocalContentCanAccessRemoteUrls,
                              True)
        settings.setAttribute(QWebSettings.LocalContentCanAccessFileUrls,
                              True)
        settings.setAttribute(QWebSettings.NotificationsEnabled, False)

        settings.setAttribute(QWebSettings.DeveloperExtrasEnabled,
                              self.enable_webkit_dev_tools)

        for setting, value in extra_settings.items():
            settings.setAttribute(setting, value)

    @staticmethod
    def _make_qt_request(scrapy_request):
        """Build a QNetworkRequest from a Scrapy request."""

        qt_request = QNetworkRequest(QUrl(scrapy_request.url))
        for header, values in scrapy_request.headers.items():
            qt_request.setRawHeader(header, b', '.join(values))

        try:
            operation = HTTP_METHOD_TO_QT_OPERATION[scrapy_request.method]
        except KeyError:
            operation = QNetworkAccessManager.CustomOperation
            qt_request.setAttribute(QNetworkRequest.CustomVerbAttribute,
                                    scrapy_request.method)

        qt_request.setAttribute(QNetworkRequest.CacheSaveControlAttribute,
                                False)

        req_body = QByteArray(scrapy_request.body)

        return qt_request, operation, req_body

    @inlineCallbacks
    def process_request(self, request, spider):
        if self.cookies_middleware:
            yield self.cookies_middleware.process_request(request, spider)

        if isinstance(request, QtWebKitRequest):
            if request.webpage:
                # Request is to continue processing with an existing webpage
                # object.
                webpage = request.webpage
                request = request.replace(webpage=None)
                webpage.networkAccessManager().request = request
                returnValue(self._handle_page_request(spider, request,
                                                      webpage))
            else:
                yield self.semaphore.acquire()
                response = yield self.create_page(request, spider)
                returnValue(response)

    def process_response(self, request, response, spider):
        if self.cookies_middleware:
            return self.cookies_middleware.process_response(request, response,
                                                            spider)
        else:
            return response

    def ensure_qapplication(self):
        """Create and setup a QApplication if one does not already exist."""
        if not QApplication.instance():
            args = ["scrapy"]
            if self.qt_platform is not None:
                args.extend(["-platform", self.qt_platform])
            app = QApplication(args)
            self._schedule_qt_event_loop(app)
            _QApplicationStopper(self._crawler.signals, app)

    def create_page(self, request, spider):
        """

        Create a webpage object, load a request on it, return a deferred that
        fires with a response on page load.

        """

        self.ensure_qapplication()

        webpage = WebPage()
        self._setup_page(webpage,
                         request.meta.get('qwebsettings_settings', {}))
        self._references.add(webpage)

        if self.show_window:
            webview = QWebView()
            webview.setPage(webpage)
            webpage.webview = webview
            self._add_webview_to_window(webview, spider.name)

        if request.meta.get('qtwebkit_user_agent', False):
            request.headers['User-Agent'] = webpage.userAgentForUrl(
                QUrl(request.url)
            )

        nam = self.nam_cls(spider, request, request.headers.get('User-Agent'),
                           parent=webpage)
        if ((self.cookies_middleware and
             'dont_merge_cookies' not in request.meta)):
            cookiejarkey = request.meta.get("cookiejar")
            cookiejar = ScrapyAwareCookieJar(self.cookies_middleware,
                                             cookiejarkey, parent=nam)
            nam.setCookieJar(cookiejar)
        webpage.setNetworkAccessManager(nam)

        d = deferred_for_signal(webpage.load_finished_with_error)
        d.addCallback(partial(self._handle_page_request, spider, request,
                              webpage))
        webpage.mainFrame().load(*self._make_qt_request(request))
        return d

    def _add_webview_to_window(self, webview, title=""):
        pass

    def _remove_webview_from_window(self, webview):
        pass

    def _handle_page_request(self, spider, request, webpage,
                             load_result=(True, None)):
        """

        Handle a request for a web page, either a page load or a request to
        continue using an existing page object.

        """

        try:
            ok, error = load_result

            if ok:
                # The error object is not available if a page load was not
                # requested.
                if error and error.domain == QWebPage.Http:
                    status = error.error
                else:
                    status = 200
                if error:
                    url = error.url
                else:
                    url = webpage.mainFrame().url()

                response = HtmlResponse(status=status,
                                        url=url.toString(),
                                        headers=error.headers,
                                        body=webpage.mainFrame().toHtml(),
                                        encoding='utf-8',
                                        request=request)

                if request.meta.get('qwebpage_response', False):
                    response.webpage = webpage
                    request.callback = partial(self._request_callback, spider,
                                               request.callback or 'parse')
                else:
                    self._close_page(webpage)

            else:
                raise self._exception_from_errorpageextensionoption(error)

        except Exception as err:
            response = Failure(err)

        return response

    @inlineCallbacks
    def _request_callback(self, spider, original_callback, response):
        """

        Close the page (lose the reference to it so it is garbage collected)
        when the callback returns.

        The original callback may prevent page closing by setting the
        should_close_webpage attribute in responses. This is useful for
        example if the page is stored somewhere else (e.g. request meta) to be
        used later. The page then needs to be closed manually at some point by
        calling its close_page() function, which is created here.

        """

        if isinstance(original_callback, basestring):
            original_callback = getattr(spider, original_callback)

        webpage = response.webpage
        response.should_close_webpage = True
        try:
            returnValue(arg_to_iter((yield maybeDeferred(original_callback,
                                                         response))))
        finally:
            if response.should_close_webpage:
                self._close_page(webpage)
            else:
                webpage.close_page = partial(self._close_page, webpage)
                webpage.close_page.__doc__ = ("Lose the reference to the "
                                              "webpage object and allow it "
                                              "to be garbage collected.")

    def _close_page(self, webpage):
        self._references.remove(webpage)
        # Resetting the main frame URL prevents it from making any more
        # requests, which would cause Qt errors after the webpage is deleted.
        webpage.mainFrame().setUrl(QUrl())
        if webpage.webview is not None:
            self._remove_webview_from_window(webpage.webview)
        self.semaphore.release()

    _qt_error_exc_mapping = {
        QNetworkReply.ConnectionRefusedError: ConnectionRefusedError,
        QNetworkReply.RemoteHostClosedError: ConnectionLost,
        QNetworkReply.HostNotFoundError: DNSLookupError,
        QNetworkReply.TimeoutError: TimeoutError,
        QNetworkReply.OperationCanceledError: ConnectingCancelledError,
        QNetworkReply.SslHandshakeFailedError: SSLError,
        QNetworkReply.ProtocolUnknownError: NotSupported
    }

    def _exception_from_errorpageextensionoption(self, option):
        if option.domain == QWebPage.QtNetwork:
            exc_cls = self._qt_error_exc_mapping.get(option.error,
                                                     ConnectError)
        # elif option.domain == QWebPage.WebKit:
        #     exc_cls = Exception
        else:
            exc_cls = Exception

        return exc_cls(option.errorString)


class MdiAreaQtWebKitMiddleware(BaseQtWebKitMiddleware):
    def __init__(self, *args, **kwargs):
        super(MdiAreaQtWebKitMiddleware, self).__init__(*args, **kwargs)
        self._mdi_area = None

    def _add_webview_to_window(self, webview, title=""):
        if self._mdi_area is None:
            self._mdi_area = QMdiArea()
            self._mdi_area.resize(1024, 768)
            self._mdi_area.setWindowTitle(title)
            self._mdi_area.show()
        subwindow = self._mdi_area.addSubWindow(webview)
        webview.titleChanged.connect(subwindow.setWindowTitle)
        subwindow.show()
        self._mdi_area.tileSubWindows()

    def _remove_webview_from_window(self, webview):
        subwindow = webview.parentWidget()
        webview.close()
        self._mdi_area.removeSubWindow(subwindow)
        self._mdi_area.tileSubWindows()


QtWebKitMiddleware = MdiAreaQtWebKitMiddleware
