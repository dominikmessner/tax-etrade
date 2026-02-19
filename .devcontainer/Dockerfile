FROM mcr.microsoft.com/devcontainers/python:2-3.12-trixie

# Install the Yarn repository GPG key securely
RUN mkdir -p /usr/share/keyrings && \
    curl -fsSL https://dl.yarnpkg.com/debian/pubkey.gpg -o /tmp/yarn-key.gpg && \
    gpg --batch --yes --output /usr/share/keyrings/yarn-archive-keyring.gpg --dearmor /tmp/yarn-key.gpg && \
    echo 'deb [signed-by=/usr/share/keyrings/yarn-archive-keyring.gpg] https://dl.yarnpkg.com/debian stable main' > /etc/apt/sources.list.d/yarn.list && \
    rm -f /tmp/yarn-key.gpg 

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && curl -sSL https://dl.google.com/linux/direct/google-chrome-stable_current_$(dpkg --print-architecture).deb -o /tmp/chrome.deb \
    && apt-get -y install /tmp/chrome.deb \
    && rm /tmp/chrome.deb

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir uv