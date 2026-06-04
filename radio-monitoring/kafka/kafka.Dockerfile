  #Dockerfile for Ubuntu 22.04 container running Apache Kafka 3.5.1

#==================================================================================
# Base Image, update & install required/helpful packages
#==================================================================================
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y nano wget curl kafkacat net-tools iproute2 dnsutils iputils-ping lynx git sudo
RUN apt-get install -y openjdk-11-jdk

#==================================================================================
# Setup non-root container with passwordless sudo, sync GID & UID with account on host if needed
#==================================================================================
ARG GID=1000
ARG UID=1000
RUN addgroup --gid $GID kafka
RUN adduser --uid $UID --gid $GID --disabled-password --gecos "" kafka
RUN echo 'kafka ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers
USER kafka

#==================================================================================
# Download & extract Kafka 3.5.1
#==================================================================================
RUN mkdir /home/kafka/Downloads
WORKDIR /home/kafka/Downloads
RUN wget https://downloads.apache.org/kafka/3.5.1/kafka-3.5.1-src.tgz
RUN tar -zxvf kafka-3.5.1-src.tgz && mv kafka-3.5.1-src /home/kafka/kafka
RUN rm -rf /home/kafka/Downloads
ENV KAFKA_HOME="/home/kafka/kafka"

#==================================================================================
# Build Kafka
#==================================================================================
WORKDIR /home/kafka/kafka
RUN ./gradlew jar -PscalaVersion=2.13.10

#==================================================================================
# Load AERPAW scripts/tools, initialize Kafka, & persist directory
#==================================================================================
WORKDIR /home/kafka

RUN echo "alias ktopics='$KAFKA_HOME/bin/kafka-topics.sh --bootstrap-server localhost:9092'" >> .bash_aliases
RUN echo "alias kwriter='$KAFKA_HOME/bin/kafka-console-producer.sh --bootstrap-server localhost:9092'" >> .bash_aliases
RUN echo "alias kreader='$KAFKA_HOME/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092'" >> .bash_aliases
RUN echo "alias start-kafka='$KAFKA_HOME/bin/kafka-server-start.sh $KAFKA_HOME/config/kraft/server.properties &'" >> .bash_aliases
RUN echo "alias stop-kafka='$KAFKA_HOME/bin/kafka-server-stop.sh'" >> .bash_aliases

RUN cp $KAFKA_HOME/config/kraft/server.properties $KAFKA_HOME/config/kraft/server.properties.default
ENV KAFKA_CONF="$KAFKA_HOME/config/kraft/server.properties"
RUN sed -i '/^controller\.quorum\.voters=/s/.*/controller\.quorum\.voters=1@192.168.60.202:9093/' $KAFKA_CONF
RUN sed -i '/^advertised\.listeners=/s/.*/advertised\.listeners=PLAINTEXT:\/\/192.168.60.202:9092/' $KAFKA_CONF
RUN sed -i '/^log\.dirs=/s/.*/log\.dirs=\/home\/kafka\/kraft-combined-logs/' $KAFKA_CONF

RUN $KAFKA_HOME/bin/kafka-storage.sh format -t $($KAFKA_HOME/bin/kafka-storage.sh random-uuid) -c $KAFKA_CONF

RUN echo 'export KAFKA_HOME="/home/kafka/kafka"' >> .profile
RUN echo 'export KAFKA_CONF="$KAFKA_HOME/config/kraft/server.properties"' >> .profile

VOLUME /home/kafka

