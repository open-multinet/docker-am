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

from dockercontainer import DockerContainer

from gcf.geni.am.resource import Resource
from lxml import etree
import uuid
from urllib2 import urlopen
from gcf_to_docker import DockerManager
from extendedresource import ExtendedResource

class DockerMaster(ExtendedResource):
    def __init__(self, max_slots, host=None, ipv6_prefix=None, starting_ipv4_port=None, dockermanager=None):
        super(DockerMaster, self).__init__(str(uuid.uuid4()),
                                           [ 'docker-container',
                                             'docker-container_100M',
                                             'docker-container-with-tunnel' ])
        if starting_ipv4_port is None or starting_ipv4_port<=1024:
            starting_ipv4_port=12000 #Default
        if dockermanager is None:
            dockermanager = DockerManager()
        if host is None or len(host)==0:
            host = urlopen('http://ip.42.pl/raw').read()
        self.pool = [DockerContainer(self, starting_ipv4_port, dockermanager, host, ipv6_prefix)
                     for _ in range(max_slots)]

    def onResetChild(self, childResource):
        self.pool.append(childResource)

    def genAdvertNode(self, _urn_authority, _my_urn):
        r = super(DockerMaster, self).genAdvertNode(_urn_authority, _my_urn)
        r.set("exclusive", "false")
        hardware = etree.SubElement(r, "hardware_type")
        hardware.set("name", "docker_cluster")
        etree.SubElement(hardware, "{http://www.protogeni.net/resources/rspec/ext/emulab/1}node_type").set("type_slots", str(len(self.pool)))
        return r
        
    def matchResource(self, sliver_type=None, component_id=None, exclusive=None):
        if sliver_type is not None and not sliver_type in self.supported_sliver_types:
            return None
        #do not allow exclusive resources, but do allow non exclusive resources
        if exclusive is not None and exclusive:
            return None
        if len(self.pool) == 0:
            return None
        if component_id is not None:
            for r in self.pool:
                if r.id == component_id:
                    self.pool.remove(r)
                    return r
            return None #No id match
        return self.pool.pop(0)

    def size(self):
        return len(self.pool)
