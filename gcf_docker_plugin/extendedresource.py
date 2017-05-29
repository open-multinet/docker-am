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

from lxml import etree

FIXED_PROXY_USER = "proxyuser"

class ExtendedResource(Resource):

    def __init__(self, rid, r_supported_sliver_types, _rtype="node"):
        """
        :param r_supported_sliver_types: a list with the supported sliver_types
        :type r_supported_sliver_types: list of str
        :param rid: unique ID of the resource. Note: should be unique among ALL resources of ALL types.
        :type rid: str
        :param rtype: the type of resource used in the URN. Note that the geni URI spec says this should be "node" (or "link")
        :type rtype: str
        """
        super(ExtendedResource, self).__init__(rid, _rtype)
        self.supported_sliver_types = r_supported_sliver_types
        self.users=dict()
        self.ssh_port=22
        self.error = ""
        self.host = "127.0.0.1"
        self.proxy_resource = None #Can be None, a fixed resource, or a resource for each slice
        self.is_proxy = False
        self.chosen_sliver_type = None # resources with multiple possible sliver types can check this after allocate
        # to see what the user requested

    def genAdvertNode(self, _urn_authority, _my_urn):
        """
            Returns a etree.Element containing advertisement info for this resource

            :param _my_urn: URN of the resource
            :type _my_urn: str
            :param _urn_authority: URN of the authority/AM
            :type _urn_authority: str
            :rtype: Element
        """

        # Actual resources should add some information like sliver_type
        r = etree.Element("node")
        resource_id = str(self.id)
        resource_available = str(self.available).lower()
        resource_urn = self.urn(_urn_authority)
        r.set("component_manager_id", _my_urn)
        r.set("component_name", resource_id)
        r.set("component_id", resource_urn)
        r.set("exclusive", "false")
        etree.SubElement(r, "available").set("now", resource_available)
        for sliver_type_name in self.supported_sliver_types:
            etree.SubElement(r, "sliver_type").set("name", sliver_type_name)
        return r

    def matchResource(self, sliver_type=None, component_id=None, exclusive=None):
        """
        Returns one matching resource.
        If this is just a single resource, it returns itself.
        If this is a pool of resources, it returns a single resource in the pool.
        Matches take sliver_type, component_id and exclusive into account.

        :rtype: ExtendedResource
        :param sliver_type: if specified return this resource or a resource in the pool, only if it matches the sliver_type (of this resource or the pool)
        :type sliver_type: str
        :param component_id: if specified, return this resource or a resource in the pool, only if it matches the component_id (of this resource or the pool)
        :type component_id: str
        :param exclusive: if specified, take exclusive into account, returning None if needed
        :type exclusive: bool
        """
        if sliver_type is not None and not sliver_type in self.supported_sliver_types:
            return None
        if component_id is not None:
            if component_id != self.id:
                return None
        #by default, do not allow exclusive resources, but do allow non exclusive resources
        if exclusive is not None and exclusive:
            return None
        return self

    def deallocate(self):
        """
        This method is called when the Allocate call fails after the allocation of the resources (for example problem with allocation time)
        :return:
        """
        self.available = True
        self.chosen_sliver_type = None
        pass

    #
    def deprovision(self):
        """
            Set the hardware in the original state (reinstall OS for example)

            Called when Delete is called
            So both deprovision AND deallocate

        :return:
        """
        self.chosen_sliver_type = None
        pass

    #Returns the ssh port to reach the resource
    def getPort(self):
        return self.ssh_port

    #Returns list of configured users
    def getUsers(self):
        return self.users.keys()

    def preprovision(self, user_keys_dict):
        """
            Provisionning take some time but the Provision call done to the API must reply quickly.
            So, preprovision only prepare required value like users to be configured, SSH port used, ...

        :param user_keys_dict: users and keys of the user. This is a dict mapping usernames to lists of keys
        :return:
        """
        if self.chosen_sliver_type is None:
            raise Exception("Internal bug: Allocate did not set chosen_sliver_type")
        pass

    def provision(self):
        """
            Do all the stuff to set up the resource, like load the proper OS, configure users and SSH authorized keys, ...
            Should return True, or set self.error with an error message and return False
        """
        if self.chosen_sliver_type is None:
            raise Exception("Internal bug: Allocate did not set chosen_sliver_type")
        pass

    def restart(self):
        """
            Restart the resource without reloading the file system
        """
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

    def addManifestProxyServiceElements(self, services_element):
        """
        This adds child elements to the service element of the resource, with proxy info.
        Specifically, this adds at least a <login> element for the proxy, and a <proxy> element for each user
        If there is no proxy, nothing is added.

        :param services_element: The services element to which proxy child elements should be added
        :type services_element: etree.Element
        """
        if self.proxy_resource:
            # self.logger.debug('addManifestProxyServiceElements for resource with proxy_resource')

            auth=etree.Element("login")
            auth.set("authentication","ssh-keys")
            auth.set("hostname", self.proxy_resource.host)
            auth.set("port", str(self.proxy_resource.getPort()))
            auth.set("username", FIXED_PROXY_USER)
            services_element.append(auth)

            for login in self.getUsers():
                proxy=etree.Element("{http://jfed.iminds.be/proxy/1.0}proxy")
                proxy.set("proxy","{}@{}:{:d}".format(
                    FIXED_PROXY_USER,
                    self.proxy_resource.host,
                    self.proxy_resource.getPort()))
                proxy.set("for", "{}@{}:{:d}".format(
                    login,
                    self.host,
                    self.getPort()))
                services_element.append(proxy)
        else:
            # self.logger.debug('addManifestProxyServiceElements for resource without proxy_resource')
            pass

    #Only used if your resource is a pool of resource, like DockerMaster
    def size(self):
        return 1

    # #Set the instance in the original state
    # def reset(self):
    #     super(ExtendedResource, self).reset()
    #     todo #todo figure out what reset is used for, remove if not used
    #     self.error = ''

    #A "blocking" method which return True when the SSH connection is available = The node is fully ready for the user
    #Should return True, or set self.error with an error message and return False
    def waitForSshConnection(self):
        pass

    #Decompress the target of the url to install_path on the resource
    def installCommand(self, url, install_path):
        pass

    #Executes the command given with the shell provided of the resource
    def executeCommand(self, shell, cmd):
        pass
