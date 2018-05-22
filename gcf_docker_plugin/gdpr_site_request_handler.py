from gcf.geni.SecureXMLRPCServer import SecureXMLRPCRequestHandler


class SecureXMLRPCAndGDPRSiteServer(SecureXMLRPCRequestHandler):
    def find_client_urn(self):
        cert_dict = self.request.getpeercert()
        self.log_message("findClientUrn in: %s", cert_dict)
        if cert_dict is None:
            return None
        if 'subjectAltName' in cert_dict:
            san = cert_dict['subjectAltName']
            for entry in san:
                (san_type, san_val) = entry
                if san_type == 'URI' and san_val.startswith('urn:publicid:IDN+'):
                    return san_val
        return None

    def do_POST(self):
        """Handles the HTTP POST request.

        Most calls will be forwarded because they are XML-RPC calls, and get forwarded to the real method.
        """
        self.log_message("Got server POST call: %s", self.path)
        if self.path == '/test.html':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            response = '<html><body><h1>HTML POST Test Success</h1></body></html>'
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return

        #call super method
        # super(SecureXMLRPCRequestHandler, self).do_POST()  # new style
        SecureXMLRPCRequestHandler.do_POST(self)

    def do_GET(self):
        """Handles the HTTP GET request.

        GET calls are never XML-RPC calls, so we should return 404 if we don't handle them
        """
        self.log_message("Got server GET call: %s", self.path)
        if self.path == '/test.html':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            client_urn = self.find_client_urn()
            response = '<html>\n   <body>\n      <h1>HTML GET Test Success for client {}</h1>\n   </body>\n</html>\n'.format(client_urn)
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return

        self.report_404()
