From ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive

COPY ./ /home/
WORKDIR /home/slither
RUN apt-get -y update  && \
	apt-get install -y python3 python3-pip && \
	python3 setup.py install && \
	python3 -m pip install -r ../requirments.txt

WORKDIR /home
RUN chmod +x ./solc_install.sh && ./solc_install.sh
