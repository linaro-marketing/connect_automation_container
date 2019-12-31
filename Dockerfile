FROM ubuntu:18.04

RUN apt-get update && \
apt-get install -y python3 && \
apt-get install -y python3-pip

WORKDIR /app
COPY . /app
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh
RUN chmod +x /app/*
ENV ENV="/app:${PATH}"

ENTRYPOINT [ "entrypoint.sh" ]
