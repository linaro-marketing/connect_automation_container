# Set the base image to Ubuntu (version 18.04)
ARG UBUNTU_VERSION=18.04
FROM ubuntu:${UBUNTU_VERSION}

# Software packages, any version, remain installed
ENV UNVERSIONED_PACKAGES \
# Required for ???
 locales

# Software packages, any version, unavailable after `docker build`
ENV EPHEMERAL_UNVERSIONED_PACKAGES \
# The automation runs under the Python 3.x interpreter
 python3 \
# and uses `pip` for installation
 python3-pip \
# Required for pip3 install from Git repo
 git

ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# FIXME: Python packages should be in a pipenv
COPY requirements.txt /tmp/

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    # Install temporary packages
    ${EPHEMERAL_UNVERSIONED_PACKAGES} \
    ${UNVERSIONED_PACKAGES} \
    && sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=en_US.UTF-8 && \
    apt-get install -y ${EPHEMERAL_UNVERSIONED_PACKAGES} && \
    pip3 install -r /tmp/requirements.txt && \
# This should be in a pipenv
# Versions should be specified by tags or commits
    pip3 install \
    git+https://github.com/linaro-marketing/JekyllPostTool.git@master \
    git+https://github.com/linaro-marketing/linaro_connect_resources_updater.git@master \
    git+https://github.com/linaro-marketing/SchedDataInterface.git@master \
    git+https://github.com/linaro-marketing/SocialMediaImageGenerator.git \
    git+https://github.com/linaro-marketing/connect_youtube_uploader.git \
    git+https://github.com/linaro-marketing/SchedPresentationTool.git \
    && \
# Clean up package cache in this layer
    apt-get --purge remove -y \
# Uninstall temporary packages
    ${EPHEMERAL_UNVERSIONED_PACKAGES} && \
# Remove dependencies which are no longer required
    apt-get --purge autoremove -y && \
# Clean package cache
    apt-get clean -y && \
# Restore interactive prompts
    unset DEBIAN_FRONTEND && \
# Remove cache files
    rm -rf \
    /tmp/* \
    /var/cache/* \
    /var/log/* \
    /var/lib/apt/lists/*


WORKDIR /app
COPY . /app
RUN chmod +x /app/*


ENV ENV="/app:${PATH}"

