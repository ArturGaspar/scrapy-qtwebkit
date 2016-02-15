Qt WebKit for Scrapy
====================

This is a Scrapy middleware for rendering pages with Qt WebKit. It allows for
easy and integrated rendering of web pages with Javascript, and interaction
with the web pages in spider callbacks. Network requests are made with Scrapy,
passing through all your existing downloader and spider middlewares.

See the ``examples`` directory for examples on how to use.


Usage
=====

To use, enable the downloader middleware in Scrapy settings::

    DOWNLOADER_MIDDLEWARES = {
        'scrapy_qtwebkit.QtWebKitMiddleware': 200
    }

And use the QtWebKitRequest class for making requests with WebKit.


The middleware can be configured with the following settings:

- ``QTWEBKIT_SHOW_WINDOW`` - Whether to display web pages in a window as they
  are processed.

- ``QTWEBKIT_QT_PLATFORM`` - Qt platform plugin to use. "minimal" can be used
  in headless setups. "default" will let Qt select the default for the current
  platform, but expects an usable graphics system. Defaults to "minimal".

- ``QTWEBKIT_COOKIES_ENABLED`` - Whether the middleware should manage cookies
  and share them with WebKit. It is recommended to also disable Scrapy's
  default cookie handling (``COOKIES_ENABLED = False``) when enabling this.

- ``QTWEBKIT_ENABLE_DEV_TOOLS`` - Whether to enable web development tools. When
  used together with ``QTWEBKIT_SHOW_WINDOW`` (and long waits before returning
  from callbacks), can be used to inspect the state of live pages.

- ``QTWEBKIT_PAGE_LIMIT`` - Limit of pages to have open at the same time.


The module also provides a downloader for data: URLs and a log formatter that
lowers the level of requests made by WebKit below DEBUG level.
