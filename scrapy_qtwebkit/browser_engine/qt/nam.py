from io import BytesIO

from PyQt5.QtCore import QIODevice, QUrl
from PyQt5.QtNetwork import (QNetworkAccessManager, QNetworkReply,
                             QNetworkRequest)

from twisted.internet.error import (ConnectingCancelledError,
                                    ConnectionAborted, ConnectionLost,
                                    ConnectionRefusedError, DNSLookupError,
                                    SSLError, TCPTimedOutError, TimeoutError,
                                    UnknownHostError)

from ..._intermediaries import (RequestFromBrowser, ScrapyIgnoreRequest,
                                ScrapyNotSupported)
from .cookiejar import CookielibQtCookieJar
from .http_methods import QT_OPERATION_TO_HTTP_METHOD


class ScrapyNetworkAccessManager(QNetworkAccessManager):
    def __init__(self, remote_downloader, user_agent=None,
                 remote_request_counter=None, cookiejarkey=None,
                 cookiejar=None, parent=None):
        super().__init__(parent)
        self.remote_downloader = remote_downloader
        self.user_agent = user_agent
        self.remote_request_counter = remote_request_counter
        self.cookiejarkey = cookiejarkey
        if cookiejar is not None:
            self.setCookieJar(CookielibQtCookieJar(cookiejar))
        self._had_requests = False

    def createRequest(self, operation, request, device=None):
        if self.remote_request_counter:
            self.remote_request_counter.callRemote('increase_request_count', 1)

        reply = ScrapyNetworkReply(self)
        reply.setRequest(request)
        reply.setOperation(operation)

        if operation == QNetworkAccessManager.CustomOperation:
            method = request.attribute(QNetworkRequest.CustomVerbAttribute)
        else:
            method = QT_OPERATION_TO_HTTP_METHOD[operation]

        request.setHeader(QNetworkRequest.UserAgentHeader, None)
        headers = {bytes(header): bytes(request.rawHeader(header))
                   for header in request.rawHeaderList()}
        if self.user_agent is not None:
            headers[b'User-Agent'] = self.user_agent

        if device:
            body = bytes(device.readAll())
            reply.uploadProgress.emit(len(body), len(body))
        else:
            body = None

        remote_req = RequestFromBrowser(
            url=request.url().toString(),
            method=method,
            headers=headers,
            body=body,
            is_first_request=(not self._had_requests),
            cookiejarkey=self.cookiejarkey
        )

        self._had_requests = True

        dfd = self.remote_downloader.callRemote('make_request', remote_req)
        dfd.addCallbacks(reply.callback, reply.errback)

        return reply


class ScrapyNetworkReply(QNetworkReply):
    """A network reply object for a request made with Scrapy."""

    def __init__(self, nam):
        super().__init__(nam)
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
                           ScrapyIgnoreRequest):
            error_code = QNetworkReply.OperationCanceledError
        elif failure.check(SSLError):
            error_code = QNetworkReply.SslHandshakeFailedError
        elif failure.check(ScrapyNotSupported):
            error_code = QNetworkReply.ProtocolUnknownError
        else:
            error_code = QNetworkReply.UnknownNetworkError

        self.setError(error_code, error_message)
        self.error.emit(error_code)
        # XXX: this segfaults.
        # self.finished.emit()

        return failure

    def bytesAvailable(self):
        return (super().bytesAvailable() +
                (len(self.content.getvalue()) - self.content.tell()))

    def readData(self, size):
        return self.content.read(size)

    def abort(self):
        self.aborted = True
        self.close()
        self.setError(QNetworkReply.OperationCanceledError, "")
        self.error.emit(QNetworkReply.OperationCanceledError)
        self.finished.emit()
