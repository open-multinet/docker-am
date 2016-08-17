from gcf_to_docker import DockerManager
import Pyro4
from optparse import OptionParser
import logging

Pyro4.config.THREADPOOL_SIZE=100
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


daemon = Pyro4.Daemon(port=11999, host="193.190.127.251")

if not options.password:
    logger.warning("No password provided, anyone on the network (all the Internet if 'host' is a public IP) could use this DockerManager")
else:
    daemon._pyroHmacKey = options.password

uri = daemon.register(DockerManager, objectId="dockermanager")
logger.info("Start listenning on : "+str(uri))
daemon.requestLoop()
