FROM python:3.5-alpine
WORKDIR /project
COPY . /project
COPY openstack_vim_driver/etc/configuration.ini /etc/openbaton/openstack_vim_driver.ini
RUN ["apk", "update"]
RUN ["apk", "add", "gcc", "musl-dev", "linux-headers", "libffi-dev", "openssl-dev"]
RUN ["pip", "install", "-r", "requirements.txt"]
RUN ["pip", "install", "."]
ENTRYPOINT ["openstack-vim-driver"]
