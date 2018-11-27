if __name__ == "__main__":
    import sys

    import qt5reactor
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    qt5reactor.install()

    from twisted.internet import reactor
    from twisted.spread import jelly, pb

    from scrapy_qtwebkit.browser import BrowserManager
    from scrapy_qtwebkit.browser.qt import Browser

    reactor.listenTCP(8789, pb.PBServerFactory(
        BrowserManager(Browser),
        unsafeTracebacks=True,
        security=jelly.DummySecurityOptions()
    ))
    reactor.run()
