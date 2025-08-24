# Dockerfile

# FROM directive instructing base image to build upon
FROM python:3.9

# File Author / Maintainer
MAINTAINER Maintainer Alex Radnaev

ENV PROJECT_ROOT /usr/src/app
ADD . /usr/src/app
COPY celery/start.sh /start.sh

RUN pip install -r /usr/src/app/requirements.txt

# EXPOSE port 8000 to allow communication to/from server
EXPOSE 8000

# CMD specifcies the command to execute to start the server running.
CMD ["/start.sh", "-docker"]
# done!
