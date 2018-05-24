import datetime

import dateutil   #requires:  pip install python-dateutil
import json

from gdpr.gdpr_db import GdprDB

#Use: GdprHelper.get().has_testbed_access(user_urn)
class GdprHelper(object):
    _GDPR_HELPER = None

    @classmethod
    def get(cls):
        if cls._GDPR_HELPER is None:
            cls._GDPR_HELPER = GdprHelper()
        return cls._GDPR_HELPER

    def __init__(self):
        self._db = GdprDB()
        pass

    def get_user_accepts(self, user_urn):
        res = self._db.find_user_accepts(user_urn)
        if res is None:
            return None
        (until_str, accepts) = res
        until = dateutil.parser.parse(until_str)
        assert until.tzinfo is not None
        user_accepts = {'user': user_urn, 'until': until}
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
        now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
        if until < now:
            return False
        return self.derive_testbed_access(accepts)
