import os
import tempfile
from urllib.parse import urljoin

from OpenSSL import crypto
from twisted.internet import ssl
from twisted.python import log
from twisted.web import http

from ..._intermediaries import RequestFromBrowser


class TmpCertSSLContextFactory(ssl.DefaultOpenSSLContextFactory):
    def __init__(self):
        super().__init__(*self._gen_cert())

    @staticmethod
    def _gen_cert():
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, 1024)
        cert = crypto.X509()
        cert.gmtime_adj_notBefore(0)
        cert.set_notAfter(b'99991231235959Z')
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)
        cert.sign(key, 'sha1')

        key_file = tempfile.NamedTemporaryFile(delete=False)
        key_file.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
        key_file.close()

        cert_file = tempfile.NamedTemporaryFile(delete=False)
        cert_file.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        cert_file.close()

        return key_file.name, cert_file.name

    def __del__(self):
        os.unlink(self.privateKeyFileName)
        os.unlink(self.certificateFileName)



class RemoteScrapyProxyRequest(http.Request):
    def process(self):
        if self.method == b'CONNECT':
            self.finish()
            self.transport.startTLS(TmpCertSSLContextFactory())
            return

        # TODO: port
        host = self.getHeader('Host')
        if self.isSecure():
            scheme = 'https'
        else:
            scheme = 'http'
        base_url = f'{scheme}://{host}'
        url = urljoin(base_url, self.uri.decode())

        self.content.seek(0, 0)
        remote_req = RequestFromBrowser(
            url=url,
            method=self.method.decode(),
            headers=dict(self.requestHeaders.getAllRawHeaders()),
            body=self.content.read(),
            is_first_request=False,
            cookiejarkey=self.channel.factory.cookiejarkey
        )
        dfd = self.channel.factory.remote_downloader.callRemote('make_request',
                                                                remote_req)
        dfd.addCallbacks(self._handle_response, self._handle_error)

    def _handle_error(self, failure):
        # TODO: log
        log.err(failure)
        self._write_response(
            status=http.INTERNAL_SERVER_ERROR,
            headers={b'Content-Type': [b"text/plain"]},
            body=b"Error"
        )

    def _handle_response(self, response):
        self._write_response(
            status=response.status,
            headers=response.headers,
            body=response.body
        )

    def _write_response(self, status, headers, body):
        self.setResponseCode(status)
        for header, values in headers.items():
            self.responseHeaders.setRawHeaders(header, values)
        self.setHeader(b'Content-Length', str(len(body)).encode('ascii'))
        self.write(body)
        self.finish()


class RemoteScrapyProxy(http.HTTPChannel):
    requestFactory = RemoteScrapyProxyRequest


class RemoteScrapyProxyFactory(http.HTTPFactory):
    protocol = RemoteScrapyProxy

    def __init__(self, remote_downloader, *args, cookiejarkey=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.remote_downloader = remote_downloader
        self.cookiejarkey = cookiejarkey
