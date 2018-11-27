from twisted.spread.pb import Copyable


class RequestFromScrapy(Copyable, object):
    def __init__(self, url, method, headers, body):
        super(RequestFromScrapy, self).__init__()
        self.url = url
        self.method = method
        self.headers = headers
        self.body = body


class RequestFromBrowser(Copyable, object):
    def __init__(self, url, method, headers, body, is_first_request,
                 cookiejarkey):
        super(RequestFromBrowser, self).__init__()
        self.url = url
        self.method = method
        self.headers = headers
        self.body = body
        self.is_first_request = is_first_request
        self.cookiejarkey = cookiejarkey


class ResponseFromScrapy(Copyable, object):
    def __init__(self, url, status, headers, body):
        super(ResponseFromScrapy, self).__init__()
        self.url = url
        self.status = status
        self.headers = headers
        self.body = body


class ErrorFromWebPage(Copyable, object):
    def __init__(self, is_http, url, status, headers, body):
        super(ErrorFromWebPage, self).__init__()
        self.url = url
        self.status = status
        self.headers = headers
        self.body = body


class ScrapyError(Exception):
    pass


class ScrapyIgnoreRequest(ScrapyError):
    pass


class ScrapyNotSupported(ScrapyError):
    pass
