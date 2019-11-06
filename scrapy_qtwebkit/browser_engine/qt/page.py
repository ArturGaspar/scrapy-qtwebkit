from PyQt5.QtCore import pyqtSignal
from PyQt5.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt5.QtWebKitWidgets import QWebPage
from twisted.internet.error import (ConnectingCancelledError, ConnectionLost,
                                    ConnectionRefusedError, DNSLookupError,
                                    SSLError, TimeoutError)

from ..._intermediaries import ScrapyNotSupported


QT_ERROR_TO_EXCEPTION = {
    QNetworkReply.ConnectionRefusedError: ConnectionRefusedError,
    QNetworkReply.RemoteHostClosedError: ConnectionLost,
    QNetworkReply.HostNotFoundError: DNSLookupError,
    QNetworkReply.TimeoutError: TimeoutError,
    QNetworkReply.OperationCanceledError: ConnectingCancelledError,
    QNetworkReply.SslHandshakeFailedError: SSLError,
    QNetworkReply.ProtocolUnknownError: ScrapyNotSupported
}


# TODO: handlers for JavaScript message boxes.


class MyErrorPageExtensionOption(QWebPage.ErrorPageExtensionOption):
    pass


class CustomQWebPage(QWebPage):
    """

    QWebPage subclass with a signal for load finished with a parameter for
    page errors.

    """

    loadFinishedWithError = pyqtSignal(bool, QWebPage.ErrorPageExtensionOption)

    _dummy_error = QWebPage.ErrorPageExtensionOption()
    _dummy_error.domain = QWebPage.Http

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.webview = None
        self._current_error = None
        self.loadFinished.connect(self._on_load_finished)

    def setNetworkAccessManager(self, nam):
        super().setNetworkAccessManager(nam)
        self.networkAccessManager().finished.connect(self._on_network_reply)

    def _has_error(self):
        return (self._current_error and
                not isinstance(self._current_error,
                               MyErrorPageExtensionOption))

    def _on_network_reply(self, reply):
        if self._has_error():
            return
        if not self._current_error and reply.error() == QNetworkReply.NoError:
            if reply.attribute(QNetworkRequest.RedirectionTargetAttribute):
                return
            self._current_error = MyErrorPageExtensionOption()
            self._current_error.domain = QWebPage.Http
            self._current_error.error = reply.attribute(
                QNetworkRequest.HttpStatusCodeAttribute
            )
            self._current_error.url = reply.url()
            self._current_error.errorString = reply.attribute(
                QNetworkRequest.HttpReasonPhraseAttribute
            )
            self._current_error.headers = {bytes(h): bytes(v)
                                           for h, v in reply.rawHeaderPairs()}
        # TODO: network error.

    def _on_load_finished(self, ok):
        error = self._current_error or self._dummy_error
        self._current_error = None
        self.loadFinishedWithError.emit(ok, error)

    def extension(self, extension, option=None, output=None):
        if extension == QWebPage.ErrorPageExtension:
            if not self._has_error():
                self._current_error = option

        return False

    def supportsExtension(self, extension):
        if extension == QWebPage.ErrorPageExtension:
            return True

        return super().supportsExtension(extension)
