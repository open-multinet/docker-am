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

from gcf_to_docker import DockerManager
from extendedresource import ExtendedResource

from gcf.geni.am.resource import Resource
from lxml import etree
import uuid
import subprocess
import time

class DockerContainer(ExtendedResource):

    DEFAULT_SLIVER_TYPE='docker-container'
    
    def __init__(self, dockermaster, starting_ipv4_port, dockermanager, host="localhost", ipv6_prefix=None):
        """

        :param dockermaster: The parent DockerMaster or None if there is none
        :type dockermaster: DockerMaster
        """
        super(DockerContainer, self).__init__(str(uuid.uuid4()), [ DockerContainer.DEFAULT_SLIVER_TYPE ])
        self.dockermaster = dockermaster
        self.user_keys_dict=dict()
        self.ssh_port=22
        self.host = host
        self.starting_ipv4_port=starting_ipv4_port
        self.image = None
        self.error = ''
        self.DockerManager = dockermanager
        self.mac = self.DockerManager.randomMacAddress()
        if ipv6_prefix is not None and len(ipv6_prefix)>0:
            self.ipv6 = self.DockerManager.computeIpV6(ipv6_prefix, self.mac)
        else:
            self.ipv6=None
        self.DockerManager.checkDocker()
        self.is_proxy = False

    def deprovision(self):
        """Deprovision this resource at the resource provider."""
        super(DockerContainer, self).deprovision()
        self.DockerManager.releasePort(self.ssh_port)
        self.DockerManager.removeContainer(self.id)
        self.user_keys_dict = dict()
        self.ssh_port=22
        
    def deallocate(self):
        super(DockerContainer, self).deallocate()
        self.available=True

    def getPort(self):
        return self.ssh_port

    def getUsers(self):
        return self.user_keys_dict.keys()

    def preprovision(self, extra_user_keys_dict):
        super(DockerContainer, self).preprovision(extra_user_keys_dict)
        self.user_keys_dict.update(extra_user_keys_dict)
        if self.ssh_port==22 or not self.DockerManager.isContainerUp(self.ssh_port):
            self.ssh_port = self.DockerManager.reserveNextPort(self.starting_ipv4_port)

    def provision(self):
        super(DockerContainer, self).provision()
        if self.DockerManager.isContainerUp(self.ssh_port):
            self.DockerManager.removeContainer(self.id)
        out = self.DockerManager.startNew(id=self.id,
                                          sliver_type=self.chosen_sliver_type,
                                          ssh_port=self.ssh_port,
                                          mac_address=self.mac,
                                          image=self.image)
        if out is not True:
            self.error = out
            return False
        else:
            self.error=''
        out = self.DockerManager.setupContainer(self, self.id, self.user_keys_dict)
        if out is not True:
            self.error = out
        else:
            self.error=''
        return True

    def restart(self):
        """
            Restart the resource without reloading the file system
        """
        super(DockerContainer, self).restart()
        self.DockerManager.restartContainer(self.id)

    def updateUser(self, new_user_keys_dict, force=False):
        for user, keys in new_user_keys_dict.items():
            if force or user not in self.user_keys_dict.keys():
                res = self.DockerManager.setupUser(self.id, user, keys)
                if res is not True:
                    return res
                self.user_keys_dict[user]=keys
        return True

    def manifestAuth(self):
        super(DockerContainer, self).manifestAuth()
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
                if self.ipv6 is not None:
                    auth=etree.Element("login")
                    auth.set("authentication","ssh-keys")
                    auth.set("hostname", str(self.ipv6))
                    auth.set("port", "22")
                    auth.set("username", login)
                    ret.append(auth)
            return ret

            
    def genAdvertNode(self, _urn_authority, _my_urn):
        r = super(DockerContainer, self).genAdvertNode(_urn_authority, _my_urn)
        return r

    #This is called when the AM releases the resource (when deleting the sliver)
    def reset(self):
        super(DockerContainer, self).reset()
        # don't think this one is needed
        # self._agg.deallocate(container=None, resources=[self])
        self.image = None
        self.error = ''
        #let the DockerMaster know that this resource is available again
        if (self.dockermaster is not None):
            self.dockermaster.onResetChild(self)

    def waitForSshConnection(self):
        """

        :rtype: bool
        """
        super(DockerContainer, self).waitForSshConnection()
        connect = False
        cmd = "nc -z "+self.host+" "+str(self.ssh_port)
        retry = 20
        while not connect and retry > 0:
            try:
                subprocess.check_output(['bash', '-c', cmd])
                connect=True
            except:
                print "Retry connection to "+self.host+" on port "+str(self.ssh_port)
                retry -= 1
                time.sleep(3)
                pass
        if not connect:
            return False
        try:
            cmd = "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@"+self.host+" -p "+str(self.ssh_port)+" 'test'"
            subprocess.check_output(['bash', '-c', cmd]).decode('utf-8').strip()
        except:
            pass
        return True

    def installCommand(self, url, install_path):
        return self.DockerManager.installCommand(self.id, url, install_path)

    def executeCommand(self, shell, cmd):
        return self.DockerManager.executeCommand(self.id, shell, cmd)
