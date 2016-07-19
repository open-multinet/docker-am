import subprocess
import re
import os
import uuid
import threading
import sys
import json

class DockerManager():
    
    START_EXPOSING_PORT=12000
    locked_port = list()
    lock = threading.Lock()

    def numberRunningContainer(self):
        cmd = "docker ps | grep -v '^CONTAINER' | wc -l"
        output = subprocess.check_output(['bash', '-c', cmd])
        output=output.strip().decode('utf-8')
        return output

    def getNextPort(self):
        if self.numberRunningContainer() == 0:
            return START_EXPOSING_PORT
        else:
            cmd = "docker ps --format {{.Ports}} | sort"
            output = subprocess.check_output(['bash', '-c', cmd])
            output=output.strip().decode('utf-8')
            expected = 12000
            for line in output.split('\n'):
                m = re.search(':([0-9]*)->', line)
                if m!=None:
                    current = int(m.group(1))
                else:
                    current = None
                if current != expected and expected not in DockerManager.locked_port:
                    return expected
                else:
                    expected+=1
        while expected in DockerManager.locked_port:
            expected += 1
        return expected

    def reserveNextPort(self):
        DockerManager.lock.acquire()
        port = self.getNextPort()
        DockerManager.locked_port.append(port)
        DockerManager.lock.release()
        return port

    def startNew(self, id=None, sliver_type=None, ssh_port=None):
        if ssh_port is None:
            ssh_port = reserveNextPort()
        uid = str(uuid.uuid4()) if id==None else id
        if sliver_type=="docker-container":
            cmd = "docker run -d --name "+uid+" -p " + str(ssh_port) + ":22 -t jessie_gcf_ssh 2> /dev/null"
        elif sliver_type == "docker-container_100M":
            cmd = "docker run -d --name "+uid+" -p " + str(ssh_port) + ":22 -m 100M -t jessie_gcf_ssh 2> /dev/null"
        try:
            subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
        except Exception as e:
            build = "docker build -t jessie_gcf_ssh " + os.path.dirname(os.path.realpath(__file__))
            subprocess.check_output(['bash', '-c', build]).decode('utf-8').strip()
            subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
        DockerManager.locked_port.remove(ssh_port)
        return uid

    def stopContainer(self, id):
        cmd = "docker stop " + str(id)
        try:
            subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
            return True
        except Exception as e:
            return False

    def removeContainer(self, id):
        cmd = "docker rm -f " + str(id)
        try:
            subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
            return True
        except Exception as e:
            return False

    def resetContainer(self, id):
        stopContainer(id)
        removeContainer(id)
        startNew(id)

    def setupUser(self, id, username, ssh_keys):
        cmd_create_user = "docker exec "+id+" sh -c 'grep \'^"+username+":\' /etc/passwd ; if [ $? -ne 0 ] ; then useradd -m -d /home/"+username+" "+ username+" && mkdir -p /home/"+username+"/.ssh ; fi'"
        subprocess.check_output(['bash', '-c', cmd_create_user])
        cmd_add_key = "docker exec "+ id + " sh -c \"echo '' > /home/"+username+"/.ssh/authorized_keys\""
        subprocess.check_output(['bash', '-c', cmd_add_key])
        for key in ssh_keys:
            cmd_add_key = "docker exec "+ id + " sh -c \"echo '"+key+"' >> /home/"+username+"/.ssh/authorized_keys\""
            subprocess.check_output(['bash', '-c', cmd_add_key])
        cmd_set_rights = "docker exec "+ id + " sh -c 'chown -R "+username+": /home/"+username+" && chmod 700 /home/"+username+"/.ssh && chmod 644 /home/"+username+"/.ssh/authorized_keys'"
        subprocess.check_output(['bash', '-c', cmd_set_rights])

    def setupContainer(self, id, username, ssh_keys):
        self.setupUser(id, username, ssh_keys)

    def getPort(self, id):
        cmd = "docker ps --format {{.Names}}//{{.Ports}} --no-trunc | grep "+id
        output = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        m = re.search(':([0-9]*)->', output)
        if m!=None:
            return int(m.group(1))
        else:
            return None

    def getUsers(self, id):
        cmd = "docker exec "+id+" find /home -name \"authorized_keys\" | grep \"/home/.*/.ssh/authorized_keys\" | cut -d'/' -f 3"
        out = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        return filter(None, out.split('\n')) #Remove empty elements

    def checkDocker(self):
        cmd = "docker ps"
        try:
            subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        except Exception, e:
            sys.stderr.write('Docker is not installed OR this user is not in the docker group OR the docker daemon is not started\n')
            exit(1)
            
    def getIpV6(self, id):
        cmd = "docker inspect "+id
        output = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        output = json.loads(output)
        return output[0]['NetworkSettings']['GlobalIPv6Address']
