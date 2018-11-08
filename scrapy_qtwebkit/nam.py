from io import BytesIO

from PyQt5.QtCore import QIODevice, QUrl
from PyQt5.QtNetwork import (QNetworkAccessManager, QNetworkReply,
                             QNetworkRequest)
from scrapy import Request
from scrapy.exceptions import IgnoreRequest, NotSupported
from twisted.internet.defer import fail, maybeDeferred
from twisted.internet.error import (ConnectingCancelledError,
                                    ConnectionAborted, ConnectionLost,
                                    ConnectionRefusedError, DNSLookupError,
                                    SSLError, TCPTimedOutError, TimeoutError,
                                    UnknownHostError)

from . import QT_OPERATION_TO_HTTP_METHOD
from .cookies import ScrapyAwareCookieJar


class ScrapyNetworkAccessManager(QNetworkAccessManager):
    def __init__(self, spider, request, user_agent=None, parent=None):
        super(ScrapyNetworkAccessManager, self).__init__(parent)
        self.spider = spider
        self.request = request
        self.user_agent = user_agent
        self._had_requests = False

    def createRequest(self, operation, request, device=None):
        self.request.actual_requests += 1
        reply = ScrapyNetworkReply(self)
        reply.setRequest(request)
        reply.setOperation(operation)

        method = QT_OPERATION_TO_HTTP_METHOD[operation]
        if method is None:
            method = request.attribute(QNetworkRequest.CustomVerbAttribute)

        request.setHeader(QNetworkRequest.UserAgentHeader, None)
        headers = {bytes(header): bytes(request.rawHeader(header))
                   for header in request.rawHeaderList()
                   # Scrapy will already add Content-Length when it is needed.
                   if header not in {b'Content-Length'}}
        if self.user_agent is not None:
            headers[b'User-Agent'] = self.user_agent

        if device:
            body = bytes(device.readAll())
            reply.uploadProgress.emit(len(body), len(body))
        else:
            body = None

        is_first_request = not self._had_requests
        scrapy_req = Request(request.url().toString(), method=method,
                             headers=headers, body=body,
                             callback=reply.callback, errback=reply.errback,
                             dont_filter=True,
                             meta={'dont_redirect': True,
                                   'handle_httpstatus_all': True,
                                   'from_qtwebkit': True,
                                   'first_webpage_request': is_first_request})
        self._had_requests = True

        cookie_jar = self.cookieJar()
        if isinstance(cookie_jar, ScrapyAwareCookieJar):
            scrapy_req.meta['cookiejar'] = cookie_jar.cookiejarkey
        else:
            scrapy_req.meta['dont_merge_cookies'] = True

        engine = self.spider.crawler.engine

        if not engine.running:
            download = (fail, ConnectionAborted("Scrapy engine stopping"))
        elif self.spider not in engine.open_spiders:
            download = (fail, ConnectionAborted("Spider closed"))
        else:
            download = (engine.download, scrapy_req, self.spider)
        download = maybeDeferred(*download)
        download.addBoth(engine.scraper._scrape, scrapy_req, self.spider)

        return reply


class ScrapyNetworkReply(QNetworkReply):
    """A network reply object for a request made with Scrapy."""

    def __init__(self, nam):
        super(ScrapyNetworkReply, self).__init__(nam)
        self.aborted = False
        self.content = BytesIO()
        self.open(QIODevice.ReadOnly)

    def callback(self, response):
        """Finish the Qt network reply with a Scrapy response."""
        if self.aborted:
            return

        if response.status in {301, 302, 303, 307}:
            location = response.headers.get('Location')
            if location:
                self.setAttribute(QNetworkRequest.RedirectionTargetAttribute,
                                  QUrl(location))

        self.setUrl(QUrl(response.url))
        self.setAttribute(QNetworkRequest.HttpStatusCodeAttribute,
                          response.status)
        for header, values in response.headers.items():
            self.setRawHeader(header, b', '.join(values))
        self.content.write(response.body)
        self.content.seek(0)
        self.downloadProgress.emit(len(response.body), len(response.body))

        self.readyRead.emit()
        self.finished.emit()

    def errback(self, failure):
        """Finish the Qt network reply with an error from Scrapy."""
        if self.aborted:
            return

        error_message = failure.getErrorMessage()

        if failure.check(ConnectionRefusedError):
            error_code = QNetworkReply.ConnectionRefusedError
        elif failure.check(ConnectionLost):
            error_code = QNetworkReply.RemoteHostClosedError
        elif failure.check(DNSLookupError, UnknownHostError):
            error_code = QNetworkReply.HostNotFoundError
            if failure.check(DNSLookupError):
                error_message = ' '.join(failure.value.args)
        elif failure.check(TCPTimedOutError, TimeoutError):
            error_code = QNetworkReply.TimeoutError
        elif failure.check(ConnectingCancelledError, ConnectionAborted,
                           IgnoreRequest):
            error_code = QNetworkReply.OperationCanceledError
        elif failure.check(SSLError):
            error_code = QNetworkReply.SslHandshakeFailedError
        elif failure.check(NotSupported):
            error_code = QNetworkReply.ProtocolUnknownError
        else:
            error_code = QNetworkReply.UnknownNetworkError

        self.setError(error_code, error_message)
        self.error.emit(error_code)
        self.finished.emit()

        return failure

    def bytesAvailable(self):
        return super(ScrapyNetworkReply, self).bytesAvailable() + (len(self.content.getvalue()) - self.content.tell())

    def readData(self, size):
        return self.content.read(size)

    def abort(self):
        self.aborted = True
        self.close()
        self.setError(QNetworkReply.OperationCanceledError, "")
        self.error.emit(QNetworkReply.OperationCanceledError)
        self.finished.emit()
