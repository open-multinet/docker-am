#----------------------------------------------------------------------
# Copyright (c) 2011-2016 Raytheon BBN Technologies
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

from gcf.geni.am.resource import Resource
from lxml import etree
import uuid


class DockerContainer(Resource):

    DEFAULT_SLIVER_TYPE="dockercontainer"
    
    def __init__(self, agg, host="localhost"):
        super(DockerContainer, self).__init__(str(uuid.uuid4()), "dockercontainer")
        self._agg = agg
        self.sliver_type = DockerContainer.DEFAULT_SLIVER_TYPE
        self.users=list()
        self.ssh_port=22
        self.host = host
        self.DockerManager = DockerManager()
        self.DockerManager.checkDocker()
        

    def deprovision(self):
        """Deprovision this resource at the resource provider."""
        self.DockerManager.removeContainer(self.id)
        self.users = list()
        self.ssh_port=22
        self.host = "localhost"
        self._agg.deallocate(container=None, resources=[self])

    def deallocate(self):
        self.available=True
        self.sliver_type = DockerContainer.DEFAULT_SLIVER_TYPE
        self._agg.deallocate(container=None, resources=[self])

    def getPort(self):
        #return DockerManager.getPort(self.id)
        return self.ssh_port

    def getUsers(self):
        return self.users

    def preprovision(self, user):
        self.users.append(user)
        self.ssh_port = self.DockerManager.reserveNextPort()

    def provision(self, user, key):
        self.DockerManager.startNew(self.id, self.sliver_type, self.ssh_port)
        return self.DockerManager.setupContainer(self.id, user, key)

    def updateUser(self, user, keys):
        if user not in self.users:
            self.users.append(user)
        self.DockerManager.setupUser(self.id, user, keys)

    def manifestDetails(self, manifest):
        if len(self.getUsers())==0:
            return manifest
        else:
            services = etree.SubElement(manifest, "services")
            for login in self.getUsers():
                auth=etree.SubElement(services, "login")
                auth.set("authentification","ssh-keys")
                auth.set("hostname", self.host)
                auth.set("port", str(self.getPort()))
                auth.set("username", login)
            return manifest
            
    def genAdvertNode(self, _urn_authority, _my_urn):
        r = etree.Element("node")
        resource_id = str(self.id)
        resource_available = str(self.available).lower()
        resource_urn = self.urn(_urn_authority)
        r.set("component_manager_id", _my_urn)
        r.set("component_name", resource_id)
        r.set("component_id", resource_urn)
        r.set("exclusive", "true")
        etree.SubElement(r, "sliver_type").set("name", self.sliver_type)
        etree.SubElement(r, "available").set("now", resource_available)
        return r
