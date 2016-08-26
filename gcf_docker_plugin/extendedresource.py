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

    #Returns a etree.Element containing advertisement info
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

    #Returns the resource if matches the component_id (if given)
    #In case of a pool, you should search for the resource which match
    def getResource(self, component_id=None):
        if component_id is not None:
            if component_id != self.id:
                return None
        return self

    #This method is called when the Allocate call fails after the allocation of the resources (for example problem with allocation time)
    def deallocate(self):
        self.available = True
        pass

    #Set the hardware in the original state (reinstall OS for example)
    def deprovision(self):
        pass

    #Returns the ssh port to reach the resource
    def getPort(self):
        return self.ssh_port

    #Returns list of configured users
    def getUsers(self):
        return self.users.keys()

    #Provisionning take some time but the Provision call done to the API must reply quickly.
    #So, preprovision only prepare required value like users to be configured, SSH port used, ... 
    def preprovision(self, user, ssh_keys):
        pass

    #Do all the stuff to set up the resource, like load the proper OS, configure users and SSH authorized keys, ...
    #Should return True, or set self.error with an error message and return False
    def provision(self, user, keys):
        pass

    #Returns an etree Element node with authentification information
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

    #Set the instance in the original state
    def reset(self):
        super(ExtendedResource, self).reset()
        self.error = ''

    #A "blocking" method which return True when the SSH connection is available = The node is fully ready for the user
    #Should return True, or set self.error with an error message and return False
    def checkSshConnection(self):
        pass

    #Decompress the target of the url to install_path on the resource
    def installCommand(self, url, install_path):
        pass

    #Executes the command given with the shell provided of the resource
    def executeCommand(self, shell, cmd):
        pass
