# -*- coding: utf-8 -*-

SPIDER_MODULES = ['hello_world.spider']
NEWSPIDER_MODULE = 'hello_world.spider'

DOWNLOADER_MIDDLEWARES = {
    'scrapy_qtwebkit.QtWebKitMiddleware': 200
}

QTWEBKIT_SHOW_WINDOW = True
QTWEBKIT_QT_PLATFORM = "default"
QTWEBKIT_COOKIES_ENABLED = True
COOKIES_ENABLED = False
