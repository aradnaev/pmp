# pmp

backend data infrastructure and server for Smart project management tool made for teams to meet their deadline


## To deploy pmp, you have two choices:
- Docker version (typically used in production)
- non-Docker version (typically used for development to allow faster iterations)


## non-Docker version deployment
### To run django seperately for development, please follow the process below:

#### Prerequisite:
* Have python 3.6 installed on your development machine (anaconda distribution is pretty good)

## Install virtual environment management tool
If you already know how to create a python virtual environment, you can skip this section, and directly go to *Run django server locally* section.

### Choose between virtualenv or conda:

### conda option (recommended for less dependencies troubleshooting)
    follow https://docs.conda.io/projects/conda/en/latest/user-guide/install/
    create virtual environement following https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html
E.g.:
```
conda create -n etabot python=3.5
```
Activate
```
conda activate etabot
```

### virtualenv option (do not follow if you use conda for virtual environment management)

    Install `virtualenv` and `virtualenvwrapper` tool to manage python environment
    ```
    $ pip install virtualenv
    $ pip install virtualenvwrapper
    ```
    Open your bash profile:
    ```
    $ vim ~/.bash_profile
    ```
    and add the following two lines at the end of the file:
    ```
    export WORKON_HOME=~/Envs
    source /usr/local/bin/virtualenvwrapper.sh
    ```
    And at your terminal, run:
    ```
    $ source ~/.bash_profile
    ```

    To create a virtual environment for the project, follow the command below:
    ```
    $ mkvirtualenv --python=python3 <name_of_the_virtual_environment>
    ```



### Configure pmp
### Note: your teammates might already have configuration files - good idea to ask them

(see Advanced settings for details of file definitions)
- add custom_settings.json to etabotsite directory 
- add sys_email_settings.json to etabotsite directory
- optionally add django_keys_prod.json with your secret keys etabotsite directory (same format as django_keys.json)
- optionally add ETA algorithm as a git submodule (see section "Optinal: connecting ETA algorithm instead of a placeholder")

### Database setup
We support Postgres database, we no longer support sqlite3 (default local Django Database).

For local development you can setup a postgres database in a few minutes using docker container:

```docker pull postgres```

```docker run --name postgres -e POSTGRES_PASSWORD=password -p 5432:5432 -v ~/dir/:/var/lib/postgresql/data -d postgres```

Execute commands (e.g. in a SQLWorkbench)
```SET AUTOCOMMIT = ON;```
```CREATE USER etabot WITH PASSWORD 'somepassword';```
```CREATE DATABASE etabot_db WITH OWNER etabot;```

change custom_settings.json with the new db interface (see section *Settings jsons*)

Go the etabotsite directory:
```
$ cd etabotsite/
```

```$ python manage.py migrate```

#### Run django server locally

*Prerequisite*: enable your virtual environemnt

go to our project root directory, install the dependencies:
```
$ pip install -r requirements.txt
```
Go the etabotsite directory:
```
$ cd etabotsite/
```

If this is your first time running the project in development mode and you are using local database, you want to create the database table by running the following command:
```
$ python manage.py migrate
```

Note: we no longer use python manage.py makemigrations to create migrations during setup. The migration files are part of the code base now since automatic makemigrations miss certain,

To run the backend server:
```
$ python manage.py runserver 127.0.0.1:8000
```

Vola! You have django server up and running in development mode. Go to you browser, enter the address below:
http://localhost:8000


## Database schema changes during development
There is one official way to define database schema - that is defined by Django migration files, which are part of code base.
This is needed to work around failures of automatic makemigrations and migrate routine (e.g. some models.py schema changes are not properly reflected in migrations files, some migration files commands are not altering actual database properly).

If your code requires database schema change, please run
```python manage.py makemigrations```
```python manage.py migrate```
and test the results.
If needed, edit new migration files manually.
Add migration files to commit.

## Trouble Shooting
production app.etabot.ai can't be reached - check that your /etc/hosts is not pointing to localhost


## Testing 

To run all the unit tests - from etabotsite directory:
```
$ python manage.py test
```

## Advanced settings

### local DNS setting
* Add your dns to hosts, for example:
  ``` 
  $ sudo vi /etc/hosts
  ```
  Add the following line to the end of the file:
  ```
  127.0.0.1 app.etabot.ai
  ```

### Settings jsons

#### custom_settings.json - general custom settings
```
{
    "local_host_url":"<your local host url for testing, e.g. http://127.0.0.1:8000">,
    "prod_host_url":"<your production host url for testing, e.g. https://app.etabot.ai>"

    "db": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "your_db_name",
        "USER": "your_username",
        "PASSWORD": "your_password",
        "HOST": "host, e.g. localhost"
    },    

    "MESSAGE_BROKER":"rabbitmq" or "aws",
    # in case of rabbitmq:
    "RMQ_USER" : "username",
    "RMQ_PASS" : "password",
    "RMQ_HOST" : "host, e.g. host.docker.internal or 127.0.0.1 or other",
    "RMQ_VHOST" : "e.g. etabotvhost",
    # in case of aws:
    "AWS_ACCESS_KEY_ID":"Amazon services access key id for SQS messenging"
    "AWS_SECRET_ACCESS_KEY":"Amazon services access key for SQS messenging"
    "AWS_SQS_REGION": "region, e.g. us-west-1",
    "CELERY_DEFAULT_QUEUE": "SQS queue name in AWS",
    "eta_crontab_args":<dictionary with crontab settings for example: 'eta_crontab_args':{'hour': 8}
                        see celery.schedules.crontab documentation for details>

    "AUTHLIB_OAUTH_CLIENTS": {
        "some_platform": {
            "client_id": "your_client_id_from_3dparty",
            "client_secret": "your_client_secret_from_3dparty",
            "access_token_url": "something_3dparty_token",
            "authorize_url": "something_3dparty_authorize",
            "client_kwargs": {
                "audience": "extra_params_if_needed",
                "scope": "extra_params_if_needed",
                "token_endpoint_auth_method": "extra_params_if_needed",
                "token_placement": "extra_params_if_needed",
                "prompt": "extra_params_if_needed"}

        "atlassian": {
            "client_id": "example",
            "client_secret": "example",
            "access_token_url": "https://auth.atlassian.com/oauth/token",
            "authorize_url": "https://auth.atlassian.com/authorize",
            "client_kwargs": {
                "audience": "api.atlassian.com",
                "scope": "read:jira-work read:jira-user write:jira-work offline_access",
                "token_endpoint_auth_method": "client_secret_post",
                "token_placement": "header",
                "prompt": "consent"}
        }            

}
```

Note: for accessing services on the same host as the docker container, use "host.docker.internal" for MacOS and Windows.
For Linux, until this is fixed (https://github.com/docker/libnetwork/pull/2348), use --network="host" in your docker run command, then 127.0.0.1 in your docker container will point to your docker host.


## django_keys.json - Django encryption keys used in development mode
```
{
    "DJANGO_SECRET_KEY":"Django secret key"
    "DJANGO_FIELD_ENCRYPT_KEY":"Django secret key used for encryption in databased fields"
}
```
run this from /etabotsite to generate a key:
```
$ python generate_key.py
```

## django_keys_prod.json
same as django_keys.json but keys for production. Keys will be checked against exposed dev keys from git repo.

## sys_email_settings.json - used for email communication setup
```
    "DJANGO_SYS_EMAIL": "username for email server",
    "DJANGO_SYS_EMAIL_PWD":"password for email server",
    "DJANGO_EMAIL_HOST":"email server host, e.g. smtp.sendgrid.net",
    "DJANGO_EMAIL_USE_TLS":bool for TLS,
    "DJANGO_EMAIL_PORT":email server port number port number,
    "DJANGO_EMAIL_TOKEN_EXPIRATION_PERIOD_S":Django email token expiration period in seconds (86400 = 24h)
```


### server end-point selection
By default, if you run server on MacOS (Darwin), it will detect you are in development mode and set host url to local_host_url (set in custom_settings.json or default value in settings.py) and set it correspondingly in UI API endpoint and email links. If OS other than Darwin, prod_host_url (set to value in custom_settings.json or default value in settings.py) will be used.


To modify the `/static/ng2_app/main.js` static file to point to API endpoint other than host urls as described above you can follow the commands below:
```
$ cd etabotapp/
$ python set_api_url.py static/ng2_app/ <end point url, e.g. http://app.etabot.ai:8000/api/>
```



#### Optinal: connecting ETA algorithm instead of a placeholder
```
$ cd etabotsite/
$ git submodule add <your git URL to repo called "etabot_algo">
$ git reset HEAD -- .gitmodules
$ git reset HEAD -- etabot_algo
```

The repo must have module ETApredict.py following pattern ETApredict_placeholder.py

#### Periodic tasks with Celery

Celery container will start automatically with Docker deployment.

For manual start: in a separate terminal start process with:
```
$ celery -A etabotsite worker -l info
```

in another seprate terminal start a process with:
```
celery -A etabotsite beat -l INFO
```


#### Installation issues

### Issue "ImportError: The curl client requires the pycurl library." 
can be resolved on Mac with:
```
pip uninstall pycurl
pip install --install-option="--with-openssl" --install-option="--openssl-dir=/usr/local/opt/openssl" pycurl
```

other issues with pycurl may be due to  MacOS depreciating open_ssl
fix: install open_ssl with brew

may need to: 

```sudo chown -R $(whoami) /usr/local/lib/pkgconfig /usr/local/sbin```
```brew install openssl```
openssl is keg-only, which means it was not symlinked into /usr/local,
because Apple has deprecated use of OpenSSL in favor of its own TLS and crypto libraries.

If you need to have openssl first in your PATH run:
```echo 'export PATH="/usr/local/opt/openssl/bin:$PATH"' >> ~/.bash_profile```

For compilers to find openssl you may need to set:
```export LDFLAGS="-L/usr/local/opt/openssl/lib"```
```export CPPFLAGS="-I/usr/local/opt/openssl/include"```

For pkg-config to find openssl you may need to set:
```export PKG_CONFIG_PATH="/usr/local/opt/openssl/lib/pkgconfig"```


### Issue "ERROR: Cannot uninstall 'certifi'. It is a distutils installed project and thus we cannot accurately determine which files belong to it which would lead to only a partial uninstall."
can be resolved with 
```
pip install -r requirements.txt --ignore-installed certifi
```
Or here is solution for all such packages:

```
pip install -r requirements.txt --ignore-installed
```
Or per package:

```
pip install --ignore-installed ${PACKAGE_NAME}
```

E.g.
```
pip install --ignore-installed certifi
```
### Celery issue with pycurl.
start python and make sure you can import pycurl
if not, try 
```

conda install pycurl```

### Networking errors
add the following lines in case you run into Networking errors:
Edit /etc/default/docker and add your DNS server to the following line:

Example 
DOCKER_OPTS="--dns 8.8.8.8 --dns 10.252.252.252"


#### Maintenance

To free up space from unused stale containers:
```
docker images -q --filter dangling=true | xargs docker rmi
```

### Docker version deployment
please follow these steps:

#### Docker deployment Prequisites:
* Have docker, docker compose installed
* Knowledge of Django and Nginx
* If needed add your dns to hosts for testing with your url locally, for example:
  ``` 
  $ sudo vi /etc/hosts
  ```
  Add the following line to the end of the file:
  ```
  127.0.0.1 <your web-app url, e.g. app.etabot.ai>
  ```

* Optionally to start, required for full operation:
- create/get the following json files in/etabotsite (see descriptions in "Settings jsons" section)
    1. custom_settings.json - general custom settings (end points, database, messenging service, etc)
    2. django_keys_prod.json - Django encryption keys used in production mode
    3. sys_email_settings.json - used for email communication setup
- git http url to an ETA algorithm

#### Bring up pmp services which include nginx and django
Clone the repo to your server
```
git clone https://github.com/ShanshanHe/pmp.git
```

### Follow steps in "Configure pmp" section in appendix

### Build docker images and create volumes
At the root directory, run the following commands:
```
$ docker-compose build --no-cache
$ docker-compose up --no-start --force-recreate
```

The two commands above will build two docker images: `pmp-nginx` and `pmp-django`, and then run both images as two containers. At the same time, they create two docker local volumes, you can check the volumes using the following command:

```
$ docker volume ls
DRIVER              VOLUME NAME
local               pmp_pmp-django-static
local               pmp_pmp-nginx-cert
```

In our nginx, we have SSL enabled, so please make sure you have certificates ready. Now we are going to create a temporary container to load the certificate files onto the `pmp_pmp-nginx-cert` volume for nginx to use. Volume data persists outside of a containers lifetime and so even when we have finished with this temporary volume the certificate files will still be there for the nginx service to see.
```
$ docker run --name temp-volume -v pmp_pmp-nginx-cert:/etc/ssl/certs busybox
```
Here we are creating the container `temp-volume` using the busybox base image and using the same named volume `pmp_pmp-nginx-cert` mounted to the same path in the container as the nginx service would.
Note: Using the same mount path is not necessary.
The previous command will create the container but it will exit immediately but we dont need it running to manage the volume.
We now copy our certificate files to the volume through this container. The following commands copy these certs and rename these files to the `pmp_pmp-nginx-cert` volume via the `temp_volume` container.

Security Note: for your production please generate your own pair of keys

```
$ docker cp nginx/certs/cert.pem temp-volume:/etc/ssl/certs/cert.pem
$ docker cp nginx/certs/key.pem temp-volume:/etc/ssl/certs/key.pem
```

### Running docker containers
Now we run the following commands again:
```
$ docker-compose build --no-cache
$ docker-compose up --force-recreate
```
Ensure all containers are up and running by:
```
$ docker ps
```
And you should see three containers running.

if you do not want celery container that runs periodic tasks - stop it by:
```
docker stop <container_id>
```
where <container_id> can be found from the earlier docker ps command

if you want to start the celery container on another machine, run this after images are built instead of docker-compose up
```
docker run pmp_celery
```

Vola, you successfully deployed your `pmp` project! Type the ip address of your server in your browser to visit the default `pmp` webpage. 

Hope you enjoy!
