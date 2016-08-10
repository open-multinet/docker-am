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
from urllib2 import urlopen, URLError, HTTPError

locked_port = list()
lock = threading.Lock()
building = dict()

class DockerManager():


    def numberRunningContainer(self):
        cmd = "docker ps | grep -v '^CONTAINER' | wc -l"
        output = subprocess.check_output(['bash', '-c', cmd])
        output=output.strip().decode('utf-8')
        return output

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

    def reserveNextPort(self, starting_port):
        lock.acquire()
        port = self.getNextPort(starting_port)
        locked_port.append(port)
        lock.release()
        return port

    #image : Specific image to install, could be URL to a DockerFile or a zip or just the name from Docker Hub (eg debian:jessie). Always starts with "username::" (replace username)
    def startNew(self, id=None, sliver_type=None, ssh_port=None, mac_address=None, image=None):
        if ssh_port is None:
            ssh_port = reserveNextPort()
        uid = str(uuid.uuid4()) if id==None else id
        imageName = "jessie_gcf_ssh" #Default
        if image is not None:
            imageName=self.processImage(image)
            if not re.match(r'[a-fA-F0-9]{40}', imageName) and image.split("::")[1]!=imageName: #An error occured during processImage
                return imageName
        if sliver_type=="docker-container":
            cmd = "docker run -d --mac-address "+mac_address+" --name "+uid+" -p " + str(ssh_port) + ":22 -P -t "+imageName+" 2>&1"
        elif sliver_type == "docker-container_100M":
            cmd = "docker run -d --mac-address "+mac_address+" --name "+uid+" -p " + str(ssh_port) + ":22 -m 100M -P -t "+imageName+" 2>&1"
        try:
            subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
        except Exception as e:
            if "Unable to find image" not in e.output:
                return e.output
            build = "docker build -t jessie_gcf_ssh " + os.path.dirname(os.path.realpath(__file__))
            try:
                subprocess.check_output(['bash', '-c', build]).decode('utf-8').strip()
                subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
            except subprocess.CalledProcessError, e:
                return e.output
        if ssh_port in locked_port:
            i=0
            while self.isContainerUp(ssh_port) == False:
                i+=1
                time.sleep(1)
                if i==45:
                    return "Container not up after 45 seconds. Something went wrong"
            locked_port.remove(ssh_port)
        return True

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

    def isContainerUp(self, port):
        cmd = "netstat -ant 2>/dev/null | awk '{print $4}' | grep -o \":[0-9]\\+$\" | grep -o [0-9]* | grep -x "+str(port)
        try:
            out=subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
            return True
        except subprocess.CalledProcessError:
            return False
        
    def resetContainer(self, id):
        stopContainer(id)
        removeContainer(id)
        startNew(id)

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

    def setupContainer(self, id, username, ssh_keys):
        return self.setupUser(id, username, ssh_keys)

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

    def computeIpV6(self, prefix, mac):
        ipv6 = prefix
        parts=mac.split(':')
        for i in range(0, len(parts), 2):
            ipv6 += str(parts[i])+str(parts[i+1])+":"
        ipv6 = ipv6[:-1]
        return ipv6

    """Returns a completely random Mac Address"""
    def randomMacAddress(self): 
        mac = [0x02, 0x42, 0xac, 0x11, random.randint(0x00, 0xff), random.randint(0x00, 0xff)]
        return ':'.join(map(lambda x: "%02x" % x, mac))

    def deleteImage(self, name):
        if name.startswith("urn") and len(name.split("::"))==2:
            name = hashlib.sha1(name).hexdigest()
        cmd = "docker rmi -f "+name
        subprocess.check_output(['bash', '-c', cmd])
            
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


    def processImage(self, image):
        fullName = image.split("::")
        user = fullName[0]
        imageName = fullName[1]
        if imageName.startswith("http://") or imageName.startswith("https://"):
            image = hashlib.sha1(image).hexdigest()
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

    def buildExternalImage(self, url, fullName):
        tmpdir = tempfile.mkdtemp()
        self.dlfile(url, tmpdir)
        if os.path.basename(url) == "Dockerfile":
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
        

    def dlfile(self, url, dest):
        try:
            f = urlopen(url)
            # Open local file for writing
            with open(dest+"/"+os.path.basename(url), "wb") as local_file:
                local_file.write(f.read())
        #handle errors
        except HTTPError, e:
            print "HTTP Error:", e.code, url
        except URLError, e:
            print "URL Error:", e.reason, url
