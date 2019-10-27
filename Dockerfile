# sudo docker build -t scrapy-qtwebkit . && sudo docker run -p 8000:8000 scrapy-qtwebkit

FROM debian:buster-slim

RUN apt-get update
RUN	apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-pyqt5 \
    python3-pyqt5.qtwebkit \
    python3-setuptools \
    python3-twisted

RUN pip3 install qt5reactor==0.5

EXPOSE 8000
ENV QT_QPA_PLATFORM=offscreen

COPY . /usr/local/src/scrapy_qtwebkit
RUN pip3 install /usr/local/src/scrapy_qtwebkit

CMD ["python3", "-m", "scrapy_qtwebkit.browser_engine", "tcp:8000"]
