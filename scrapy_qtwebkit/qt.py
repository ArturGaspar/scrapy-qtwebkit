"""

Importer that decides on which Qt module to load at runtime.

Intended to enable compatibility with PySide2 when it is released.

"""


import importlib
import os
import sys


# Pretend this is a package.
__path__ = []


class QtImporter(object):
    qt_bindings = ['PyQt5']

    def __init__(self, qt_package=None, this_package=__name__):
        super(QtImporter, self).__init__()
        self.qt_package = qt_package
        self.name_prefix = this_package + '.'

    def find_module(self, fullname, path=None):
        if fullname.startswith(self.name_prefix):
            return self

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]

        if self.qt_package is None:
            for qt_package in self.qt_bindings:
                try:
                    importlib.import_module(qt_package)
                except ImportError:
                    pass
                else:
                    break
            else:
                raise ImportError(("Qt bindings not found, attempted to import "
                                   "{}").format(', '.join(self.qt_bindings)))
            self.qt_package = qt_package

        actual_name = self.qt_package + '.' + fullname[len(self.name_prefix):]
        return sys.modules.setdefault(fullname,
                                      importlib.import_module(actual_name))


qt_package = os.environ.get("SCRAPY_QTWEBKIT_QT_BINDINGS") or None
sys.meta_path.append(QtImporter(qt_package))
