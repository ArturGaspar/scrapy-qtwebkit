from setuptools import find_packages, setup


setup(
    name='scrapy-qtwebkit',
    version='1.0.0',
    description='Qt WebKit for Scrapy',
    author='Artur Gaspar',
    author_email='artur.gaspar.00@gmail.com',
    packages=find_packages(),
    install_requires=['Twisted>=18']
)
