from __future__ import absolute_import
from gcf.geni.am.resource import Resource

from lxml import etree

class ExtendedResource(Resource):

    def __init__(self, rid, rtype):
        super(ExtendedResource, self).__init__(rid, rtype)
        self.users=dict()
        self.ssh_port=22
        self.error = ""
        self.host = "127.0.0.1"

    #Return a etree.Element containing advertisement info
    #You should have to add some information like sliver_type
    def genAdvertNode(self, _urn_authority, _my_urn):
        r = etree.Element("node")
        resource_id = str(self.id)
        resource_available = str(self.available).lower()
        resource_urn = self.urn(_urn_authority)
        r.set("component_manager_id", _my_urn)
        r.set("component_name", resource_id)
        r.set("component_id", resource_urn)
        r.set("exclusive", "false")
        return r

    def getResource(self, component_id=None):
        if component_id is not None:
            if component_id != self.id:
                return None
        return self

    def deallocate(self):
        self.available = True
        pass

    def getPort(self):
        return self.ssh_port

    def getUsers(self):
        return self.users.keys()

    def preprovision(self, user, ssh_keys):
        pass

    def provision(self, user, keys):
        pass

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

    def checkSshConnection(self):
        pass

    def installCommand(self, url, install_path):
        pass

    def executeCommand(self, shell, cmd):
        pass
