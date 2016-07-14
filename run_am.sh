#! /bin/sh

PYTHONPATH="${PYTHONPATH}:$(pwd)/gcf_testbedname_plugin"
echo $PYTHONPATH
python2 geni-tools/src/gcf-am.py -V 3 -c gcf_testbedname_plugin/gcf_config
