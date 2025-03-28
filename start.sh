#!/bin/bash

echo Starting Gunicorn.

#make sure we are at project root /usr/src/app
cd $PROJECT_ROOT

if [ ! -f $PROJECT_ROOT/.build ]; then
  echo "Collecting and compiling statics"
  pushd etabotsite
  python manage.py collectstatic --noinput
  python manage.py migrate --run-syncdb
  popd
  date > $PROJECT_ROOT/.build
fi

cd etabotsite
NUM_WORKERS=3
TIMEOUT=120

if [ $MODE = "PYTEST" ]; then
  exec pytest
else
  nohup celery -A etabotsite beat -l INFO &
  exec gunicorn etabotsite.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers $NUM_WORKERS \
      --worker-class gevent \
      --timeout $TIMEOUT
      --limit-request-field-size 10485760
fi
