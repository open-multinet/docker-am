#----------------------------------------------------------------------
# Copyright (c) 2015 Inria by David Margery
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
An empty aggregate manager delegate 
"""

from ConfigParser import SafeConfigParser
import logging

import gcf.geni.am.am3 as am3
from gcf.sfa.trust.certificate import Certificate

class Slice(object):
    """calls to delegate.decode_urns expect to get back
    a object on wich getURN() can be called. This class to implement
    this in a very basic manner.
    """

    def __init__(self,urn_str):
        self.urn=urn_str

    def getURN(self):
        return self.urn

class MyTestbedDelegate(am3.ReferenceAggregateManager):
    CONFIG_LOCATIONS=["/etc/geni-tools-delegate/testbed.ini", 
                     "testbed.ini"]

    def __init__(self, root_cert, urn_authority, url, **kwargs):
        super(MyTestbedDelegate,self).__init__(root_cert,urn_authority,url,**kwargs)

        self.logger=logging.getLogger('geni-delegate')

        self.aggregate_manager_id=self.getAggregateManagerId(kwargs['certfile'])
        self._my_urn=self.aggregate_manager_id

        urn_components=self.aggregate_manager_id.split('+')
        self.urn_authority_prefix="%s+%s"%(urn_components[0],urn_components[1])

        self.parser=SafeConfigParser()
        found_configs=self.parser.read(self.CONFIG_LOCATIONS)
        if len(found_configs) < 1:
            self.logger.warn('Did not find testbed configuration from %s' % self.CONFIG_LOCATIONS)
        else:
            self.logger.info("Read configuration from the following sources: %s" % found_configs)
        self.logger.debug("Starting testbed aggregate manager delegate for urn %s at url %s"% (urn_authority,url))


    def GetVersion(self, options):
        return super(MyTestbedDelegate, self).GetVersion(options)


    def ListResources(self, credentials, options):
        privileges = ()
        self.getVerifiedCredentials(None,
                                    credentials, 
                                    options,
                                    privileges)
        # If we get here, the credentials give the caller
        # all needed privileges to act on the given target.



    def Allocate(self, slice_urn, credentials, rspec, options):
        privileges = (am3.ALLOCATE_PRIV,)

        creds=self.getVerifiedCredentials(slice_urn, 
                                          credentials, 
                                          options, 
                                          privileges)
        # If we get here, the credentials give the caller
        # all needed privileges to act on the given target.


    def Provision(self, urns, credentials, options):
        privileges = (am3.PROVISION_PRIV,)
        creds = self.getverifiedcredentials(the_slice.urn, 
                                            credentials, 
                                            options, 
                                            privileges)


    def PerformOperationalAction(self, urns, credentials, action, options):
        privileges = (am3.PERFORM_ACTION_PRIV,)
        creds = self.getVerifiedCredentials(the_slice.urn, 
                                            credentials, 
                                            options, 
                                            privileges)


    def Status(self, urns, credentials, options):
        privileges = (am3.SLIVERSTATUSPRIV,)
        creds=self.getVerifiedCredentials(the_slice.urn, 
                                          credentials, 
                                          options, 
                                          privileges)



    def Describe(self, urns, credentials, options):
        privileges = (am3.SLIVERSTATUSPRIV,)
        creds= self.getVerifiedCredentials(the_slice.urn, 
                                           credentials, 
                                           options, 
                                           privileges)


    def Renew(self, urns, credentials, expiration_time, options):
        privileges = (am3.RENEWSLIVERPRIV,)
        creds = self.getVerifiedCredentials(the_slice.urn, 
                                            credentials, 
                                            options, 
                                            privileges)


    def Shutdown(self, slice_urn, credentials, options):
        privileges = (am3.SHUTDOWNSLIVERPRIV,)
        self.getVerifiedCredentials(slice_urn, 
                                    credentials, 
                                    options, 
                                    privileges)
        return self.successResult(True)

    def decode_urns(self,urns,**kwargs):
        """Several methods need to map URNs to slivers and/or deduce
        a slice based on the slivers specified.

        When called from AMMethodContext, kwargs will have 2 keys
        (credentials and options), with the same values as the credentials
        and options parameters of the AMv3 API entry points. This can be 
        usefull for delegates derived from the ReferenceAggregateManager, 
        but is not used in this reference implementation.

        Returns a slice and a list of slivers.
        """
        # All delegate methods implementing AMv3 API are called in a context 
        # (of class AMMethodContext that is created with a call to decode_urns
        # when urns are passed as arguments to the call.
        #
        # When a slice is found from the urns, and slice_urn is not part of the arguments
        # to the call, this sets slice_urn as part of the args to be used
        # by the authorizer when taking decisions, with a call to getURN on the first item 
        # returned by decode_urns
        return super(MyTestbedDelegate, self).decode_urns(urns, **kwargs)
        

    def getAggregateManagerId(self, certfile=None):
        if not hasattr(self, 'aggregate_manager_id'):
            cert=Certificate(filename=certfile)
            altSubject=cert.get_extension('subjectAltName')
            altSubjects=altSubject.split(', ')  
            publicids=[s for s in altSubjects if 'publicid' in s]
            if len(publicids) < 1:
                raise Exception("Could not get aggregate manager id from subjectAltName as no altName has the string publicid")
            self.aggregate_manager_id=publicids[0][4:]
            self.logger.info("Will run am with %s as component_manager_id"%self.aggregate_manager_id)
        return self.aggregate_manager_id
