"""Thin XML-RPC client. Tests seed their data here, then assert in the browser."""
import xmlrpc.client


class OdooRPC:
    def __init__(self, url, db, user, password):
        self.url, self.db, self.user, self.password = url, db, user, password
        self.uid = None
        self._models = None

    def authenticate(self):
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise RuntimeError(f"Odoo rejected the QA credentials on {self.url}")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return self.uid

    def call(self, model, method, *args, **kwargs):
        return self._models.execute_kw(
            self.db, self.uid, self.password, model, method, list(args), kwargs)

    def create(self, model, values):
        return self.call(model, "create", values)

    def search_read(self, model, domain, fields=None, limit=80):
        return self.call(model, "search_read", domain, fields=fields or [], limit=limit)

    def unlink(self, model, ids):
        return self.call(model, "unlink", ids)

    def version(self):
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common").version()
