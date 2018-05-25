FROM python:alpine
WORKDIR /project
COPY . /project
RUN ["apk", "update"]
RUN ["apk", "add", "gcc", "musl-dev", "linux-headers", "libffi-dev", "openssl-dev"]
RUN ["pip", "install", "-r", "requirements.txt"]
RUN ["pip", "install", "."]
ENTRYPOINT ["openstack-vim-driver"]
