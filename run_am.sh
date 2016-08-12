#! /bin/sh

export PYTHONPATH="${PYTHONPATH}:$(pwd)/gcf_docker_plugin/"
python2 geni-tools/src/gcf-am.py -V 3 -c gcf_docker_plugin/gcf_config
