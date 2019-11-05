import sys
from types import SimpleNamespace

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.0')
from gi.repository import GLib, Gtk, WebKit2

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.spread import pb

from ..._intermediaries import RequestFromScrapy, RequestFromBrowser

from ..utils.proxy import RemoteScrapyProxyFactory

from .js import get_js_value


def _setup_pre_reactor():
    import gi
    # Some packagers do not include pygtkcompat, yet the Twisted GTK 3 reactor
    # setup always expects it. gi seems to do the necessary checks so make a
    # dummy module to keep Twisted happy.
    # TODO: check since which version gi checks for conflict.
    try:
        import gi.pygtkcompat
    except ImportError:
        _pygtkcompat = SimpleNamespace(enable=lambda: None)
        sys.modules["gi.pygtkcompat"] = gi.pygtkcompat = _pygtkcompat

    from twisted.internet import gtk3reactor
    gtk3reactor.install()
    Gtk.init()


class Browser(pb.Referenceable):
    def __init__(self, reactor, downloader, global_options):
        super().__init__()
        self._reactor = reactor
        self.downloader = downloader
        self.options = global_options
        self._windows = None

    def remote_create_webpage(self, options: dict):
        proxy = RemoteScrapyProxyFactory(
            remote_downloader=self.downloader,
            cookiejarkey=options.get('cookiejarkey')
        )
        # TODO: add warning about an HTTP proxy opening on some port.
        listeningport = self._reactor.listenTCP(0, proxy)
        port = listeningport.getHost().port

        ctx = WebKit2.WebContext.new_ephemeral()
        ctx.set_network_proxy_settings(
            WebKit2.NetworkProxyMode.CUSTOM,
            WebKit2.NetworkProxySettings(f'http://localhost:{port}', None)
        )
        ctx.set_tls_errors_policy(WebKit2.TLSErrorsPolicy.IGNORE)

        webview = WebKit2.WebView.new_with_context(ctx)

        if self.options.get('show_windows', False):
            window = Gtk.Window()
            window.add(webview)
            window.show_all()
        else:
            window = None

        return WebPageRemoteControl(self, self.downloader, options, webview,
                                    window, listeningport)


class WebPageRemoteControl(pb.Referenceable):
    def __init__(self, browser: Browser, downloader, options: dict,
                 webview: WebKit2.WebView, window, listeningport):
        super().__init__()
        self.browser = browser
        self._downloader = downloader
        self._options = options
        self._url = None
        self._webview = webview
        self._window = window
        self._listeningport = listeningport

    def _close(self):
        if self._webview:
            self._webview.destroy()
            self._webview = None
        if self._window:
            self._window.destroy()
            self._window = None
        if self._listeningport:
            port = self._listeningport
            self._listeningport = None
            return port.stopListening()

    def __del__(self):
        self._close()

    def remote_close(self):
        return self._close()

    @inlineCallbacks
    def remote_load_request(self, request: RequestFromScrapy):
        # WebKit2GTK does not support setting headers or method when loading
        # request. Instead, make the request and set it as the content.
        remote_req = RequestFromBrowser(
            url=request.url,
            method=request.method,
            headers=request.headers,
            body=request.body,
            is_first_request=True,
            cookiejarkey=self._options.get('cookiejarkey')
        )
        response = yield self._downloader.callRemote('make_request', remote_req)

        # TODO: make headers a caseless dict.
        ctype = response.headers.get(b'Content-Type')
        if ctype:
            mime_type = ctype[0].decode().split(';', 1)[0]
        else:
            mime_type = None

        d = Deferred()

        def on_load_changed(webview, event):
            if event == WebKit2.LoadEvent.FINISHED:
                webview.disconnect(handler_id)
                d.callback(None)

        handler_id = self._webview.connect("load_changed", on_load_changed)

        self._webview.load_bytes(GLib.Bytes(response.body), mime_type, None,
                                 request.url)

        yield d
        return (True, response.status, response.headers, None)

    def remote_get_url(self):
        return self._webview.get_uri()

    @inlineCallbacks
    def _run_script(self, script):
        d = Deferred()
        # TODO: Gio.Cancellable
        self._webview.run_javascript(script, None,
                                     lambda *args: d.callback(args),
                                     None)
        webview, task, user_data = yield d
        result = self._webview.run_javascript_finish(task)
        return result.get_js_value()

    @inlineCallbacks
    def remote_get_body(self):
        jsvalue = yield self._run_script("document.documentElement.outerHTML")
        return ('utf-8', jsvalue.to_string_as_bytes().get_data())

    def remote_run_script(self, script):
        return self._run_script(script).addCallback(get_js_value)
