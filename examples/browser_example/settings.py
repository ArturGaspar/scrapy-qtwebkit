# Scrapy settings for browser_example project

SPIDER_MODULES = ['browser_example.spiders']
NEWSPIDER_MODULE = 'browser_example.spiders'

ROBOTSTXT_OBEY = False

DOWNLOADER_MIDDLEWARES = {
    'scrapy_qtwebkit.middleware.BrowserMiddleware': 200
}
SPIDER_MIDDLEWARES = {
    'scrapy_qtwebkit.middleware.BrowserResponseTrackerMiddleware': 200
}
COOKIES_ENABLED = False
BROWSER_ENGINE_COOKIES_ENABLED = True

BROWSER_ENGINE_SERVER = 'tcp:localhost:8000'
# BROWSER_ENGINE_START_SERVER = True
BROWSER_ENGINE_OPTIONS = {
    'show_windows': True,
    'window_type': 'mdi'
}
# Enable and configure HTTP caching (disabled by default)
# See https://doc.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = 'httpcache'
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'

