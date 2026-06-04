This directory contains files for the Prometheus Node Exporter container.
This container exports metrics of its host on port 9100.

To build:
`sudo docker build --network=host -t trinkey-reader -f Dockerfile.trinkey .`
To run:
`sudo docker compose up -d`
