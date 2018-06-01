Docker MA Addon: Terms And Conditions site
==========================================

The ``terms_conditions`` dir contains everything needed adding a "Terms & Conditions" site to the docker AM.
Users that do not accept the terms and conditions on this site, will be denied access.

Site customization
------------------

You can change the following files to customize the site:
* ``terms_conditions/terms_conditions.html``
* ``terms_conditions/terms_conditions.js``
* ``terms_conditions/terms_conditions.css``

Accept parts customization
--------------------------

In the original site, 2 terms and conditions sections need to be approved, before site access is granted. 
This is reflected in the json that is sent to the web-api part of the site 
(see ``on_toggle_accept`` in ``terms_conditions/terms_conditions.js``), for example:

    {
        'accept_main': true,
        'accept_userdata': true
    }

You can change names of these sub-parts as needed. You can also add as many sub parts as you like, or use just one sub-part.

To make these changes:
* Change the site itself (edit the html and js)
* Edit ``TermsAndConditionsSite.register_accept`` and ``TermsAndConditionsHelper.derive_testbed_access``


Accept Duration customization
-----------------------------

The default accept duration is 356 days. You can change this in ``terms_conditions/terms_conditions_site_request_handler.py``
at line 47:

    accept_until = datetime.datetime.now(tz.tzutc()) + datetime.timedelta(days=365)

Addon integration
-----------------

This addon is integrated into the docker AM at 2 points.

Note that these change are already integrated into the branch that contains this README. You do not need to make any changes.
These changes are documented here to give some insight into how the terms and condition addon works.

First, the site is activated by 2 changes:
* Change the geni-tools code:
  * ``cd geni-tools``
  * ``git remote add TODO wvdemeer``
  * ``git fetch wvdemeer``
  * ``git checkout -b cust_req_hand_addon wvdemeer/cust_req_hand_addon``
* Add ``custom_request_handler_class`` to ``DockerAggregateManager`` in ``testbed.py``:
    
    
    ...
    
    # ADD THIS IMPORT:
    from terms_conditions.terms_conditions_site_request_handler import SecureXMLRPCAndTermsAndConditionsSiteRequestHandler

    class DockerAggregateManager(am3.ReferenceAggregateManager):
        # ADD THIS LINE:
        custom_request_handler_class = SecureXMLRPCAndTermsAndConditionsSiteRequestHandler
        
        def __init__(self, ...

Next, change the Allocate call, so it denies access to users that did not accept the terms:
    
    ...
    
    # ADD THIS IMPORT:
    from terms_conditions.terms_conditions_helper import TermsAndConditionsHelper
    
    ...
    
    def Allocate(self, slice_urn, credentials, rspec, options):
    
        ...
        
        # Grab the user_urn
        user_urn = gid.GID(string=options['geni_true_caller_cert']).get_urn()

        # ADD THIS CODE:
        if not TermsAndConditionsHelper.get().has_testbed_access(user_urn):
            self.logger.error("Cannot create sliver. No testbed access for user '%s'" % user_urn)
            return self.errorResult(am3.AM_API.REFUSED,
                                    '[T&C-APPROVAL-MISSING] '
                                    'Approval of the Terms & Conditions is required in order to use this testbed. '
                                    'Please visit '+self.public_url+'terms_conditions/index.html')

        ...
        
You can also add this code to other calls, such as ``Renew``
