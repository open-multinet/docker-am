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

"""
The GPO Reference Aggregate Manager v3, showing how to implement
the GENI AM API version 3. This AggregateManager has only fake resources.
Invoked from gcf-am.py
The GENI AM API is defined in the AggregateManager class.
"""

# Note: This AM uses SFA authorization to check that the caller
# has appropriate credentials to make the call. If this AM is used in 
# conjunction with the policy-based authorization capability (in gcf.geni.auth)
# then this code needs to only extract expiration times from the credentials
# which can be done using the gcf.sfa.credential module

from __future__ import absolute_import

import sys

from extendedresource import ExtendedResource, FIXED_PROXY_USER
from gdpr.gdpr_site_request_handler import SecureXMLRPCAndGDPRSiteRequestHandler

sys.path.insert(1, '../geni-tools/src')

import base64
import collections
import datetime
import os
import traceback
import xml.dom.minidom as minidom
import zlib
import ConfigParser
import threading
import time
import gcf.geni.am.am3 as am3
import pickle
import Pyro4

from StringIO import StringIO
from lxml import etree
from gcf.geni.am.aggregate import Aggregate
from dockermaster import DockerMaster
from gcf_to_docker import DockerManager
from gcf.geni.util.urn_util import publicid_to_urn
from gcf.geni.util import urn_util as urn

from gcf.sfa.trust.credential import Credential
from gcf.gcf_version import GCF_VERSION

from gcf.geni.auth.base_authorizer import *
from gcf.geni.am.api_error_exception import ApiErrorException

from shutil import copyfile

# See sfa/trust/rights.py
# These are names of operations
# from the rights.py privilege_table
# Credentials may list privileges that
# map to these operations, giving the caller permission
# to perform the functions
RENEWSLIVERPRIV = am3.RENEWSLIVERPRIV

# Map the Allocate, Provision and POA calls to the CreateSliver privilege.
ALLOCATE_PRIV = am3.ALLOCATE_PRIV
PROVISION_PRIV = am3.PROVISION_PRIV
PERFORM_ACTION_PRIV = am3.PERFORM_ACTION_PRIV
DELETESLIVERPRIV = am3.DELETESLIVERPRIV
SLIVERSTATUSPRIV = am3.SLIVERSTATUSPRIV
SHUTDOWNSLIVERPRIV = am3.SHUTDOWNSLIVERPRIV

# Publicid format resource namespace. EG Resource URNs
# will be <namespace>:resource:<resourcetype>_<resourceid>
# This is something like the name of your AM
# See gen-certs.CERT_AUTHORITY
RESOURCE_NAMESPACE = am3.RESOURCE_NAMESPACE

# MAX LEASE is 7 days (arbitrarily)
REFAM_MAXLEASE_MINUTES = am3.REFAM_MAXLEASE_MINUTES

# Expiration on Allocated resources is 10 minutes.
ALLOCATE_EXPIRATION_SECONDS = am3.ALLOCATE_EXPIRATION_SECONDS

# GENI Allocation States
STATE_GENI_UNALLOCATED = am3.STATE_GENI_UNALLOCATED
STATE_GENI_ALLOCATED = am3.STATE_GENI_ALLOCATED
STATE_GENI_PROVISIONED = am3.STATE_GENI_PROVISIONED

# GENI Operational States
# These are in effect when the allocation state is PROVISIONED.
OPSTATE_GENI_PENDING_ALLOCATION = am3.OPSTATE_GENI_PENDING_ALLOCATION
OPSTATE_GENI_NOT_READY = am3.OPSTATE_GENI_NOT_READY
OPSTATE_GENI_CONFIGURING = am3.OPSTATE_GENI_CONFIGURING
OPSTATE_GENI_STOPPING = am3.OPSTATE_GENI_STOPPING
OPSTATE_GENI_READY = am3.OPSTATE_GENI_READY
OPSTATE_GENI_READY_BUSY = am3.OPSTATE_GENI_READY_BUSY
OPSTATE_GENI_FAILED = am3.OPSTATE_GENI_FAILED

EXPIRE_LOCK = threading.Lock()
DUMP_LOCK= threading.Lock()
ALLOCATE_LOCK = threading.Lock()

RSPEC_V3_NAMESPACE_URI = "http://www.geni.net/resources/rspec/3"

#increment CODE_VERSION whenever changing something that impacts the stored data
STATE_CODE_VERSION = '1'
STATE_FILENAME = 'am-state-v{}.dat'.format(STATE_CODE_VERSION)

class DockerAggregateManager(am3.ReferenceAggregateManager):
    def __init__(self, root_cert, urn_authority, url, **kwargs):
        """
        Create a testbed AggregateManager ("AM"), which supports docker containers and simple raw resources

        :param root_cert: is a single cert or dir of multiple certs that are trusted to sign credentials
        :type root_cert: ?
        :param urn_authority: the tla/tla part of the authority urn. For "urn:publicid:IDN+example.com+authority+am" this must be "example.com"
        :type urn_authority: string
        :param url: the URL at which the AM runs.
        :type url: string
        :param kwargs:
        """
        super(DockerAggregateManager,self).__init__(root_cert,urn_authority,url,**kwargs)
        self._hrn = urn_authority
        self._urn_authority = "IDN "+urn_authority
        self._my_urn = publicid_to_urn("%s %s %s" % (self._urn_authority, 'authority', 'am'))
        self.DockerManager = DockerManager()
        self.proxy_dockermaster = None
        thread_sliver_daemon = threading.Thread(target=self.expireSliversDaemon)
        thread_sliver_daemon.daemon=True
        thread_sliver_daemon.start()
        try:
            self.logger.info("Restoring AM state from \"{}\"...".format(STATE_FILENAME))
            s=open(STATE_FILENAME, 'rb')
            p = pickle.Unpickler(s)
            self._agg = p.load()
            self._slices = p.load()
            self.proxy_dockermaster = p.load()
            self.public_url = p.load()
            s.close()
        except Exception as e:
            self.logger.info(str(e))
            self.logger.info("Restoring AM state FAILED: Loading new instance...")
            self._agg = Aggregate()
            config = ConfigParser.SafeConfigParser()
            config.read(os.path.dirname(os.path.abspath(__file__))+"/docker_am_config")
            self.public_url = None

            for r in config.sections():
                def config_fetch(option_name, if_missing=None):
                    if not config.has_option(r, option_name) \
                            or config.get(r, option_name) is None \
                            or config.get(r, option_name) == "":
                        return if_missing
                    else:
                        return config.get(r, option_name)

                if r == 'general':
                    self.public_url = config_fetch("public_url")
                    pass
                else:
                    #Both proxy and resources need a dockermanager config
                    if config_fetch("dockermaster_pyro4_host") is None:
                        # No host specified, so a new object is created locally,
                        # which means docker runs on the local host instead of on a remote host
                        dockermanager = DockerManager()
                    else:
                        # Host specified, so also use a DockerManager object,
                        # but use PYRO to use one on a remote host instead of a local one.
                        # This means that this uses docker on a remote host
                        uri = "PYRO:dockermanager@" + config.get(r, "dockermaster_pyro4_host") + ":" + config.get(r, "dockermaster_pyro4_port")
                        dockermanager = Pyro4.Proxy(uri)
                        dockermanager._pyroHmacKey = config.get(r, "dockermaster_pyro4_password")

                    if r.startswith("proxy"):
                        if self.proxy_dockermaster is not None:
                            raise Exception('Only 1 proxy section in config is supported')
                        # proxy_type meaning:
                        #    slice means one new proxy per slice.
                        #    global means one fixed proxy.
                        proxy_type = config_fetch("type")
                        if proxy_type is None or not proxy_type in [ 'global', 'slice' ]:
                            raise Exception("Invalid config: none or unknown proxy type specified in section \"{}\"".format(r))
                        if proxy_type == 'global':
                            raise Exception(
                                "Valid proxy type {} specified in section \"{}\" is not yet supported".format(proxy_type,r))
                        if proxy_type == 'slice':
                            self.proxy_dockermaster = DockerMaster(int(config.get(r, "max_containers", 20)),
                                                              config_fetch('node_ipv4_hostname'),
                                                              None, #no ipv6 prefix
                                                              int(config_fetch('starting_ipv4_port', '2222')),
                                                              dockermanager)
                        pass
                    else:
                        self._agg.add_resources([DockerMaster(int(config_fetch("max_containers", 20)),
                                                              config_fetch("node_ipv4_hostname"),
                                                              config_fetch("ipv6_prefix"),
                                                              int(config_fetch('starting_ipv4_port', '12000')),
                                                              dockermanager)])
                        #Here you can add the example resource. (You have to delete STATE_FILENAME to reload resources)
                #self._agg.add_resources([ResourceExample(str(uuid.uuid4()), "127.0.0.1")])
            self.dumpState()
            if self.public_url is None:
                self.public_url = self._url
                self.logger.warn("Warning: no public_url in docker_am_config. Will use '%s' as URL", self.public_url)

        self.logger.info("Running %s AM v%d code version %s", self._am_type, self._api_version, GCF_VERSION)

    # Make the XML-RPC server also serve some generic HTTP requests (used to server GDPR site)
    custom_request_handler_class = SecureXMLRPCAndGDPRSiteRequestHandler

    # The list of credentials are options - some single cred
    # must give the caller required permissions.
    # The semantics of the API are unclear on this point, so
    # this is just the current implementation
    def ListResources(self, credentials, options):
        '''Return an RSpec of resources managed at this AM.
        If geni_available is specified in the options,
        then only report available resources. If geni_compressed
        option is specified, then compress the result.'''
        self.logger.info('ListResources(%r)' % (options))
        self.expire_slivers()

        # Note this list of privileges is really the name of an operation
        # from the privilege_table in sfa/trust/rights.py
        # Credentials will specify a list of privileges, each of which
        # confers the right to perform a list of operations.
        # EG the 'info' privilege in a credential allows the operations
        # listslices, listnodes, policy

        # could require list or listnodes?
        privileges = ()
        self.getVerifiedCredentials(None,
                                    credentials, 
                                    options,
                                    privileges)

        # If we get here, the credentials give the caller
        # all needed privileges to act on the given target.

        if 'geni_rspec_version' not in options:
            # This is a required option, so error out with bad arguments.
            self.logger.error('No geni_rspec_version supplied to ListResources.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version was not supplied.')
        if 'type' not in options['geni_rspec_version']:
            self.logger.error('ListResources: geni_rspec_version does not contain a type field.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version does not have a type field.')
        if 'version' not in options['geni_rspec_version']:
            self.logger.error('ListResources: geni_rspec_version does not contain a version field.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version does not have a version field.')

        # Look to see what RSpec version the client requested
        # Error-check that the input value is supported.
        rspec_type = options['geni_rspec_version']['type']
        if isinstance(rspec_type, basestring):
            rspec_type = rspec_type.lower().strip()
        rspec_version = options['geni_rspec_version']['version']
        if rspec_type != 'geni':
            self.logger.error('ListResources: Unknown RSpec type %s requested', rspec_type)
            return self.errorResult(am3.AM_API.BAD_VERSION,
                                    'Bad Version: requested RSpec type %s is not a valid option.' % (rspec_type))
        if rspec_version != '3':
            self.logger.error('ListResources: Unknown RSpec version %s requested', rspec_version)
            return self.errorResult(am3.AM_API.BAD_VERSION,
                                    'Bad Version: requested RSpec version %s is not a valid option.' % (rspec_version))
        self.logger.info("ListResources requested RSpec %s (%s)", rspec_type, rspec_version)

        if 'geni_slice_urn' in options:
            self.logger.error('ListResources: geni_slice_urn is no longer a supported option.')
            msg = 'Bad Arguments:'
            msg += 'option geni_slice_urn is no longer a supported option.'
            msg += ' Use "Describe" instead.'
            return self.errorResult(am3.AM_API.BAD_ARGS, msg)

        all_resources = self._agg.catalog(None)
        show_only_available = 'geni_available' in options and options['geni_available']
        adv_header = self.advert_header()
        for resource in all_resources:
            if show_only_available and not resource.available:
                continue
            adv_header.append(resource.genAdvertNode(self._urn_authority, self._my_urn))
        result = etree.tostring(adv_header, pretty_print=True, xml_declaration=True, encoding='utf-8')
        # Optionally compress the result
        if 'geni_compressed' in options and options['geni_compressed']:
            try:
                result = base64.b64encode(zlib.compress(result))
            except Exception as exc:
                self.logger.error("Error compressing and encoding resource list: %s", traceback.format_exc())
                raise Exception("Server error compressing resource list", exc)
        return self.successResult(result)

    # The list of credentials are options - some single cred
    # must give the caller required permissions.
    # The semantics of the API are unclear on this point, so
    # this is just the current implementation
    def Allocate(self, slice_urn, credentials, rspec, options):
        """Allocate slivers to the given slice according to the given RSpec.
        Return an RSpec of the actually allocated resources.

        :param slice_urn: the slice in which to allocate the resources
        :type slice_urn: string
        :param rspec: the request RSpec
        :type rspec: string
        :param credentials: the credential(s) that authorise the caller to use the slice specified in slice_urn
        :type credentials: list of dict
        :param options: optional parameters for the Allocate call
        :type options: dict
        """

        self.logger.info('Allocate(%r)' % (slice_urn))
        self.expire_slivers()
        # Note this list of privileges is really the name of an operation
        # from the privilege_table in sfa/trust/rights.py
        # Credentials will specify a list of privileges, each of which
        # confers the right to perform a list of operations.
        # EG the 'info' privilege in a credential allows the operations
        # listslices, listnodes, policy
        privileges = (ALLOCATE_PRIV,)

        creds=self.getVerifiedCredentials(slice_urn, credentials, options, privileges)
        # If we get here, the credentials give the caller
        # all needed privileges to act on the given target.

        # Grab the user_urn
        user_urn = gid.GID(string=options['geni_true_caller_cert']).get_urn()


        rspec_dom = None
        try:
            rspec_dom = minidom.parseString(rspec)
            #TODO: remember to call rspec_dom.unlink() once no part of it is still needed. This speeds up freeing its memory.
        except Exception as exc:
            self.logger.error("Cannot create sliver %s. Exception parsing rspec: %s" % (slice_urn, exc))
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Args: RSpec is unparseable')

        # Allow only Geni v3 request RSpec
        # expected root node is thus: <rspec type="request" xmlns="http://www.geni.net/resources/rspec/3">

        # rspec_nodelist = rspec_dom.getElementsByTagNameNS(RSPEC_V3_NAMESPACE_URI, "rspec") # type: NodeList
        # if (rspec_nodelist.length == 0):
        #     return self.errorResult(am3.AM_API.BAD_ARGS, 'Bad Args: no RSpec element found')
        # if (rspec_nodelist.length > 1):
        #     return self.errorResult(am3.AM_API.BAD_ARGS, 'Bad Args: multiple RSpec element found')
        # rspec_element = rspec_nodelist.item(0) # type : Element

        rspec_element = rspec_dom.documentElement # type : Element
        if rspec_element is None:
            return self.errorResult(am3.AM_API.BAD_ARGS, 'Bad Args: no root RSpec element found')
        if not rspec_element.hasAttribute("type"):
            return self.errorResult(am3.AM_API.BAD_ARGS, 'Bad Args: rspec element has no "type" argument')
        if rspec_element.getAttribute("type") != "request":
            return self.errorResult(am3.AM_API.BAD_ARGS, 'Bad Args: rspec element has type "'+rspec_element.getAttribute("type")+'" instead of "request"')

        ALLOCATE_LOCK.acquire()
        available = self.resources(available=True)
        available = sorted(available, key=lambda a: a.size(), reverse=True)
                
        # Note: We only care about nodes for this component manager.
        #       nodes without component_manager_id or with a component_manager_id of another AM are ignored
        local_nodes = list()
        for node_elem in rspec_dom.documentElement.getElementsByTagName('node'):
            if node_elem.getAttribute("component_manager_id") == self._my_urn:
                local_nodes.append(node_elem)

        # If there are no nodes in the RSpec that we should handle, the AM specification does not tell us what to do.
        # In general, it is best to throw the SEARCH_FAILED error, because silently doing nothing is potentially too confusing.
        if len(local_nodes)==0:
            ALLOCATE_LOCK.release()
            return self.errorResult(am3.AM_API.SEARCH_FAILED, "No requested resource can be allocated on this AM. "
                                                              "Check your request (usually bad component_manager_id)")

        resources = list()
        images_to_delete = list()

        def abort_resource_allocation():
            for r in resources:
                r.deallocate()
            ALLOCATE_LOCK.release()

        proxy_resource = None
        if self.proxy_dockermaster is not None:
            proxy_resource = self.proxy_dockermaster.matchResource()
            if proxy_resource is None:
                abort_resource_allocation()
                return self.errorResult(am3.AM_API.TOO_BIG, 'Too Big: insufficient resources to fulfill request (not enough resources to create proxy)')
            proxy_resource.is_proxy = True
            proxy_resource.external_id = None
            proxy_resource.available = False
            proxy_resource.chosen_sliver_type='docker-container'
            proxy_resource.image = None
            resources.append(proxy_resource)

        for node_elem in local_nodes:
            client_id = node_elem.getAttribute('client_id')
            if client_id == "" or client_id is None:
                abort_resource_allocation()
                return self.errorResult(am3.AM_API.BAD_ARGS, "A node does not have a client_id")
            if len(node_elem.getElementsByTagName('sliver_type')) < 1:
                abort_resource_allocation()
                return self.errorResult(am3.AM_API.BAD_ARGS,
                                        "The node '{}' does not have a sliver_type".format(client_id))
            sliver_type = node_elem.getElementsByTagName('sliver_type')[0]
            image = None
            if sliver_type != "":
                if len(sliver_type.getElementsByTagName("disk_image")) == 1:
                    image = sliver_type.getElementsByTagName("disk_image")[0].getAttribute("name")
                    images_to_delete.append(image)
                sliver_type = sliver_type.getAttribute('name')
                # notE: basestring handles both str and unicode
            if sliver_type is None \
                    or not isinstance(sliver_type, basestring) \
                    or sliver_type == "":
                self.logger.info('Bad sliver_type="%s" (%r) (type=%s)', sliver_type, sliver_type, type(sliver_type))
                abort_resource_allocation()
                return self.errorResult(am3.AM_API.BAD_ARGS,
                                        "The node '{}' does not have a valid sliver_type".format(client_id))
            self.logger.info('Checking node with sliver_type="%s"', sliver_type)
            component_id = node_elem.getAttribute('component_id')
            if component_id == "": component_id=None
            exclusive = node_elem.getAttribute('exclusive') # type : string
            if exclusive == "": exclusive=None
            if exclusive is not None:
                exclusive = exclusive.lower() in ['true', '1', 't', 'y', 'yes']
            resource = None # type: ExtendedResource
            for r in available:
                resource = r.matchResource(sliver_type, component_id, exclusive)
                if resource is None:
                    # Search next available resource
                        continue
                else:
                    #resource found
                    if component_id is not None and (resource.id != component_id):
                        abort_resource_allocation()
                        return self.errorResult(5, #5 = SERVERERROR
                                                "Server ERROR: {} != {}".format(resource.id, component_id))
                    try:
                        #Resource returned by a resource pool are not listed in "available" list,
                        # so ignore Exception
                        available.remove(resource)
                    except:
                        pass
                    break
            if resource is None: # There aren't enough resources
                self.logger.error('Too big: not enought %s available',sliver_type)
                abort_resource_allocation()
                return self.errorResult(am3.AM_API.TOO_BIG, 'Too Big: insufficient resources to fulfill request')
            resource.external_id = client_id
            resource.available = False
            resource.chosen_sliver_type=sliver_type
            resource.image=image
            resource.proxy_resource = proxy_resource
            resources.append(resource)

        ALLOCATE_LOCK.release()

        # determine the start time as bounded by slice expiration and 'now'
        now = datetime.datetime.utcnow()
        start_time = now
        if 'geni_start_time' in options:
            # # Need to parse this into datetime
            # start_time_raw = options['geni_start_time']
            # start_time = self._naiveUTC(dateutil.parser.parse(start_time_raw))
            return self.errorResult(am3.AM_API.BAD_ARGS, 
                                    "geni_start_time is not supported")

        # determine max expiration time from credentials
        # do not create a sliver that will outlive the slice!
        expiration = self.min_expire(creds, self.max_alloc,
                                     ('geni_end_time' in options
                                      and options['geni_end_time']))

        # determine end time as min of the slice
        # and the requested time (if any)
        end_time = self.min_expire(creds, None,
                                   ('geni_end_time' in options
                                    and options['geni_end_time']))

        # if slice exists, check accept only if no  existing sliver overlaps
        # with requested start/end time. If slice doesn't exist, create it
        if slice_urn in self._slices:
            newslice = self._slices[slice_urn]
            # Check if any current slivers overlap with requested start/end
            one_slice_overlaps = False
            for sliver in newslice.slivers():
                if sliver.startTime() < end_time and \
                            sliver.endTime() > start_time:
                        one_slice_overlaps = True
                        break

            if one_slice_overlaps:
                ALLOCATE_LOCK.acquire()
                for sliver in newslice.slivers():
                    sliver.resource().deallocate()
                ALLOCATE_LOCK.release()
                # template = "Slice %s already has slivers at requested time"
                template = "Slice %s already has slivers"
                self.logger.error(template % (slice_urn))
                return self.errorResult(am3.AM_API.ALREADY_EXISTS,
                                        template % (slice_urn))
        else:
            newslice = Slice(slice_urn)
            
        for resource in resources:
            sliver = newslice.add_resource(resource)
            if resource.image is not None:
                resource.image = slice_urn+"::"+resource.image
            sliver.setExpiration(expiration)
            sliver.setStartTime(start_time)
            sliver.setEndTime(end_time)
            sliver.setAllocationState(STATE_GENI_ALLOCATED)
        for i in images_to_delete:
            if i.startswith("http://") or i.startswith("https://") and i not in newslice.images_to_delete:
                newslice.images_to_delete.append(i)
        self._agg.allocate(slice_urn, newslice.resources())
        self._agg.allocate(user_urn, newslice.resources())
        newslice.request_rspec = rspec
        self._slices[slice_urn] = newslice

        # Log the allocation
        self.logger.info("Allocated new slice %s" % slice_urn)
        for sliver in newslice.slivers():
            self.logger.info("Allocated resource %s to slice %s as sliver %s",
                             sliver.resource().id, slice_urn, sliver.urn())

        manifest = self.manifest_rspec(slice_urn)
        self.dumpState()
        result = dict(geni_rspec=manifest,
                      geni_slivers=[s.status() for s in newslice.slivers()])
        return self.successResult(result)

    def provision_install_execute_sliver(self, the_slice, sliver):
        def getXmlNode(client_id, manifest=the_slice.request_rspec):
            assert the_slice is not None
            assert manifest is not None
            for node in etree.parse(StringIO(manifest)).getroot().getchildren():
                if node.get("client_id")==client_id:
                    return node
            return None

        def getServiceInstall(etreeNode):
            ns="{"+etreeNode.nsmap.get(None)+"}"
            services =  etreeNode.find(ns+"services")
            if services is None:
                return []
            else:
                ret = list()
                for install in services.findall(ns+'install'):
                    ret.append([install.get('url'), install.get('install_path')])
                return ret

        def getServiceExecute(etreeNode):
            ns="{"+etreeNode.nsmap.get(None)+"}"
            services =  etreeNode.find(ns+"services")
            if services is None:
                return []
            else:
                ret = list()
                for install in services.findall(ns+'execute'):
                    ret.append([install.get('shell'), install.get('command')])
                return ret

        if sliver.resource().provision() is not True:
            sliver.setOperationalState(OPSTATE_GENI_FAILED)
            sliver.resource().deprovision()
            return
        if sliver.resource().waitForSshConnection() is not True:
            sliver.setOperationalState(OPSTATE_GENI_FAILED)
            sliver.resource().deprovision()
            return
        sliver.setOperationalState(OPSTATE_GENI_READY_BUSY)
        self.dumpState()
        client_id = sliver.resource().external_id
        if client_id is not None:
            assert client_id is not None
            assert isinstance(client_id, basestring)
            node_xml = getXmlNode(client_id)
            assert node_xml is not None
            # assert isinstance(node_xml, etree.Node)
            for i in getServiceInstall(node_xml):
                ret = sliver.resource().installCommand(i[0], i[1])
                if ret is not True:
                    sliver.setOperationalState(OPSTATE_GENI_FAILED)
                    sliver.resource().error = ret
                else:
                    sliver.resource().error = ""
                self.dumpState()
            sliver.setOperationalState(OPSTATE_GENI_READY)
            for i in getServiceExecute(node_xml):
                sliver.resource().executeCommand(i[0], i[1])
        else:
            sliver.setOperationalState(OPSTATE_GENI_READY)

    def Provision(self, urns, credentials, options):
        """Allocate slivers to the given slice according to the given RSpec.
        Return an RSpec of the actually allocated resources.
        """
        self.logger.info('Provision(%r)' % (urns))
        self.expire_slivers()

        the_slice, slivers = self.decode_urns(urns)
        # Note this list of privileges is really the name of an operation
        # from the privilege_table in sfa/trust/rights.py
        # Credentials will specify a list of privileges, each of which
        # confers the right to perform a list of operations.
        # EG the 'info' privilege in a credential allows the operations
        # listslices, listnodes, policy
        privileges = (PROVISION_PRIV,)
        creds = self.getVerifiedCredentials(the_slice.urn, credentials, options, privileges)

        if 'geni_rspec_version' not in options:
            # This is a required option, so error out with bad arguments.
            self.logger.error('No geni_rspec_version supplied to Provision.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version was not supplied.')
        if 'type' not in options['geni_rspec_version']:
            self.logger.error('Provision: geni_rspec_version does not contain a type field.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version does not have a type field.')
        if 'version' not in options['geni_rspec_version']:
            self.logger.error('Provision: geni_rspec_version does not contain a version field.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version does not have a version field.')

        # Look to see what RSpec version the client requested
        # Error-check that the input value is supported.
        rspec_type = options['geni_rspec_version']['type']
        if isinstance(rspec_type, basestring):
            rspec_type = rspec_type.lower().strip()
        rspec_version = options['geni_rspec_version']['version']
        if rspec_type != 'geni':
            self.logger.error('Provision: Unknown RSpec type %s requested', rspec_type)
            return self.errorResult(am3.AM_API.BAD_VERSION,
                                    'Bad Version: requested RSpec type %s is not a valid option.' % (rspec_type))
        if rspec_version != '3':
            self.logger.error('Provision: Unknown RSpec version %s requested', rspec_version)
            return self.errorResult(am3.AM_API.BAD_VERSION,
                                    'Bad Version: requested RSpec version %s is not a valid option.' % (rspec_version))
        self.logger.info("Provision requested RSpec %s (%s)", rspec_type, rspec_version)

        # Only provision slivers that are in the scheduled time frame
        now = datetime.datetime.utcnow()
        provisionable_slivers = \
            [sliver for sliver in slivers \
                 if now >= sliver.startTime() and now <= sliver.endTime()]
        slivers = provisionable_slivers

        if len(slivers) == 0:
            return self.errorResult(am3.AM_API.UNAVAILABLE,
                                    "No slivers available to provision at this time")

        max_expiration = self.min_expire(creds, self.max_lease, 
                                     ('geni_end_time' in options
                                      and options['geni_end_time']))
        for sliver in slivers:
            # Extend the lease and set to PROVISIONED
            expiration = min(sliver.endTime(), max_expiration)
            sliver.setEndTime(expiration)
            sliver.setExpiration(expiration)
            sliver.setAllocationState(STATE_GENI_PROVISIONED)
            

        # Configure user and ssh keys on nodes (dockercontainer)

        user_keys_dict = dict()
        if 'geni_users' in options:
            for user in options['geni_users']:
                if 'keys' in user and len(user['keys'])>0:
                    user_keys_dict[urn.URN(urn=user['urn']).getName()] = user['keys']

        if user_keys_dict:
            for sliver in slivers:
                if sliver.operationalState() == OPSTATE_GENI_CONFIGURING:
                    continue
                sliver.setOperationalState(OPSTATE_GENI_CONFIGURING)
                #pre-provision should be fast, so we don't do it on a seperate thread
                if sliver.resource().is_proxy:
                    allkeys = []
                    for userurn, keylist in user_keys_dict.items():
                        allkeys.extend(keylist)
                    new_user_keys_dict = { FIXED_PROXY_USER : allkeys }
                    sliver.resource().preprovision(new_user_keys_dict)
                else:
                    sliver.resource().preprovision(user_keys_dict)

                #provision might be slow, so we do it on a seperate thread
                threading.Thread(target=self.provision_install_execute_sliver,
                                 args=[the_slice, sliver]).start()
        else:
            return self.errorResult(am3.AM_API.BAD_ARGS, "No user (with SSH key) provided")
        self.dumpState()
        result = dict(geni_rspec=self.manifest_rspec(the_slice.urn, provision=True),
                      geni_slivers=[s.status() for s in slivers])
        return self.successResult(result)

    def GetVersion(self, options):
        '''Specify version information about this AM. That could
        include API version information, RSpec format and version
        information, etc. Return a dict.'''
        self.logger.info("Called GetVersion")
        reqver = [dict(type="GENI",
                       version="3",
                       schema="http://www.geni.net/resources/rspec/3/request.xsd",
                       namespace="http://www.geni.net/resources/rspec/3",
                       extensions=[])]
        adver = [dict(type="GENI",
                      version="3",
                      schema="http://www.geni.net/resources/rspec/3/ad.xsd",
                      namespace="http://www.geni.net/resources/rspec/3",
                      extensions=[])]
        api_versions = dict()
        api_versions[str(self._api_version)] = self.public_url
        credential_types = [dict(geni_type = Credential.SFA_CREDENTIAL_TYPE,
                                 geni_version = "3")]
        versions = dict(geni_api=self._api_version,
                        geni_api_versions=api_versions,
                        hrn=self._hrn,
                        urn=self._my_urn,
                        geni_am_type='gcf',
                        geni_am_code=GCF_VERSION,
                        geni_request_rspec_versions=reqver,
                        geni_ad_rspec_versions=adver,
                        geni_credential_types=credential_types)
        result = self.successResult(versions)
        # Add the top-level 'geni_api' per the AM API spec.
        result['geni_api'] = versions['geni_api']
        return result

    def PerformOperationalAction(self, urns, credentials, action, options):
        """Peform the specified action on the set of objects specified by
        urns.
        """
        self.logger.info('PerformOperationalAction(%r)' % (urns))
        self.expire_slivers()

        the_slice, slivers = self.decode_urns(urns)
        # Note this list of privileges is really the name of an operation
        # from the privilege_table in sfa/trust/rights.py
        # Credentials will specify a list of privileges, each of which
        # confers the right to perform a list of operations.
        # EG the 'info' privilege in a credential allows the operations
        # listslices, listnodes, policy
        privileges = (PERFORM_ACTION_PRIV,)
        _ = self.getVerifiedCredentials(the_slice.urn, credentials, options, privileges)

        # A place to store errors on a per-sliver basis.
        # {sliverURN --> "error", sliverURN --> "error", etc.}
        astates = []
        ostates = []
        if action == 'geni_start':
            astates = [STATE_GENI_PROVISIONED]
            ostates = [OPSTATE_GENI_NOT_READY, OPSTATE_GENI_READY, OPSTATE_GENI_CONFIGURING]
        elif action == 'geni_restart':
            astates = [STATE_GENI_PROVISIONED]
            ostates = [OPSTATE_GENI_READY]
        elif action == 'geni_stop':
            astates = [STATE_GENI_PROVISIONED]
            ostates = [OPSTATE_GENI_READY]
        elif action == 'geni_update_users':
            astates = [STATE_GENI_PROVISIONED]
            ostates = [OPSTATE_GENI_READY]
        elif action == 'geni_reload':
            astates = [STATE_GENI_PROVISIONED]
            ostates = [OPSTATE_GENI_READY]

        else:
            msg = "Unsupported: action %s is not supported" % (action)
            raise ApiErrorException(am3.AM_API.UNSUPPORTED, msg)

        # Handle best effort. Look ahead to see if the operation
        # can be done. If the client did not specify best effort and
        # any resources are in the wrong state, stop and return an error.
        # But if the client specified best effort, trundle on and
        # do the best you can do.
        errors = collections.defaultdict(str)
        for sliver in slivers:
            # ensure that the slivers are provisioned
            if (sliver.allocationState() not in astates
                or sliver.operationalState() not in ostates):
                msg = "%d: Sliver %s is not in the right state for action %s (current state = %s %s)."
                msg = msg % (am3.AM_API.UNSUPPORTED, sliver.urn(), action, sliver.allocationState(), sliver.operationalState())
                errors[sliver.urn()] = msg
        best_effort = False
        if 'geni_best_effort' in options:
            best_effort = bool(options['geni_best_effort'])
        if not best_effort and errors:
            raise ApiErrorException(am3.AM_API.UNSUPPORTED,
                                    "\n".join(errors.values()))

        def thread_restart(sliver):
            ret = sliver.resource().restart()
            if not ret:
                sliver.setOperationalState(OPSTATE_GENI_FAILED)
                return
            #now wait until container is up again
            if sliver.resource().waitForSshConnection() is not True:
                sliver.setOperationalState(OPSTATE_GENI_FAILED)
                sliver.resource().deprovision()
                return
            sliver.setOperationalState(OPSTATE_GENI_READY)
            self.dumpState()

        # Perform the state changes:
        for sliver in slivers:
            if (action == 'geni_start'):
                if (sliver.allocationState() in astates
                    and sliver.operationalState() in ostates):
                    pass
            elif (action == 'geni_reload'):
                if (sliver.allocationState() in astates
                    and sliver.operationalState() in ostates):
                    sliver.setOperationalState(OPSTATE_GENI_CONFIGURING)
                    threading.Thread(target=self.provision_install_execute_sliver,
                                     args=[the_slice, sliver]).start()
            elif (action == 'geni_restart'):
                if (sliver.allocationState() in astates
                    and sliver.operationalState() in ostates):
                    sliver.setOperationalState(OPSTATE_GENI_CONFIGURING)
                    threading.Thread(target=thread_restart, args=[sliver]).start()
            elif (action == 'geni_stop'):
                if (sliver.allocationState() in astates
                    and sliver.operationalState() in ostates):
                    try:
                        #not perfect: deprovision also prevents reprovisioning
                        sliver.resource().deprovision()
                    except:
                        #ignore errors when deprovisioning
                        pass
                    sliver.setOperationalState(OPSTATE_GENI_NOT_READY)
            elif (action == 'geni_update_users'):
                user_keys_dict = dict()
                if 'geni_users' in options:
                    for user in options['geni_users']:
                        if 'keys' in user and len(user['keys'])>0:
                            user_keys_dict[urn.URN(urn=user['urn']).getName()] = user['keys']
                if sliver.resource().is_proxy:
                    allkeys = sliver.resource().user_keys_dict[FIXED_PROXY_USER]
                    if allkeys is None:
                        self.logger.warn('geni_update_users allkeys init: Failed to find existing user keys.')
                        allkeys = []
                    else:
                        self.logger.info('geni_update_users allkeys init: Found %d existing user keys.' % len(allkeys))
                    for userurn, keylist in user_keys_dict.items():
                        allkeys.extend(keylist)
                    new_user_keys_dict = {FIXED_PROXY_USER: allkeys}
                    self.logger.info('Updating proxy sliver keys %d' % len(allkeys))
                    sliver.resource().updateUser(new_user_keys_dict, force=True)
                else:
                    self.logger.info('Updating sliver keys %d' % len(user_keys_dict))
                    sliver.resource().updateUser(user_keys_dict)
            else:
                # This should have been caught above
                msg = "Unsupported: action %s is not supported" % (action)
                raise ApiErrorException(am3.AM_API.UNSUPPORTED, msg)
        self.dumpState()
        return self.successResult([s.status(errors[s.urn()])
                                   for s in slivers])

    def Describe(self, urns, credentials, options):
        """Generate a manifest RSpec for the given resources.
        """
        self.logger.info('Describe(%r)' % (urns))
        self.expire_slivers()
        # APIv3 spec says that a slice with nothing local should
        # give an empty manifest, not an error
        try:
            the_slice, slivers = self.decode_urns(urns)
        except ApiErrorException as ae:
            if ae.code == am3.AM_API.SEARCH_FAILED and "Unknown slice" in ae.output:
                # This is ok
                slivers = []
                the_slice = Slice(urns[0])
            else:
                raise ae

        privileges = (SLIVERSTATUSPRIV,)
        self.getVerifiedCredentials(the_slice.urn, credentials, options, privileges)

        if 'geni_rspec_version' not in options:
            # This is a required option, so error out with bad arguments.
            self.logger.error('No geni_rspec_version supplied to Describe.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version was not supplied.')
        if 'type' not in options['geni_rspec_version']:
            self.logger.error('Describe: geni_rspec_version does not contain a type field.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version does not have a type field.')
        if 'version' not in options['geni_rspec_version']:
            self.logger.error('Describe: geni_rspec_version does not contain a version field.')
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Arguments: option geni_rspec_version does not have a version field.')

        # Look to see what RSpec version the client requested
        # Error-check that the input value is supported.
        rspec_type = options['geni_rspec_version']['type']
        if isinstance(rspec_type, basestring):
            rspec_type = rspec_type.lower().strip()
        rspec_version = options['geni_rspec_version']['version']
        if rspec_type != 'geni':
            self.logger.error('Describe: Unknown RSpec type %s requested', rspec_type)
            return self.errorResult(am3.AM_API.BAD_VERSION,
                                    'Bad Version: requested RSpec type %s is not a valid option.' % (rspec_type))
        if rspec_version != '3':
            self.logger.error('Describe: Unknown RSpec version %s requested', rspec_version)
            return self.errorResult(am3.AM_API.BAD_VERSION,
                                    'Bad Version: requested RSpec version %s is not a valid option.' % (rspec_version))
        self.logger.info("Describe requested RSpec %s (%s)", rspec_type, rspec_version)

        manifest = self.manifest_rspec(the_slice.getURN(), provision=True)
        self.logger.debug("Result is now \"%s\"", manifest)
        # Optionally compress the manifest
        if 'geni_compressed' in options and options['geni_compressed']:
            try:
                manifest = base64.b64encode(zlib.compress(manifest))
            except Exception as exc:
                self.logger.error("Error compressing and encoding resource list: %s", traceback.format_exc())
                raise Exception("Server error compressing resource list", exc)
        value = dict(geni_rspec=manifest,
                     geni_urn=the_slice.urn,
                     geni_slivers=[s.status() for s in slivers])
        return self.successResult(value)

    def Delete(self, urns, credentials, options):
        """Stop and completely delete the named slivers and/or slice."""
        self.logger.info('Delete(%r)' % (urns))
        self.expire_slivers()

        the_slice, slivers = self.decode_urns(urns)
        privileges = (DELETESLIVERPRIV,)

        self.getVerifiedCredentials(the_slice.urn, credentials, options, privileges)

        # Grab the user_urn
        user_urn = gid.GID(string=options['geni_true_caller_cert']).get_urn()

        # If we get here, the credentials give the caller
        # all needed privileges to act on the given target.
        if the_slice.isShutdown():
            self.logger.info("Slice %s not deleted because it is shutdown",
                             the_slice.urn)
            return self.errorResult(am3.AM_API.UNAVAILABLE,
                                    ("Unavailable: Slice %s is unavailable."
                                     % (the_slice.urn)))
        resources = [sliver.resource() for sliver in slivers]
        self._agg.deallocate(the_slice.urn, resources)
        self._agg.deallocate(user_urn, resources)

        delete_ev = threading.Event()

        def thread_delete(slivers):
            for sliver in slivers:
                slyce = sliver.slice()
                slyce.delete_sliver(sliver)
            delete_ev.set()
            # If slice is now empty, delete it.
            if not slyce.slivers():
                try:
                    for i in self._slices[slyce.urn].images_to_delete:
                        self.DockerManager.deleteImage(slyce.urn+"::"+i)
                except:
                    pass
                self.logger.debug("Deleting empty slice %r", slyce.urn)
                del self._slices[slyce.urn]
            self.dumpState()

        threading.Thread(target=thread_delete, args=[slivers]).start()

        #Wait, unless it takes too long (0.5 seconds)
        delete_ev.wait(timeout=0.5)

        return self.successResult([s.status() for s in slivers])

    def Status(self, urns, credentials, options):
        '''Report as much as is known about the status of the resources
        in the sliver. The AM may not know.
        Return a dict of sliver urn, status, and a list of dicts resource
        statuses.'''

        # Loop over the resources in a sliver gathering status.
        self.logger.info('Status(%r)' % (urns))
        self.expire_slivers()
        the_slice, slivers = self.decode_urns(urns)
        privileges = (SLIVERSTATUSPRIV,)
        self.getVerifiedCredentials(the_slice.urn, credentials, options, privileges)
        geni_slivers = list()
        for sliver in slivers:
            expiration = self.rfc3339format(sliver.expiration())
            start_time = self.rfc3339format(sliver.startTime())
            # end_time = self.rfc3339format(sliver.endTime())
            allocation_state = sliver.allocationState()
            operational_state = sliver.operationalState()
            error = sliver.resource().error
            geni_slivers.append(dict(geni_sliver_urn=sliver.urn(),
                                     geni_expires=expiration,
                                     geni_start_time=start_time,
                                     # geni_end_time=end_time,
                                     geni_allocation_status=allocation_state,
                                     geni_operational_status=operational_state,
                                     geni_error=''))
        result = dict(geni_urn=the_slice.urn,
                      geni_slivers=[s.status(s.resource().error) for s in slivers])
        return self.successResult(result)

    def Renew(self, urns, credentials, expiration_time, options):
        '''Renew the local sliver that is part of the named Slice
        until the given expiration time (in UTC with a TZ per RFC3339).
        Requires at least one credential that is valid until then.
        Return False on any error, True on success.'''

        out = super(DockerAggregateManager,self).Renew(urns, credentials, expiration_time, options)
        self.dumpState()
        return out

    # See https://www.protogeni.net/trac/protogeni/wiki/RspecAdOpState
    def advert_header(self):
        schema_locs = ["http://www.geni.net/resources/rspec/3",
                       "http://www.geni.net/resources/rspec/3/ad.xsd",
                       "http://www.geni.net/resources/rspec/ext/opstate/1",
                       "http://www.geni.net/resources/rspec/ext/opstate/1/ad.xsd"]
        adv_header = etree.Element("rspec", nsmap={None : "http://www.geni.net/resources/rspec/3", "xsi" : "http://www.w3.org/2001/XMLSchema-instance", "ns3" : "http://www.protogeni.net/resources/rspec/ext/emulab/1"}, attrib={"{http://www.w3.org/2001/XMLSchema-instance}schemaLocation" : ' '.join(schema_locs)})
        adv_header.set("type", "advertisement")
        rspec_opstate = etree.SubElement(adv_header, "rspec_opstate", nsmap={None : "http://www.geni.net/resources/rspec/ext/opstate/1"})
        rspec_opstate.set("aggregate_manager_id", self._my_urn)
        rspec_opstate.set("start", "geni_notready")
        etree.SubElement(rspec_opstate, "sliver_type").set("name", "dockercontainer")
        state = etree.SubElement(rspec_opstate, "state")
        state.set("name", "geni_notready")
        action = etree.SubElement(state, "action")
        action.set("name", "geni_start")
        action.set("next", "geni_ready")
        etree.SubElement(action, "description").text ="Transition the node to a ready state."
        etree.SubElement(state, "description").text = "DockerContainers are immediately ready once started."
        state=etree.SubElement(rspec_opstate, "state")
        state.set("name", "geni_ready")
        etree.SubElement(state, "description").text = "DockerContainer node is up and ready to use."
        action = etree.SubElement(state, "action")
        action.set("name", "geni_restart")
        action.set("next", "geni_ready")
        etree.SubElement(action, "description").text = "Reboot the node"
        action = etree.SubElement(state, "action")
        action.set("name", "geni_stop")
        action.set("next", "geni_notready")
        etree.SubElement(action, "description").text = "Power down or stop the node."
        return adv_header

    def manifest_rspec(self, slice_urn, provision=False):
        rspec = etree.parse(StringIO(self._slices[slice_urn].request_rspec))
        rspec.getroot().set("type", "manifest")
        ns=rspec.getroot().nsmap.get(None)
        
        services = rspec.getroot().xpath("x:node/x:services", namespaces={'x':ns})
        i_exec = 0
        for s in services:
            executes= s.xpath("x:execute", namespaces={'x':ns})
            if len(executes) > 0:
                for e in executes:
                    tmp = etree.Element("{http://www.fed4fire.eu/docker_am}execute_logs")
                    tmp.set("log","/tmp/startup-"+str(i_exec)+".txt")
                    tmp.set("status","/tmp/startup-"+str(i_exec)+".status")
                    tmp.set("command","/tmp/startup-"+str(i_exec)+".sh")
                    # e.getparent().remove(e)
                    s.append(tmp)
                    i_exec+=1
        for node in rspec.getroot().getchildren():
            for s in self._slices[slice_urn].slivers():
                if node.get("client_id") == s.resource().external_id and node.get("component_manager_id") == self._my_urn:
                    node.set("component_id", s.resource().urn(self._urn_authority))
                    node.set("sliver_id", s.urn())
                    if provision:
                        services = None
                        for c in node.getchildren():
                            if c.tag == "{"+ns+"}"+"services":
                                services = c
                                break
                        if services is None:
                            services = etree.Element("services")
                        services.extend(s.resource().manifestAuth())
                        s.resource().addManifestProxyServiceElements(services)
                        node.append(services)
        return etree.tostring(rspec, pretty_print=True, xml_declaration=True, encoding='utf-8')
            
        

    def resources(self, available=None):
        """Get the list of managed resources. If available is not None,
        it is interpreted as boolean and only resources whose availability
        matches will be included in the returned list.
        """
        result = list(self._agg.catalog())
        if available is not None:
            result = [r for r in result if r.available is available]
        return result

    def expire_slivers(self):
        """Look for expired slivers and clean them up. Ultimately this
        should be run by a daemon, but until then, it is called at the
        beginning of all methods.
        """
        if EXPIRE_LOCK.locked():
            return None
        EXPIRE_LOCK.acquire()
        expired = list()
        now = datetime.datetime.utcnow()
        for slyce in self._slices.values():
            for sliver in slyce.slivers():
                self.logger.debug('Checking sliver %s (expiration = %r) at %r',
                                  sliver.urn(), sliver.expiration(), now)
                if sliver.expiration() < now:
                    self.logger.debug('Expring sliver %s (expiration = %r) at %r',
                                      sliver.urn(), sliver.expiration(), now)
                    expired.append(sliver)
        dump=False
        if len(expired)>0:
            self.logger.info('Expiring %d slivers', len(expired))
            dump=True
        for sliver in expired:
            slyce = sliver.slice()
            slyce.delete_sliver(sliver)
            # If slice is now empty, delete it.
            if len(slyce.slivers()) == 0:
                self.logger.debug("Deleting empty slice %r", slyce.urn)
                try:
                    for i in self._slices[slyce.urn].images_to_delete:
                        self.DockerManager.deleteImage(slyce.urn+"::"+i)
                except:
                    pass
                del self._slices[slyce.urn]
        if dump: #If something has changed, save data
            self.dumpState()
        EXPIRE_LOCK.release()
        
            
    def dumpState(self):
        DUMP_LOCK.acquire()
        try:
            TMP_STATE_FILENAME = STATE_FILENAME+".tmp"
            open(TMP_STATE_FILENAME, 'w').close()
            s = open(TMP_STATE_FILENAME, "wb")
            p = pickle.Pickler(s, pickle.HIGHEST_PROTOCOL)
            p.dump(self._agg)
            p.dump(self._slices)
            p.dump(self.proxy_dockermaster)
            p.dump(self.public_url)
            s.close()
            copyfile(TMP_STATE_FILENAME, STATE_FILENAME)
        except RuntimeError:
            print 'error in DumpState'
            pass
        DUMP_LOCK.release()

    def expireSliversDaemon(self):
        while True:
            time.sleep(300)
            self.expire_slivers()
    
class Slice(am3.Slice):
    def __init__(self, urn):
        super(Slice,self).__init__(urn)
        self.request_rspec = None
        self.images_to_delete = list()
