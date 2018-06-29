import ldap


class Slime:
    def __init__(self, ldap_url, ldap_bind_dn):
        self.ldap_url = ldap_url
        self.ldap_connection = ldap.initialize(ldap_url)
        self.ldap_connection.protocol_version = 3
        self.ldap_bind_dn = ldap_bind_dn

    def __str__(self):
        return "SLIMe connection to {0}".format(self.ldap_url)

    def login(self, username, password):
        username = self.ldap_bind_dn.replace('{{username}}', username)
        try:
            self.__login(username, password)
        except ldap.SERVER_DOWN:
            # If we get SERVER_DOWN, session may have closed. Attempt to re-connect to the server
            # and try the login again
            self.ldap_connection.delete()
            self.__init__(self.ldap_url, self.ldap_bind_dn)
            self.__login(username, password)

    def __login(self, username, password):
        try:
            self.ldap_connection.simple_bind_s(username, password)
        except ldap.INVALID_CREDENTIALS:
            raise self.LDAPBindFailed

    class LDAPBindFailed(Exception):
        """Could not bind using LDAP credentials"""
        pass
