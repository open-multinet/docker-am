from gcf_to_docker import DockerManager
import Pyro4

Pyro4.config.THREADPOOL_SIZE=100
Pyro4.config.THREADPOOL_ALLOW_QUEUE = True

daemon = Pyro4.Daemon(port=11999)
uri = daemon.register(DockerManager, objectId="test")
print uri
daemon.requestLoop()
