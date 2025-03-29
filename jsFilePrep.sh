#!/bin/bash

echo move the js static files from frontend directory to django project.
cp -R /usr/src/app/ng_app/dist/index.html /usr/src/app/server/etabotsite/templates/
cp -R /usr/src/app/ng_app/dist/. /usr/src/app/server/etabotsite/etabotapp/static/ng_app_js/

search="bundle.js"
replace="bundle.js' %}"
sed "s|${search}|${replace}|g" /usr/src/app/server/etabotsite/templates/index.html > /usr/src/app/server/etabotsite/templates/tmp.html
mv /usr/src/app/server/etabotsite/templates/tmp.html /usr/src/app/server/etabotsite/templates/index.html

search="bundle.css"
replace="bundle.css' %}"
sed "s|${search}|${replace}|g" /usr/src/app/server/etabotsite/templates/index.html > /usr/src/app/server/etabotsite/templates/tmp.html
mv /usr/src/app/server/etabotsite/templates/tmp.html /usr/src/app/server/etabotsite/templates/index.html

search="polyfills."
replace="{% static 'ng_app_js/polyfills."
sed "s|${search}|${replace}|g" /usr/src/app/server/etabotsite/templates/index.html > /usr/src/app/server/etabotsite/templates/tmp.html
mv /usr/src/app/server/etabotsite/templates/tmp.html /usr/src/app/server/etabotsite/templates/index.html

search="inline."
replace="{% static 'ng_app_js/inline."
sed "s|${search}|${replace}|g" /usr/src/app/server/etabotsite/templates/index.html > /usr/src/app/server/etabotsite/templates/tmp.html
mv /usr/src/app/server/etabotsite/templates/tmp.html /usr/src/app/server/etabotsite/templates/index.html

search="vendor."
replace="{% static 'ng_app_js/vendor."
sed "s|${search}|${replace}|g" /usr/src/app/server/etabotsite/templates/index.html > /usr/src/app/server/etabotsite/templates/tmp.html
mv /usr/src/app/server/etabotsite/templates/tmp.html /usr/src/app/server/etabotsite/templates/index.html

search="main."
replace="{% static 'ng_app_js/main."
sed "s|${search}|${replace}|g" /usr/src/app/server/etabotsite/templates/index.html > /usr/src/app/server/etabotsite/templates/tmp.html
mv /usr/src/app/server/etabotsite/templates/tmp.html /usr/src/app/server/etabotsite/templates/index.html

search="href=\"styles."
replace="href=\"{% static 'ng_app_js/styles."
sed "s|${search}|${replace}|g" /usr/src/app/server/etabotsite/templates/index.html > /usr/src/app/server/etabotsite/templates/tmp.html

{ echo -n '{% load static %}'; cat /usr/src/app/server/etabotsite/templates/tmp.html; } > /usr/src/app/server/etabotsite/templates/index.html
#add="\{\% load staticfiles \%\}"
#sed "1s|^|${add}|g" /usr/src/app/server/etabotsite/templates/tmp.html /usr/src/app/server/etabotsite/templates/index.html
