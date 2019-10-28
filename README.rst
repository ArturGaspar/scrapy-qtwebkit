Qt WebKit for Scrapy
====================

This is a Scrapy middleware for rendering pages with Qt WebKit. It allows for
easy and integrated rendering of web pages with Javascript, and interaction
with web pages in spider callbacks. Network requests are made with Scrapy,
passing through existing downloader and spider middlewares.

See the ``examples`` directory for examples on how to use.


Usage
=====

To use, enable the downloader middleware in Scrapy settings::

    DOWNLOADER_MIDDLEWARES = {
        'scrapy_qtwebkit.middleware.BrowserMiddleware': 200
    }

Optionally, also enable the spider middleware to track pages and automatically
close them::

    SPIDER_MIDDLEWARES = {
        'scrapy_qtwebkit.middleware.BrowserResponseTrackerMiddleware': 200
    }

And use the scrapy_qtwebkit.BrowserRequest class for making requests with
WebKit.


The middleware can be configured with the following settings:

- ``BROWSER_ENGINE_SERVER`` - Address of browser engine server
  (see scrapy_qtwebkit.browser_engine) as a Twisted endpoint description string
  (e.g. ``tcp:localhost:8000``).

- ``BROWSER_ENGINE_START_SERVER`` - Whether to start the browser engine server.
  Not used if ``BROWSER_ENGINE_SERVER`` is set.

- ``BROWSER_ENGINE_COOKIES_ENABLED`` - Whether to synchronise cookies between
  Scrapy and the browser engine.

- ``BROWSER_ENGINE_PAGE_LIMIT`` - Limit of pages to have open at the same time
  (for this client only) in the browser engine.

- ``BROWSER_ENGINE_OPTIONS`` - Dictionary of global options for the browser
  engine. Options supported by the ``qt`` backend include ``show_windows`` and
  ``window_type``.

The module also provides a log formatter that lowers the level of requests made
by the browser engine below DEBUG level.


Installation
============

TODO


Getting started
===============

After installing scrapy-qtwebkit, if you also have PyQt5 and Qt WebKit, run the
browser engine server::

    python3 -m scrapy_qtwebkit.browser_engine tcp:8000

Alternatively, if you would prefer to run it on Docker (not requiring manual
installation of PyQt5 or Qt WebKit), refer to
`Using the provided Dockerfile to run the browser engine server on Docker`.

TODO: ensure Scrapy is installed on Installation section

Go to the ``examples`` directory where a Scrapy project is set up to use
scrapy-qtwebkit. Run the example spider with ``scrapy crawl basic``.


Using the provided Dockerfile to run the browser engine server on Docker
========================================================================

Build an image from the provided Dockerfile (this step is only necessary once)::

    docker build -t scrapy-qtwebkit .

Run it as::

    docker run -p 8000:8000 scrapy-qtwebkit


Seeing the browser window when running on Docker
------------------------------------------------

In order to be able to see the browser window when running on Docker,
run it as::

    docker run -v /tmp/.X11-unix:/tmp/.X11-unix \
               -v "$HOME/.Xauthority:/root/.Xauthority" \
               -e "DISPLAY=$DISPLAY" \
               -e XAUTHORITY=/root/.Xauthority \
               -e QT_QPA_PLATFORM= \
               -p 8000:8000 scrapy-qtwebkit

If the above does not work, you might need to run ``xhost local:root``.
