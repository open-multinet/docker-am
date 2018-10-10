import datetime
from dateutil import tz

import dateutil   #requires:  pip install python-dateutil
import json

from terms_conditions import TermsAndConditionsDB

#Use: TermsAndConditionsHelper.get().has_testbed_access(user_urn)
class TermsAndConditionsHelper(object):
    _TC_HELPER = None

    @classmethod
    def get(cls):
        if cls._TC_HELPER is None:
            cls._TC_HELPER = TermsAndConditionsHelper()
        return cls._TC_HELPER

    def __init__(self):
        self._db = TermsAndConditionsDB()
        pass

    def get_user_accepts(self, user_urn):
        res = self._db.find_user_accepts(user_urn)
        if res is None:
            return { 'user_urn': user_urn, 'testbed_access': False }
        (until_str, accepts) = res
        until = dateutil.parser.parse(until_str)
        assert until.tzinfo is not None

        # Special case, if expired accepts are stored, ignore them
        now = datetime.datetime.now(tz.tzutc()) + datetime.timedelta(minutes=10)
        assert now.tzinfo is not None
        if until < now:
            return { 'user_urn': user_urn, 'testbed_access': False }

        user_accepts = {'user_urn': user_urn, 'until': until.isoformat() }
        user_accepts.update(accepts)
        return user_accepts

    def derive_testbed_access(self, user_accepts):
        safe_accepts = {}
        keys = ['accept_main', 'accept_userdata']
        for key in keys:
            safe_accepts[key] = bool(user_accepts[key]) if key in user_accepts else False
        return safe_accepts['accept_main'] and safe_accepts['accept_userdata']

    def has_testbed_access(self, user_urn):

        res = self._db.find_user_accepts(user_urn)
        if res is None:
            return False
        (until_str, accepts) = res
        until = dateutil.parser.parse(until_str)
        assert until.tzinfo is not None
        now = datetime.datetime.now(tz.tzutc()) + datetime.timedelta(minutes=10)
        assert now.tzinfo is not None
        if until < now:
            return False
        return self.derive_testbed_access(accepts)
