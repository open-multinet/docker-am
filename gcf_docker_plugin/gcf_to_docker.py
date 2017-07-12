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

import subprocess
import re
import os
import uuid
import threading
import sys
import json
import random
import tempfile
import hashlib
import zipfile
import shutil
import time
import logging
import Pyro4
from urllib2 import urlopen, URLError, HTTPError

locked_port = list()
lock = threading.Lock()
building = dict()

@Pyro4.expose
class DockerManager(object):
    def __init__(self, default_image="jessie_gcf_ssh"):
        self.default_image = default_image

    #Return the number of running containers
    def getRunningContainerCount(self):
        cmd = "docker ps | grep -v '^CONTAINER' | wc -l"
        output = subprocess.check_output(['bash', '-c', cmd])
        output=output.strip().decode('utf-8')
        return int(output)

    #Return the next port available on the host using netstat
    #starting_port : From which port start to check
    def getNextPort(self, starting_port):
        _locked_port = list(locked_port)
        cmd = "netstat -ant 2>/dev/null | awk '{print $4}' | grep -o \":[0-9]\\+$\" | grep -o [0-9]* | sort -n | uniq"
        output = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        expected = starting_port
        busy = list()
        for line in output.split('\n'):
            if int(line) >= starting_port:
                busy.append(int(line))
        while expected in busy or expected in _locked_port:
            expected+=1
        return expected

    #Get the next port with a Lock (avoid concurrency issue) and add it to the locked_port array
    def reserveNextPort(self, starting_port):
        lock.acquire()
        port = self.getNextPort(starting_port)
        locked_port.append(port)
        lock.release()
        return port

    #Start a new container
    #id : Specific name to give to the container
    #sliver_type : Kind of container (limited to 100M memory for example)
    #ssh_port : Port to bind to port 22
    #mac_address : Defined mac address of the container
    #image : Specific image to install (See processImage() documentation)
    def startNew(self, id=None, sliver_type=None, ssh_port=None, mac_address=None, image=None):
        if ssh_port is None:
            ssh_port = self.reserveNextPort()
        uid = str(uuid.uuid4()) if id==None else id
        imageName = self.default_image
        if image is not None:
            imageName=self.processImage(image)
            if not re.match(r'[a-fA-F0-9]{40}', imageName) and image.split("::")[1]!=imageName: #An error occured during processImage
                raise Exception("Invalid image name: %s" % imageName)
        if sliver_type=="docker-container":
            cmd = "docker run -d --mac-address "+mac_address+" --name "+uid+" -p " + str(ssh_port) + ":22 -P -t "+imageName+" 2>&1"
        elif sliver_type == "docker-container_100M":
            cmd = "docker run -d --mac-address "+mac_address+" --name "+uid+" -p " + str(ssh_port) + ":22 -m 100M -P -t "+imageName+" 2>&1"
        elif sliver_type == "docker-container-with-tunnel":
            cmd = "docker run -d --mac-address "+mac_address+" --name "+uid+" -p " + str(ssh_port) + ":22 --cap-add=NET_ADMIN --device=/dev/net/tun -P -t "+imageName+" 2>&1"
        else:
            raise Exception("Internal error: no known sliver_type chosen: %s" % sliver_type)
        try:
            subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
        except Exception as e:
            if "Unable to find image" not in e.output:
                return e.output
            #This should only be reached if the default_image itself is not yet built.
            #  So we try building it, then retry the command, and fail if that still fails
            build = "docker build -t "+self.default_image+" " + os.path.dirname(os.path.realpath(__file__))
            try:
                if building.get(imageName, None) is None:
                    building[imageName] = threading.Lock()
                building[imageName].acquire() #Don't run multiple build at the same time
                subprocess.check_output(['bash', '-c', build]).decode('utf-8').strip()
                subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
            except subprocess.CalledProcessError, e:
                return e.output
            finally:
                building[imageName].release()
        if ssh_port in locked_port:
            i=0
            while self.isContainerUp(ssh_port) == False: #Wait the container to listen before release the port
                i+=1
                time.sleep(1)
                if i==45:
                    return "Container not up after 45 seconds. Something went wrong"
            locked_port.remove(ssh_port)
        return True

    def restartContainer(self, id):
        cmd = "docker restart "+str(id)+" 2>&1"
        try:
            subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
            return True
        except Exception as e:
            return False

    #Remove a port from locked ports list
    #Have to be done if container start failed
    def releasePort(self, port):
        if port in locked_port:
            locked_port.remove(port)

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
            return e.output

    #Check if a container is up using netstat
    #In fact, check if the port is listenning
    def isContainerUp(self, port):
        cmd = "netstat -ant 2>/dev/null | awk '{print $4}' | grep -o \":[0-9]\\+$\" | grep -o [0-9]* | grep -x "+str(port)
        try:
            out=subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
            return True
        except subprocess.CalledProcessError:
            return False

    def resetContainer(self, id):
        self.stopContainer(id)
        self.removeContainer(id)
        self.startNew(id)

    #Setup a user in the container
    #ssh_keys : Array of public ssh keys to allow (authorized_keys file)
    def setupUser(self, id, username, ssh_keys):
        try:
            cmd_create_user = "docker exec "+id+" sh -c 'grep \'^"+username+":\' /etc/passwd ; if [ $? -ne 0 ] ; then useradd -m -d /home/"+username+" "+ username+" && mkdir -p /home/"+username+"/.ssh ; fi' 2>&1"
            out = subprocess.check_output(['bash', '-c', cmd_create_user])
            cmd_add_key = "docker exec "+ id + " sh -c \"echo '' > /home/"+username+"/.ssh/authorized_keys\" 2>&1"
            out = subprocess.check_output(['bash', '-c', cmd_add_key])
            for key in ssh_keys:
                cmd_add_key = "docker exec "+ id + " sh -c \"echo '"+key+"' >> /home/"+username+"/.ssh/authorized_keys\" 2>&1"
                out = subprocess.check_output(['bash', '-c', cmd_add_key])
            cmd_set_rights = "docker exec "+ id + " sh -c 'chown -R "+username+": /home/"+username+" && chmod 700 /home/"+username+"/.ssh && chmod 644 /home/"+username+"/.ssh/authorized_keys' 2>&1"
            out = subprocess.check_output(['bash', '-c', cmd_set_rights])
            return True
        except subprocess.CalledProcessError, e:
            return e.output

    def setupContainer(self, id, user_keys_dict):
        for username, ssh_keys in user_keys_dict.items():
            res = self.setupUser(id, username, ssh_keys)
            if res is not True:
                return res
        return True

    #Get the ssh_port used by a specific container
    def getPort(self, id):
        cmd = "docker ps --format {{.Names}}//{{.Ports}} --no-trunc | grep "+id
        output = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        m = re.search(':([0-9]*)->', output)
        if m!=None:
            return int(m.group(1))
        else:
            return None

    #Get list of user with an account in the container (with a home and authorized ssh key)
    def getUsers(self, id):
        cmd = "docker exec "+id+" find /home -name \"authorized_keys\" | grep \"/home/.*/.ssh/authorized_keys\" | cut -d'/' -f 3"
        out = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        return filter(None, out.split('\n')) #Remove empty elements

    #Check if docker is installed and accessible by the AM
    def checkDocker(self):
        cmd = "docker ps"
        try:
            subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        except Exception, e:
            sys.stderr.write('Docker is not installed OR this user is not in the docker group OR the docker daemon is not started\n')
            exit(1)

    #Get IPv6 of a container
    def getIpV6(self, id):
        cmd = "docker inspect "+id
        output = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
        output = json.loads(output)
        return output[0]['NetworkSettings']['GlobalIPv6Address']

    #Predict Ipv6 using the ipv6 prefix and the mac address
    def computeIpV6(self, prefix, mac):
        ipv6 = prefix
        parts=mac.split(':')
        for i in range(0, len(parts), 2):
            ipv6 += str(parts[i])+str(parts[i+1])+":"
        ipv6 = ipv6[:-1]
        return ipv6

    #Returns a random Mac Address with the same prefix as Docker (02:42:ac:11)
    def randomMacAddress(self):
        mac = [0x02, 0x42, 0xac, 0x11, random.randint(0x00, 0xff), random.randint(0x00, 0xff)]
        return ':'.join(map(lambda x: "%02x" % x, mac))

    #Delete a docker built image
    def deleteImage(self, name):
        if name.startswith("urn") and len(name.split("::"))==2:
            name = hashlib.sha1(name).hexdigest()
        cmd = "docker rmi -f "+name
        subprocess.check_output(['bash', '-c', cmd])

    #Build a docker hub image with an OpenSSH server
    def buildSshImage(self, name):
        try:
            cmd = "mktemp"
            tmpfile = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
            cmd = "echo 'FROM " +name+"' > "+tmpfile
            out = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
            cmd = "cat "+os.path.dirname(os.path.abspath(__file__))+"/Dockerfile_template >> "+tmpfile
            out = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
            cmd = "docker build -t "+name+" --force-rm -f "+tmpfile+" /tmp 2>&1"
            out = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
            cmd = "rm -f "+tmpfile
            out = subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
            return True
        except subprocess.CalledProcessError, e:
            return e.output

    #Build the image given in parameter
    #image : could be URL to a DockerFile or a zip or just the name from Docker Hub (eg debian:jessie). Always starts with "foo::" (foo is usually the slice urn) to make the name "private"
    def processImage(self, image):
        fullName = image.split("::")
        user = fullName[0]
        imageName = fullName[1]
        if imageName.startswith("http://") or imageName.startswith("https://"):
            image = hashlib.sha1(image).hexdigest() #Hash the "URN::imagename" to avoid issue with docker
            cmd = "docker images --no-trunc --format {{.Repository}} | grep -x "+image
            try:
                subprocess.check_output(['bash', '-c', cmd]).strip().decode('utf-8')
            except subprocess.CalledProcessError: #Image doesn't exists
                out = self.buildExternalImage(imageName, image)
                if out is not True:
                    return out
            return image
        else: #Docker hub image
            #Check if image exists
            cmd = "docker images --no-trunc --format {{.Repository}} | grep -x "+imageName
            try:
                subprocess.check_output(['bash', '-c', cmd])
            except subprocess.CalledProcessError:
                if building.get(image, None) is None:
                    building[image] = threading.Lock()
                building[image].acquire()
                out = self.buildSshImage(imageName)
                if out is not True:
                    return out
                building[image].release()
            return imageName

    #Build image from a URL and set the name "fullname" in docker
    def buildExternalImage(self, url, fullName):
        tmpdir = tempfile.mkdtemp()
        self.dlfile(url, tmpdir)
        if os.path.basename(url) == "Dockerfile": #If the target URL is a simple DockerFile
            pass
        elif os.path.basename(url).split(".")[-1] == "zip": #A zip containing /Dockerfile or /folder/Dockerfile (and other things)
            zipfile.ZipFile(tmpdir+"/"+os.path.basename(url)).extractall(tmpdir)
            if len(os.listdir(tmpdir))==2 and "Dockerfile" not in os.listdir(tmpdir): #If the zip contains a subfolder
                cmd = "mv "+tmpdir+"/*/* "+tmpdir
                subprocess.check_output(['bash', '-c', cmd])
        else:
            shutil.rmtree(tmpdir)
            return "Error : Unsupported URL"
        #Fix CMD to start SSH daemon and the original command
        cmd = ""
        for line in open(tmpdir+"/Dockerfile"):
            if line.startswith("CMD "):
                cmd = line.strip()[4:]
        if len(cmd) > 0:
            if cmd.startswith("[") and cmd.endswith("]"): #if CMD looks like "CMD ["nginx", "-g"]"
                cmd = cmd[1:-1]
                index = 0
                shell_cmd=""
                while index != -1:
                    next_index = cmd.find("\"", index+1)
                    shell_cmd +=" "+cmd[index:next_index+1]
                    index=cmd.find("\"", next_index+1)
                    new_cmd = "CMD sh -c '"+shell_cmd+" & /usr/sbin/sshd -D'"
            else: #if CMD looks like "CMD nginx -g"
                new_cmd = "CMD sh -c '"+cmd+" & /usr/sbin/sshd -D'"
        else: #If no CMD in the Dockerfile
            new_cmd = "CMD [\"/usr/sbin/sshd\", \"-D\"]"
        with open(tmpdir+"/Dockerfile", 'a') as fo:
            with open(os.path.dirname(os.path.abspath(__file__))+"/Dockerfile_template", 'r') as fi:
                fo.write(fi.read())
        cmd = "sed -i 's/CMD.*//g' "+tmpdir+"/Dockerfile"
        subprocess.check_output(['bash', '-c', cmd])
        with open(tmpdir+"/Dockerfile", 'a') as fo:
            fo.write(new_cmd)
        cmd = "docker build -t "+fullName+" --force-rm -f "+tmpdir+"/Dockerfile "+tmpdir+" 2>&1"
        try:
            subprocess.check_output(['bash', '-c', cmd])
        except subprocess.CalledProcessError, e:
            shutil.rmtree(tmpdir)
            return e.output
        shutil.rmtree(tmpdir)
        return True

    #Download a file to the given path
    def dlfile(self, url, dest):
        try:
            f = urlopen(url)
            # Open local file for writing
            with open(dest+"/"+os.path.basename(url), "wb") as local_file:
                local_file.write(f.read())
        #handle errors
        except HTTPError, e:
            logging.getLogger('gcf.am3').error("HTTP Error:", e.code, url)
        except URLError, e:
            logging.getLogger('gcf.am3').error("HTTP Error:", e.code, url)

    #Extract a tar.gz file given to the install_path in the container id
    def installCommand(self, id, url, install_path):
        cmd_docker = "docker exec "+id+" "
        filename = os.path.basename(url)
        ext = os.path.basename(url).split(".")[-1]
        cmd = cmd_docker+"mkdir -p "+install_path+" 2>&1"
        try:
            subprocess.check_output(['bash', '-c', cmd])
            cmd = cmd_docker+"curl -fsS -o "+install_path+"/"+filename+" "+url+" 2>&1"
            subprocess.check_output(['bash', '-c', cmd])
            if filename.split(".")[-1] == "gz" and filename.split(".")[-2] == "tar": # tar.gz file
                cmd = cmd_docker+"tar xzf "+install_path+"/"+filename+" -C "+install_path+" 2>&1"
                subprocess.check_output(['bash', '-c', cmd])
        except subprocess.CalledProcessError as e:
            return e.output.strip()
        return True

    #Executes the command cmd with the shell 'shell' in the container id
    #Creates 3 files in /tmp of the container : startup-[0-9].(status|txt|sh)
    #.sh contains the command executed
    #.status contains the return status of the command
    #.txt return the output
    def executeCommand(self, id, shell, cmd):
        cmd_docker = "docker exec "+id+" "
        log_dir = "/tmp/"
        if shell not in ['sh', 'bash']:
            cmd = cmd_docker+"sh -c 'echo \"Invalid shell\" >> /tmp/execute.log '"
            subprocess.check_output(['bash', '-c', cmd])
            return
        try:
            list_startup = cmd_docker+"sh -c 'ls "+log_dir+" | grep startup-.*.sh | grep -o [0-9]*'"
            out = subprocess.check_output(['bash', '-c', list_startup]).strip().split('\n')
            next_nb = int(max(out))+1
        except subprocess.CalledProcessError as e:
            next_nb = 0
        tmp = tempfile.mkstemp()[1]
        with open(tmp, 'w') as local:
            local.write(cmd)
        cmd = "docker cp "+tmp+" "+id+":/"+log_dir+"startup-"+str(next_nb)+".sh"
        try:
            subprocess.check_output(['bash', '-c', cmd])
            os.remove(tmp)
            cmd = cmd_docker+"sudo sh -c '"+shell+" "+log_dir+"startup-"+str(next_nb)+".sh 2>&1 > "+log_dir+"startup-"+str(next_nb)+".txt'"
            subprocess.check_output(['bash', '-c', cmd])
            cmd = cmd_docker+"sh -c 'echo \"0\" > "+log_dir+"startup-"+str(next_nb)+".status'"
            subprocess.check_output(['bash', '-c', cmd])
        except subprocess.CalledProcessError as e:
            cmd = cmd_docker+"sh -c 'echo \""+str(e.returncode)+"\" > "+log_dir+"startup-"+str(next_nb)+".status'"
            subprocess.check_output(['bash', '-c', cmd])
