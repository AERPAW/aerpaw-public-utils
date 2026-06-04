#Dockerfile for Ubuntu 22.04 container running Elasticsearch, Logstash & Kibana 8.10.2

#==================================================================================
# Base Image, update & install required/helpful packages
#==================================================================================
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y nano wget curl kafkacat net-tools iproute2 dnsutils iputils-ping jq sudo
RUN apt-get install -y openjdk-17-jdk
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install tcpdump
RUN apt-get clean

#==================================================================================
# Setup non-root container with passwordless sudo, sync GID & UID with account on host if needed
#==================================================================================
ARG GID=1000
ARG UID=1000
RUN addgroup --gid $GID elk
RUN adduser --uid $UID --gid $GID --disabled-password --gecos "" elk
RUN echo 'elk ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers
USER elk

#==================================================================================
# Download & extract ELK 8.10.2
#==================================================================================
RUN mkdir /home/elk/Downloads
WORKDIR /home/elk/Downloads

# Elasticsearch
RUN wget --progress=bar:force https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.10.2-linux-x86_64.tar.gz
RUN tar -zxf elasticsearch-8.10.2-linux-x86_64.tar.gz && mv elasticsearch-8.10.2 /home/elk/elasticsearch
RUN rm elasticsearch-8.10.2-linux-x86_64.tar.gz
ENV ES_HOME="/home/elk/elasticsearch"

# Kibana
RUN wget --progress=bar:force https://artifacts.elastic.co/downloads/kibana/kibana-8.10.2-linux-x86_64.tar.gz
RUN tar -zxf kibana-8.10.2-linux-x86_64.tar.gz && mv kibana-8.10.2 /home/elk/kibana
RUN rm kibana-8.10.2-linux-x86_64.tar.gz
ENV KB_HOME="/home/elk/kibana"

# Logstash
RUN wget --progress=bar:force https://artifacts.elastic.co/downloads/logstash/logstash-8.10.2-linux-x86_64.tar.gz
RUN tar -zxf logstash-8.10.2-linux-x86_64.tar.gz && mv logstash-8.10.2 /home/elk/logstash
RUN rm logstash-8.10.2-linux-x86_64.tar.gz
ENV LS_HOME="/home/elk/logstash"
#==================================================================================
# Modify config files
#==================================================================================
RUN cp $ES_HOME/config/elasticsearch.yml $ES_HOME/config/elasticsearch.yml.default
RUN sed -i '/^#network\.host:/s/.*/network\.host: 192\.168\.60\.201/' $ES_HOME/config/elasticsearch.yml

RUN cp $KB_HOME/config/kibana.yml $KB_HOME/config/kibana.yml.default
RUN sed -i '/^#server\.host:/s/.*/server\.host: 192\.168\.60\.201/' $KB_HOME/config/kibana.yml
RUN sed -i '/^#server\.name:/s/.*/server\.name: "AERPAW-Kibana"/' $KB_HOME/config/kibana.yml
RUN sed -i '/^#elasticsearch\.hosts:/s/.*/elasticsearch.hosts: ["http:\/\/192\.168\.60\.201:9200"]/' $KB_HOME/config/kibana.yml
RUN echo "xpack.fleet.enabled: false" >> $KB_HOME/config/kibana.yml
RUN echo "telemetry.optIn: false" >> $KB_HOME/config/kibana.yml

RUN cp $LS_HOME/config/logstash.yml $LS_HOME/config/logstash.yml.default
#==================================================================================
# Rest of initial setup must be done manually. Attempted to automate several times & could not get it to work - elastic would crash
# 1. Connect container to OVS
# 2. Start Elastic & enroll Kibana
#       $ES_HOME/bin/elasticsearch
#   b. Note password for elastic superuser, reset if needed with:
#       $ES_HOME/bin/elasticsearch-reset-password -u -elastic   #(Requires elasticsearch to be running)
# 3. Kill active elasticsearch process & restart in daemon mode (you can use start-elastic alias below)
# 4. Enroll Kibana with token from step 2
#       $KB_HOME/bin/kibana-setup --enrollment-token <token>
#   b. If previous token was lost or expired, generate a new token with:
#       $ES_HOME/bin/elasticsearch-create-enrollment-token -s kibana    #(Requires elasticsearch to be running)
# 5. Create Logstash pipelines
#==================================================================================s
# Install Kafka integration plugin for Logstash
#==================================================================================

WORKDIR /home/elk/logstash
RUN bin/logstash-plugin install logstash-integration-kafka

#==================================================================================
# Load AERPAW scripts/tools & persist home directory
#==================================================================================
WORKDIR /home/elk

RUN echo 'export ES_HOME="/home/elk/elasticsearch"' >> .profile
RUN echo 'export KB_HOME="/home/elk/kibana"' >> .profile
RUN echo 'export LS_HOME="/home/elk/logstash"' >> .profile

RUN echo 'alias start-elastic="$ES_HOME/bin/elasticsearch -d"' >> /home/elk/.bash_aliases
RUN echo 'alias start-kibana="$KB_HOME/bin/kibana &"' >> /home/elk/.bash_aliases
RUN echo 'alias start-logstash="$LS_HOME/bin/logstash &"' >> /home/elk/.bash_aliases

VOLUME /home/elk

