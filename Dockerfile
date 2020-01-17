FROM ubuntu:18.04


RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y locales \
    && sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=en_US.UTF-8 && \
    apt-get install -y python3 && \
    apt-get install -y python3-pip && \
    apt-get install -y git

ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

COPY requirements.txt /tmp/

RUN pip3 install -r /tmp/requirements.txt
RUN pip3 install \
 git+https://github.com/linaro-marketing/JekyllPostTool.git@master \
 git+https://github.com/linaro-marketing/linaro_connect_resources_updater.git@master \
 git+https://github.com/linaro-marketing/SchedDataInterface.git@master \
 git+https://github.com/linaro-marketing/SocialMediaImageGenerator.git \
 git+https://github.com/linaro-marketing/connect_youtube_uploader.git \
 git+https://github.com/linaro-marketing/SchedPresentationTool.git

WORKDIR /app
COPY . /app
RUN chmod +x /app/*


ENV ENV="/app:${PATH}"

