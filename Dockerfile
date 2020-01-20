# Set the base image to Ubuntu (version 18.04)
ARG UBUNTU_VERSION=18.04
FROM ubuntu:${UBUNTU_VERSION}

# Software packages, any version, remain installed
ENV UNVERSIONED_PACKAGES \
# Required by Perl
 locales

# Software packages, any version, unavailable after `docker build`
ENV EPHEMERAL_UNVERSIONED_PACKAGES \
# The automation runs under the Python 3.x interpreter
 python3 \
# and uses `pip` for installation
 python3-pip \
 python3-setuptools \
 python3-wheel \
# Required for pip3 install from Git repo
 git

ENV LANG en_US.UTF-8

# FIXME: Python packages should be in a pipenv
COPY requirements.txt /tmp/

# Required by Perl
# COPY locale /etc/default/locale

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    # Temporarily set `C` for locale, as it's the only one available
    LANG=C \
    LANGUAGE=$LANG \
    LC_ALL=$LANG \
    apt-get install -y --no-install-recommends \
    ${UNVERSIONED_PACKAGES}

RUN echo "LC_ALL=${LANG}" >> /etc/environment && \
    echo "${LANG} UTF-8" >> /etc/locale.gen && \
    echo "LANG=${LANG}" >> /etc/default/locale && \
    # echo "LC_ALL=${LANG}" >> /etc/default/locale && \
    echo "LANG=${LANG}" > /etc/locale.conf && \
    locale-gen ${LANG} && \
    export LANG=${LANG} && \
    export LANGUAGE=${LANG} && \
    export LC_ALL=${LANG}


# RUN update-locale LANG=en_US.UTF-8
    # && \
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
# Install temporary packages
    ${EPHEMERAL_UNVERSIONED_PACKAGES} \
    && dpkg-reconfigure --frontend=noninteractive locales && \
    apt-get install -y ${EPHEMERAL_UNVERSIONED_PACKAGES}


# This should be in a pipenv
RUN pip3 install -r /tmp/requirements.txt \
# Versions should be specified by tags or commits
    git+https://github.com/linaro-marketing/JekyllPostTool.git@master \
    git+https://github.com/linaro-marketing/linaro_connect_resources_updater.git@master \
    git+https://github.com/linaro-marketing/SchedDataInterface.git@master \
    git+https://github.com/linaro-marketing/SocialMediaImageGenerator.git \
    git+https://github.com/linaro-marketing/connect_youtube_uploader.git \
    git+https://github.com/linaro-marketing/SchedPresentationTool.git


# Clean up package cache in this layer
RUN apt-get --purge remove -y \
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

