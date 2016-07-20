#----------------------------------------------------------------------
# Copyright (c) 2012-2016 Raytheon BBN Technologies
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
sys.path.insert(1, '../geni-tools/src')

import base64
import collections
import datetime
import dateutil.parser
import logging
import os
import traceback
import uuid
import xml.dom.minidom as minidom
import xmlrpclib
import zlib
import threading
import time
import gcf.geni.am.am3 as am3
import pickle

from StringIO import StringIO
from lxml import etree
from gcf.geni.am.aggregate import Aggregate
from dockercontainer import DockerContainer
from dockermaster import DockerMaster
from gcf import geni
from gcf.geni.util.tz_util import tzd
from gcf.geni.util.urn_util import publicid_to_urn
from gcf.geni.util import urn_util as urn
from gcf.geni.SecureXMLRPCServer import SecureXMLRPCServer

from gcf.sfa.trust.credential import Credential
from gcf.sfa.trust.abac_credential import ABACCredential
from gcf.gcf_version import GCF_VERSION

from gcf.omnilib.util import credparsing as credutils

from gcf.geni.auth.base_authorizer import *
from gcf.geni.am.am_method_context import AMMethodContext
from gcf.geni.am.api_error_exception import ApiErrorException

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
DUMP_LOCK = threading.Lock()


class ReferenceAggregateManager(am3.ReferenceAggregateManager):

    # root_cert is a single cert or dir of multiple certs
    # that are trusted to sign credentials
    def __init__(self, root_cert, urn_authority, url, **kwargs):
        super(ReferenceAggregateManager,self).__init__(root_cert,urn_authority,url,**kwargs)
        self._urn_authority = "IDN "+urn_authority #IDN docker.ilabt.iminds.be
        self._my_urn = publicid_to_urn("%s %s %s" % (self._urn_authority, 'authority', 'am'))
        thread_sliver_daemon = threading.Thread(target=self.expireSliversDaemon)
        thread_sliver_daemon.daemon=True
        thread_sliver_daemon.start()
        try:
            s=open('agg.dat', 'r')
            self._agg = pickle.load(s)
            s.close()
            s=open('slices.dat', 'r')
            self._slices = pickle.load(s)
            s.close()
        except Exception as e:
            self.logger.info(str(e))
            self.logger.info("Load new instance")
            self._agg = Aggregate()
            self._agg.add_resources([DockerMaster(self._agg, 20)])
            self.dumpState()
        self.logger.info("Running %s AM v%d code version %s", self._am_type, self._api_version, GCF_VERSION)

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
        if isinstance(rspec_type, str):
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
        available = 'geni_available' in options and options['geni_available']
        resource_xml = ""
        adv_header = self.advert_header()
        for r in all_resources:
            if available and not r.available:
                continue
            #resource_xml = resource_xml + self.advert_resource(r)
            adv_header.append(self.advert_resource(r))
        result = etree.tostring(adv_header, pretty_print=True, xml_declaration=True, encoding='utf-8')
        # Optionally compress the result
        if 'geni_compressed' in options and options['geni_compressed']:
            try:
                result = base64.b64encode(zlib.compress(result))
            except Exception, exc:
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
        except Exception, exc:
            self.logger.error("Cannot create sliver %s. Exception parsing rspec: %s" % (slice_urn, exc))
            return self.errorResult(am3.AM_API.BAD_ARGS,
                                    'Bad Args: RSpec is unparseable')

        # Look at the version of the input request RSpec
        # Make sure it is supported
        # Then make sure that you return an RSpec in the same format
        # EG if both V1 and V2 are supported, and the user gives V2 request,
        # then you must return a V2 manifest and not V1

        #Get only resources with sliver_types required in the rspec
        sliver_types = []
        for node in etree.parse(StringIO(rspec)).getroot().getchildren():
            if node.get("exclusive") == "true":
                return self.errorResult(am3.AM_API.UNSUPPORTED, "Can't allocate an exclusive resource, not supported")
            for t in node.getchildren():
                if t.get("name") not in sliver_types:
                    sliver_types.append(t.get("name"))
        available = self.resources(available=True, sliver_types=sliver_types)

        # Note: This only handles unbound nodes. Any attempt by the client
        # to specify a node is ignored.
        unbound = list()
        for elem in rspec_dom.documentElement.getElementsByTagName('node'):
            if elem.getAttribute("component_manager_id") == self._my_urn:
                unbound.append(elem)

        resources = list()
        for elem in unbound:
            client_id = elem.getAttribute('client_id')
            sliver_type = elem.getElementsByTagName('sliver_type')[0]
            if sliver_type != "": sliver_type = sliver_type.getAttribute('name')
            component_id = elem.getAttribute('component_id')
            if component_id == "": component_id=None
            resource = None
            for r in available:
                _type = r.genAdvertNode("", "").xpath('sliver_type/@name')#Available sliver types for this resource
                if sliver_type in _type:
                    resource = r.getResource(component_id)
                    if component_id is not None and (resource is None or resource.id != component_id): #resource with Component_id not found
                        resource = None
                        continue
                    if resource is None: #Dockermaster is empty
                        available.remove(r)
                    try: #Resource returned by DockerMaster are not listed in "available" list, so ignore Exception
                        available.remove(resource)
                    except:
                        pass
                    break
            if resource is None: # There aren't enough resources
                self.logger.error('Too big: not enought %s available',sliver_type)
                for r in resources:
                    r.deallocate()
                return self.errorResult(am3.AM_API.TOO_BIG, 'Too Big: insufficient resources to fulfill request')
            resource.external_id = client_id
            resource.available = False
            resource.sliver_type=sliver_type
            resources.append(resource)

        # determine max expiration time from credentials
        # do not create a sliver that will outlive the slice!
        expiration = self.min_expire(creds, self.max_alloc,
                                     ('geni_end_time' in options
                                      and options['geni_end_time']))

        # determine end time as min of the slice 
        # and the requested time (if any)
        end_time = self.min_expire(creds, 
                                   requested=('geni_end_time' in options 
                                              and options['geni_end_time']))

        # determine the start time as bounded by slice expiration and 'now'
        now = datetime.datetime.utcnow()
        start_time = now
        if 'geni_start_time' in options:
            # Need to parse this into datetime
            start_time_raw = options['geni_start_time']
            start_time = self._naiveUTC(dateutil.parser.parse(start_time_raw))
        start_time = max(now, start_time)
        if (start_time > self.min_expire(creds)):
            return self.errorResult(am3.AM_API.BAD_ARGS, 
                                    "Can't request start time on sliver after slice expiration")

        # determine max expiration time from credentials
        # do not create a sliver that will outlive the slice!
        expiration = self.min_expire(creds, self.max_alloc,
                                     ('geni_end_time' in options
                                      and options['geni_end_time']))

        # If we're allocating something for future, give a window
        # from start time in which to reserve
        if start_time > now:
            expiration = min(start_time + self.max_alloc, 
                             self.min_expire(creds))

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
                template = "Slice %s already has slivers at requested time"
                self.logger.error(template % (slice_urn))
                for sliver in newslice.slivers():
                    sliver.resource().deallocate()
                return self.errorResult(am3.AM_API.ALREADY_EXISTS,
                                        template % (slice_urn))
        else:
            newslice = am3.Slice(slice_urn)

        for resource in resources:
            sliver = newslice.add_resource(resource)
            sliver.setExpiration(expiration)
            sliver.setStartTime(start_time)
            sliver.setEndTime(end_time)
            sliver.setAllocationState(STATE_GENI_ALLOCATED)
        self._agg.allocate(slice_urn, newslice.resources())
        self._agg.allocate(user_urn, newslice.resources())
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
        if isinstance(rspec_type, str):
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
            sliver.setOperationalState(OPSTATE_GENI_CONFIGURING)

        # Configure user and ssh keys on nodes (dockercontainer)

        def thread_provisionning(sliver, user, keys):
            sliver.resource().provision(user, keys)
            sliver.setOperationalState(OPSTATE_GENI_READY)
            
        if 'geni_users' in options:
            i=0
            for user in options['geni_users']:
                if 'keys' in options['geni_users'][i] and len(options['geni_users'][i]['keys'])>0:
                    for sliver in slivers:
                        sliver.resource().preprovision(urn.URN(urn=user['urn']).getName())
                        threading.Thread(target=thread_provisionning, args=[sliver, urn.URN(urn=user['urn']).getName(), user['keys']]).start()
                else:
                    sliver.setOperationalState(OPSTATE_GENI_PENDING_ALLOCATION)
                    sliver.setAllocationState(STATE_GENI_ALLOCATED)
                    return self.errorResult(am3.AM_API.BAD_ARGS, "No SSH public key provided")
                i+=1
        self.dumpState()
        result = dict(geni_rspec=self.manifest_rspec(the_slice.urn, provision=True),
                      geni_slivers=[s.status() for s in slivers])
        return self.successResult(result)

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
                msg = "%d: Sliver %s is not in the right state for action %s."
                msg = msg % (am3.AM_API.UNSUPPORTED, sliver.urn(), action)
                errors[sliver.urn()] = msg
        best_effort = False
        if 'geni_best_effort' in options:
            best_effort = bool(options['geni_best_effort'])
        if not best_effort and errors:
            raise ApiErrorException(am3.AM_API.UNSUPPORTED,
                                    "\n".join(errors.values()))

        # Perform the state changes:
        for sliver in slivers:
            if (action == 'geni_start'):
                if (sliver.allocationState() in astates
                    and sliver.operationalState() in ostates):
                    pass
            elif (action == 'geni_restart'):
                if (sliver.allocationState() in astates
                    and sliver.operationalState() in ostates):
                    sliver.setOperationalState(OPSTATE_GENI_READY)
            elif (action == 'geni_stop'):
                if (sliver.allocationState() in astates
                    and sliver.operationalState() in ostates):
                    sliver.setOperationalState(OPSTATE_GENI_NOT_READY)
            elif (action == 'geni_update_users'):
                for u in options['geni_users']:
                    name = urn.URN(urn=u['urn']).getName()
                    sliver.resource().updateUser(name, u['keys'])
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
        except ApiErrorException, ae:
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
        if isinstance(rspec_type, str):
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

        manifest_body = self.manifest_header()
        for sliver in slivers:
            manifest_body = self.manifest_sliver(sliver, manifest_body, provision=True)
        manifest = etree.tostring(manifest_body, pretty_print=True, xml_declaration=True, encoding='utf-8')
        self.logger.debug("Result is now \"%s\"", manifest)
        # Optionally compress the manifest
        #A DECOMMENTER
        #        if 'geni_compressed' in options and options['geni_compressed']:
            # try:
            #     manifest = base64.b64encode(zlib.compress(manifest))
            # except Exception, exc:
            #     self.logger.error("Error compressing and encoding resource list: %s", traceback.format_exc())
            #     raise Exception("Server error compressing resource list", exc)
        value = dict(geni_rspec=manifest,
                     geni_urn=the_slice.urn,
                     geni_slivers=[s.status() for s in slivers])
        return self.successResult(value)



    def Renew(self, urns, credentials, expiration_time, options):
        '''Renew the local sliver that is part of the named Slice
        until the given expiration time (in UTC with a TZ per RFC3339).
        Requires at least one credential that is valid until then.
        Return False on any error, True on success.'''

        self.logger.info('Renew(%r, %r)' % (urns, expiration_time))
        self.expire_slivers()
        the_slice, slivers = self.decode_urns(urns)

        privileges = (RENEWSLIVERPRIV,)
        creds = self.getVerifiedCredentials(the_slice.urn, credentials, options, privileges)

        # All the credentials we just got are valid
        expiration = self.min_expire(creds, self.max_lease)
        requested = dateutil.parser.parse(str(expiration_time), tzinfos=tzd)


        # Per the AM API, the input time should be TZ-aware
        # But since the slice cred may not (per ISO8601), convert
        # it to naiveUTC for comparison
        requested = self._naiveUTC(requested)


        # If geni_extend_alap option provided, use the earlier 
        # of the requested time and max expiration as the expiration time
        if 'geni_extend_alap' in options and options['geni_extend_alap']:
            if expiration < requested:
                self.logger.info("Got geni_extend_alap: revising slice %s renew request from %s to %s", urns, requested, expiration)
                requested = expiration

        now = datetime.datetime.utcnow()
        if requested > expiration:
            # Fail the call, the requested expiration exceeds the slice expir.
            msg = (("Out of range: Expiration %s is out of range"
                   + " (past last credential expiration of %s).")
                   % (expiration_time, expiration))
            self.logger.error(msg)
            return self.errorResult(am3.AM_API.OUT_OF_RANGE, msg)
        elif requested < now:
            msg = (("Out of range: Expiration %s is out of range"
                   + " (prior to now %s).")
                   % (expiration_time, now.isoformat()))
            self.logger.error(msg)
            return self.errorResult(am3.AM_API.OUT_OF_RANGE, msg)
        else:
            # Renew all the named slivers
            for sliver in slivers:
                sliver.setExpiration(requested)
                end_time = max(sliver.endTime(), requested)
                sliver.setEndTime(end_time)

        geni_slivers = [s.status() for s in slivers]
        self.dumpState()
        return self.successResult(geni_slivers)

    def advert_resource(self, resource):
        return resource.genAdvertNode(self._urn_authority, self._my_urn)

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

    def manifest_header(self):
        manifest_header = etree.Element("rspec", nsmap={None : "http://www.geni.net/resources/rspec/3", "xsi" : "http://www.w3.org/2001/XMLSchema-instance"}, attrib={"{http://www.w3.org/2001/XMLSchema-instance}schemaLocation" : "http://www.geni.net/resources/rspec/3 http://www.geni.net/resources/rspec/3/manifest.xsd"})
        manifest_header.set("type", "manifest")
        return manifest_header

    def manifest_sliver(self, sliver, manifest, provision=False):
        s = etree.SubElement(manifest, "node")
        s.set("client_id", sliver.resource().external_id)
        s.set("component_id", sliver.resource().urn(self._urn_authority))
        s.set("component_manager_id", self._my_urn)
        s.set("sliver_id", sliver.urn())
        if provision:
            s=sliver.resource().manifestDetails(s)            
        return manifest
    

    def manifest_slice(self, slice_urn, manifest, provision=False):
        for sliver in self._slices[slice_urn].slivers():
            manifest = self.manifest_sliver(sliver, manifest, provision)
        return manifest

    def manifest_rspec(self, slice_urn, provision=False):
        return etree.tostring(self.manifest_slice(slice_urn, self.manifest_header(), provision), pretty_print=True, xml_declaration=True, encoding='utf-8')

    def resources(self, available=None, sliver_types=None):
        """Get the list of managed resources. If available is not None,
        it is interpreted as boolean and only resources whose availability
        matches will be included in the returned list.
        """
        result = self._agg.catalog()
        if available is not None:
            result = [r for r in result if r.available is available]
        if sliver_types is not None:
            for r in list(result): #Avoid loop troubles due to delete
                types = r.genAdvertNode("", "").xpath('sliver_type')
                found = None
                for t in types:
                    if t.get("name") in sliver_types : found = True
                if not found: result.remove(r)
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
                del self._slices[slyce.urn]
        EXPIRE_LOCK.release()
        if dump: #If something has changed, save data
            self.dumpState()
            
    def dumpState(self):
        DUMP_LOCK.acquire()
        s = open("agg.dat", "w")
        pickle.dump(self._agg, s)
        s.close()
        s = open("slices.dat", "w")
        pickle.dump(self._slices, s)
        s.close()
        DUMP_LOCK.release()

    def expireSliversDaemon(self):
        while True:
            time.sleep(300)
            self.expire_slivers()
            
            

    
