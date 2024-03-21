FROM node:18

ENV NODE_OPTIONS=--openssl-legacy-provider

RUN mkdir /opt/navigator
COPY ./nav-app ./opt/navigator
WORKDIR /opt/navigator

RUN npm install
RUN npm install -g @angular/cli
RUN ng build --configuration production --aot=false --build-optimizer=false
RUN tar -zcvf dist.tar.gz dist/
