from PyQt5.QtNetwork import QNetworkAccessManager


HTTP_METHOD_TO_QT_OPERATION = {
    "HEAD": QNetworkAccessManager.HeadOperation,
    "GET": QNetworkAccessManager.GetOperation,
    "PUT": QNetworkAccessManager.PutOperation,
    "POST": QNetworkAccessManager.PostOperation,
    "DELETE": QNetworkAccessManager.DeleteOperation
}

QT_OPERATION_TO_HTTP_METHOD = {
    v: k for k, v in HTTP_METHOD_TO_QT_OPERATION.items()
}
