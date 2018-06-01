import datetime

import dateutil   #requires:  pip install python-dateutil
from dateutil import tz
import json
import pkg_resources

from gcf.geni.SecureThreadedXMLRPCServer import SecureThreadedXMLRPCRequestHandler
from gcf.geni.SecureXMLRPCServer import SecureXMLRPCRequestHandler

from terms_conditions.terms_conditions import TermsAndConditionsDB
from terms_conditions.terms_conditions_helper import TermsAndConditionsHelper


class TermsAndConditionsSite(TermsAndConditionsHelper):
    _TC_SITE = None

    @classmethod
    def get(cls):
        if cls._TC_SITE is None:
            cls._TC_SITE = TermsAndConditionsSite()
        return cls._TC_SITE

    def __init__(self):
        super(TermsAndConditionsSite, self).__init__()
        self._html = pkg_resources.resource_string(__name__, 'terms_conditions.html')
        self._js = pkg_resources.resource_string(__name__, 'terms_conditions.js')
        self._css = pkg_resources.resource_string(__name__, 'terms_conditions.css')

    def html(self):
        return self._html

    def js(self):
        return self._js

    def css(self):
        return self._css

    def register_accept(self, user_urn, user_accepts):
        safe_accepts = {}
        keys = ['accept_main', 'accept_userdata']
        for key in keys:
            safe_accepts[key] = bool(user_accepts[key]) if key in user_accepts else False

        safe_accepts['testbed_access'] = self.derive_testbed_access(safe_accepts)

        accept_until = datetime.datetime.now(tz.tzutc()) + datetime.timedelta(days=365)

        self._db.register_user_accepts(user_urn,
                                       safe_accepts,
                                       accept_until.isoformat())
                                       # datetime.datetime.now(datetime.timezone.utc).isoformat())
        return

    def register_decline(self, user_urn):
        self._db.delete_user_accepts(user_urn)
        return

    def get_user_accepts(self, user_urn):
        return super(TermsAndConditionsSite, self).get_user_accepts(user_urn)


class SecureXMLRPCAndTermsAndConditionsSiteRequestHandler(SecureThreadedXMLRPCRequestHandler):
    def find_client_urn(self):
        cert_dict = self.request.getpeercert()
        # self.log_message("findClientUrn in: %s", cert_dict)
        if cert_dict is None:
            return None
        if 'subjectAltName' in cert_dict:
            san = cert_dict['subjectAltName']
            for entry in san:
                (san_type, san_val) = entry
                if san_type == 'URI' and san_val.startswith('urn:publicid:IDN+'):
                    return san_val
        return None

    def read_request_data(self, max_bytes=None):
        #copied from SimpleXMLRPCServer do_POST
        max_chunk_size = 10 * 1024 * 1024
        size_remaining = int(self.headers["content-length"])

        if max_bytes is not None and size_remaining > max_bytes:
            self.send_error(400, "Client is sending too much data")
            self.send_header("Content-length", "0")
            self.end_headers()
            return None

        L = []
        while size_remaining:
            chunk_size = min(size_remaining, max_chunk_size)
            chunk = self.rfile.read(chunk_size)
            if not chunk:
                break
            L.append(chunk)
            size_remaining -= len(L[-1])

        if len(L) == 0:
            self.send_error(400, "Required data missing")
            self.send_header("Content-length", "0")
            self.end_headers()
            return None

        data = ''.join(L)
        return self.decode_request_content(data)

    def do_POST(self):
        """Handles the HTTP POST request.

        Most calls will be forwarded because they are XML-RPC calls, and get forwarded to the real method.
        """
        # we don't actually support any POST at the moment. If we did, we'd intercept it here, and do it instead of defering to XML-RPC

        #call super method
        # super(SecureXMLRPCRequestHandler, self).do_POST()  # new style
        SecureXMLRPCRequestHandler.do_POST(self)

    def do_DELETE(self):
        """Handles the HTTP DELETE request.
        """
        self.log_message("Got server DELETE call: %s", self.path)
        if self.path == '/terms_conditions' or self.path == '/terms_conditions/' or self.path == '/terms_conditions/accept':
            client_urn = self.find_client_urn()
            if client_urn is None:
                self.report_forbidden()
                return
            TermsAndConditionsSite.get().register_decline(client_urn)
            self.send_response(204) # No Content
            self.send_header("Content-length", "0")
            self.end_headers()
            # self.wfile.close()
            return

        self.send_error(405, "Method not allowed here")

    def do_PUT(self):
        """Handles the HTTP PUT request.
        """
        self.log_message("Got server PUT call: %s", self.path)
        if self.path == '/terms_conditions/accept':
            client_urn = self.find_client_urn()
            if client_urn is None:
                self.report_forbidden()
                return
            data = self.read_request_data(max_bytes=1000) #These are always very small JSON messages
            if data is None:
                # we assume read_request_data has set the right error
                return
            try:
                user_accepts = json.loads(data)
            except ValueError:
                self.send_error(400, "JSON parse exception")
                self.send_header("Content-length", "0")
                self.end_headers()
                return

            TermsAndConditionsSite.get().register_accept(client_urn, user_accepts)
            self.send_response(204) # No Content
            self.send_header("Content-length", "0")
            self.end_headers()
            # self.wfile.close()
            return

        self.send_error(405, "Method not allowed here")

    def do_GET(self):
        """Handles the HTTP GET request.

        GET calls are never XML-RPC calls, so we should return 404 if we don't handle them
        """
        self.log_message("Got server GET call: %s", self.path)
        if self.path == '/terms_conditions' or self.path == '/terms_conditions/':
            self.send_response(301)
            self.send_header("Location", "/terms_conditions/index.html")
            self.end_headers()
            return

        if self.path == '/terms_conditions/index.html':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            client_urn = self.find_client_urn()
            if client_urn is None:
                self.report_forbidden()
                return
            response = TermsAndConditionsSite.get().html()
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return

        if self.path == '/terms_conditions/terms_conditions.js':
            self.send_response(200)
            self.send_header("Content-type", "application/javascript")
            client_urn = self.find_client_urn()
            if client_urn is None:
                self.report_forbidden()
                return
            response = TermsAndConditionsSite.get().js()
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return

        if self.path == '/terms_conditions/terms_conditions.css':
            self.send_response(200)
            self.send_header("Content-type", "text/css")
            client_urn = self.find_client_urn()
            if client_urn is None:
                self.report_forbidden()
                return
            response = TermsAndConditionsSite.get().css()
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return

        if self.path == '/terms_conditions/accept':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            client_urn = self.find_client_urn()
            if client_urn is None:
                self.report_forbidden()
                return
            response = json.dumps(TermsAndConditionsSite.get().get_user_accepts(client_urn), indent=4)
            if response is None:
                self.report_404()
                return
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return

        self.report_404()

    def report_forbidden(self):
        self.send_response(403)
        response = 'Forbidden'
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)