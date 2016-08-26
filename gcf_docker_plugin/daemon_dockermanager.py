#----------------------------------------------------------------------
# Copyright (c) 2016 Inria/iMinds by Arthur Garnier
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and/or hardware specification (the "Work") to
# deal in the Work without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Work, and to permit persons to whom the Work
# is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Work.
#
# THE WORK IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE WORK OR THE USE OR OTHER DEALINGS
# IN THE WORK.
#----------------------------------------------------------------------


from gcf_to_docker import DockerManager
import Pyro4
from optparse import OptionParser
import logging

Pyro4.config.THREADPOOL_SIZE=500
Pyro4.config.THREADPOOL_ALLOW_QUEUE = True

parser = OptionParser()
parser.add_option("--host", dest="host", help="Accesssible IP from the AM", metavar="IP")
parser.add_option("--password", dest="password", help="Passphrase to preventing arbitrary connections", metavar="PASSPHRASE")
parser.add_option("--port", dest="port", default=11999, help="Port to listen to", metavar="PORT")
(options, args) = parser.parse_args()

logging.basicConfig()
logger = logging.getLogger("DockerManager Daemon")
logger.setLevel(10)

if not options.host:
    logger.error("--host option is required. Most of the time it is the public or private IP of the host")
    exit(1)

if not options.port:
    port = 11999
else:
    port = options.port

daemon = Pyro4.Daemon(port=int(options.port), host=options.host)

if not options.password:
    logger.warning("No password provided, anyone on the network (all the Internet if 'host' is a public IP) could use this DockerManager")
else:
    daemon._pyroHmacKey = options.password

uri = daemon.register(DockerManager, objectId="dockermanager")
logger.info("Start listenning on : "+str(uri))
daemon.requestLoop()
