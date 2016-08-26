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

from __future__ import absolute_import
from gcf.geni.am.resource import Resource
from extendedresource import ExtendedResource

from lxml import etree
import subprocess

class ResourceExample(ExtendedResource):

    SLIVER_TYPE = "myresourceexample"
    
    def __init__(self, rid, host="MYDOMAIN.com"):
        super(ExtendedResource, self).__init__(rid, self.SLIVER_TYPE)
        self.users=dict()
        self.ssh_port=22
        self.error = ""
        self.host = host

    def genAdvertNode(self, _urn_authority, _my_urn):
        r = super(ResourceExample, self).genAdvertNode(_urn_authority, _my_urn)
        etree.SubElement(r, "sliver_type").set("name", self.SLIVER_TYPE)
        return r

    def getResource(self, component_id=None):
        if component_id is not None:
            if component_id != self.id:
                return None
        return self

    def deallocate(self):
        self.available = True
        self.users = dict()

    def getPort(self):
        return self.ssh_port

    def getUsers(self):
        return self.users.keys()

    def preprovision(self, user, ssh_keys):
        if user not in self.users.keys():
            self.users[user]=ssh_keys

    def provision(self, user, keys):
        #Assuming the AM have SSH root access to the node and the node is up
        #Setup users
        for username in self.users.keys():
            
            #ssh = "ssh-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@"+self.host+" -p "+str(self.ssh_port)+" "
            #!! Do nothing !! If you want to run those commands, comment the live below and uncomment the line above
            ssh = "exit 0 ; "
            cmd_create_user = ssh+"'grep \'^"+username+":\' /etc/passwd ; if [ $? -ne 0 ] ; then useradd -m -d /home/"+username+" "+ username+" && mkdir -p /home/"+username+"/.ssh ; fi'"
            out = subprocess.check_output(['bash', '-c', cmd_create_user])
            cmd_add_key = ssh+"\"echo '' > /home/"+username+"/.ssh/authorized_keys\""
            out = subprocess.check_output(['bash', '-c', cmd_add_key])
            for key in keys:
                cmd_add_key = ssh+"\"echo '"+key+"' >> /home/"+username+"/.ssh/authorized_keys\""
                out = subprocess.check_output(['bash', '-c', cmd_add_key])
            cmd_set_rights = ssh+"'chown -R "+username+": /home/"+username+" && chmod 700 /home/"+username+"/.ssh && chmod 644 /home/"+username+"/.ssh/authorized_keys'"
            out = subprocess.check_output(['bash', '-c', cmd_set_rights])
            return True
            

    def manifestAuth(self):
        if len(self.getUsers())==0:
            return []
        else:
            ret = []
            for login in self.getUsers():
                auth=etree.Element("login")
                auth.set("authentication","ssh-keys")
                auth.set("hostname", self.host)
                auth.set("port", str(self.getPort()))
                auth.set("username", login)
                ret.append(auth)
            return ret

    #A blocking (while ...) method. Return True when the resource is up and ready, or False if you set a timeout
    def checkSshConnection(self):
        try:
            #ssh = "ssh root@"+self.host+" -p "+str(self.ssh_port)
            #!! Do nothing !! If you want to run this command, comment the live below and uncomment the line above
            ssh= "exit 0;"
            subprocess.check_output(['bash', '-c', ssh])
            return True
        except subprocess.CalledProcessError as e:
            return False
        pass

    #Install the target url to the install_path (decompressed)
    def installCommand(self, url, install_path):
        pass

    #Execute a command with the given shell on the resource
    def executeCommand(self, shell, cmd):
        pass
