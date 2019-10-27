from twisted.spread import pb


class BrowserManager(pb.Root):
    def __init__(self, browser_cls):
        super().__init__()
        self.browser_cls = browser_cls

    def remote_open_browser(self, downloader, options):
        return self.browser_cls(downloader, options)
