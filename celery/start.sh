#!/bin/bash

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [START.SH] $1"
}

echo Starting Celery.

#make sure we are at project root /usr/src/app
cd $PROJECT_ROOT
cd etabotsite

trap 'echo "Shutting down gracefully..."; kill -TERM $celery_pid; wait $celery_pid' SIGTERM SIGINT

log_msg "log_msg exec celery"
echo ExecCelery

exec celery -A etabotsite worker \
  -l info \
  --max-tasks-per-child=4 \
  --concurrency=2

celery_pid=$!
log_msg "Celery worker started with PID: $celery_pid"

wait $celery_pid

exit_code=$?

log_msg "=== CELERY WORKER EXITED ==="
log_msg "Celery worker exit code: $exit_code"

if [ $exit_code -eq 0 ]; then
    log_msg "Celery worker exited normally"
else
    log_msg "Celery worker exited with error code: $exit_code"
fi
