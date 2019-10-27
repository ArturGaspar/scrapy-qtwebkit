from PyQt5.QtWidgets import QMdiArea


class BaseQWebViewWindows(object):
    def add_webview(self, webview):
        pass

    def remove_webview(self, webview):
        pass


class SimpleQWebViewWindows(BaseQWebViewWindows):
    def add_webview(self, webview):
        webview.show()

    def remove_webview(self, webview):
        pass


class MdiQWebViewWindows(BaseQWebViewWindows):
    def __init__(self):
        super().__init__()
        self._mdi_area = None

    def add_webview(self, webview):
        if self._mdi_area is None:
            self._mdi_area = QMdiArea()
            self._mdi_area.resize(1024, 768)
            # self._mdi_area.setWindowTitle()
            self._mdi_area.show()
        subwindow = self._mdi_area.addSubWindow(webview)
        webview.titleChanged.connect(subwindow.setWindowTitle)
        subwindow.show()
        self._mdi_area.tileSubWindows()

    def remove_webview(self, webview):
        subwindow = webview.parentWidget()
        webview.close()
        self._mdi_area.removeSubWindow(subwindow)
        self._mdi_area.tileSubWindows()


window_types = {
    'simple': SimpleQWebViewWindows,
    'mdi': MdiQWebViewWindows
}
