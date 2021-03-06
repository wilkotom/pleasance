#!/usr/bin/env python


__author__ = 'twilkinson'

import json
import re
import base64
import web
import zlib
from time import strftime, localtime
from pleasanceMongoDB import PleasanceMongo
from pleasanceShelf import PleasanceShelf
from slime import Slime

urls = (
    '/dump/?', 'Dump',
    '/dump/(.*)$', 'DumpObject',
    '/package(s|info|export)/?', 'ShowAllPackages',
    r'/packages/([A-Za-z0-9\-_]*)/?$', 'PackageInstances',
    r'/packages/([A-Za-z0-9\-_]*)/(.*)/export/?$', 'PackageExportVersion',
    r'/packages/([A-Za-z0-9\-_]*)/(.*)', 'PackageInstanceVersions',
    r'/packageinfo/([A-Za-z0-9\-_]*)/?$', 'PackageInstancesInfo',
    r'/packageinfo/([A-Za-z0-9\-_]*)/(.*)', 'PackageVersionInfo',
    r'/packageexport/([A-Za-z0-9\-_]*)/?$', 'PackageInstancesInfo',
    r'/packageexport/([A-Za-z0-9\-_]*)/(.*)', 'PackageExportVersion',
    '/packageimport', 'PackageImportVersion',
    r'/promote/([A-Za-z0-9\-_]*)/(.*)', 'PackageVersionPromote',
    r'/unpromote/([A-Za-z0-9\-_]*)/(.*)', 'PackageVersionUnpromote',
    '/configuration/?$', 'Configuration',
    r'/configuration/([A-Za-z0-9\-_]*)$', 'ConfigurationServiceInstance',  # eg /configuration/eqc-pm-service-int
    r'/configuration/([A-Za-z0-9\-_]*)/history/?$', 'ConfigurationServiceInstanceHistory',
    r'/configuration/([A-Za-z0-9\-_]*)/history/(.*)$', 'ConfigurationServiceInstanceHistoricVersion',
    r'/configuration/([A-Za-z0-9\-_]*)/(.*)', 'ConfigurationServiceInstanceHosts',  # eg ...-int/cheiconeqc001-95
    '/bootstrap/?$', 'BootStrap',
    '/bootstrap/(.*)', 'BootstrapServer',  # /bootstrap/linux/eqc-pm-service-int/eqc-pm/1.0
    '/installer/?$', 'Installers',
    r'/installer/([A-Za-z0-9\-_]*)$', 'InstallerInstances',  # /installer/expediaApplicationFolder
    r'/installer/([A-Za-z0-9\-_]*)/(.*)', 'InstallerInstanceSpecific',  # /installer/expediaApplicationFolder/linux
    '/(.*)', 'PrintBadURL'
)

# Define the application
app = web.application(urls, globals())


###############################################################################
# If we get a request for an object we don't recognise, throw some debugging
# data back
###############################################################################

class PrintBadURL:
    @staticmethod
    def GET(uri):
        output = 'Calling URI:' + uri + '\n'
        for setting in web.ctx.env:
            output = output + setting + ' ' + str(web.ctx.env[setting]) + '\n'
        output = output + "Path: " + web.ctx.path + " Homepath: " + web.ctx.homepath + " Fullpath: " + web.ctx.fullpath
        return output


###############################################################################
# Dump Class. Throws whatever is in memory to the browser, for debugging ###
###############################################################################

class Dump:
    @staticmethod
    def GET():
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Objects</title></head><body>"
        for objectName in pleasance.configuration_objects():
            response += "<a href='" + web.ctx.home + "/dump/" + objectName + "'>" + objectName + "</a><br/>"
        response += "</body></html>"
        return response


class DumpObject:
    @staticmethod
    def GET(object_name):
        object_name = str(object_name)
        web.header('Content-Type', 'application/json')
        web.header('X-Object-Name', object_name)
        return pleasance.dump_configuration_object(object_name)


##############################################################################
# Configuration - Consists of global settings and per-server ones
##############################################################################

class Configuration:  # List available configurations (aka service instances)
    @staticmethod
    def GET():
        response = ''
        if 'HTTP_ACCEPT' in web.ctx.environ and web.ctx.environ['HTTP_ACCEPT'].startswith("application/json"):
            web.header('Content-Type', 'application/json')
            response = json.dumps(sorted(pleasance.list_objects("environments")))
        else:
            web.header('Content-Type', 'text/html')
            response = "<html><head><title>Available Applications</title></head><body>"
            for environmentName in sorted(pleasance.list_objects("environments")):
                response += "<a href='" + web.ctx.home + "/configuration/" + environmentName + "'>"
                response += environmentName + "</a><br/>"
            response += "</body></html>"
        return response


class ConfigurationServiceInstance:  # Get / Update / Delete global Configuration for a given service instance
    @staticmethod
    def GET(instance_name):
        try:
            web.header('Content-Type', 'application/json')
            return pleasance.retrieve_configuration(instance_name)
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()

    @staticmethod
    def PUT(instance_name):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        username = '' # We need to initialise these to empty values in the case that auth is disabled
        password = ''
        if auth is not None:
            try:
                auth = re.sub('^Basic ', '', auth)
                username, password = base64.decodestring(auth).split(':')
            except ValueError:
                return web.unauthorized()
        if not check_auth(username, password):
            return web.Unauthorized()
        try:
            if pleasance.update_configuration(instance_name, web.ctx.env.get('CONTENT_TYPE'), web.data(), username):
                return "Updated Environment " + instance_name
        except pleasance.ConfigurationNotJSONError:
            return web.webapi.UnsupportedMediaType()
        except pleasance.ConfigurationNotValidJSONError:
            return web.badrequest('Could not parse the JSON supplied')

    @staticmethod
    def DELETE(instance_name):
        return pleasance.delete_configuration(instance_name)


class ConfigurationServiceInstanceHosts:  # Get / Update / Delete individual server Configuration for a given instance

    @staticmethod
    def GET(instance_name, node_identifier):
        try:
            web.header('Content-Type', 'application/json')
            return pleasance.retrieve_node_configuration(instance_name, node_identifier)
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()

    @staticmethod
    def PUT(instance_name, node_identifier):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        username = '' # We need to initialise these to empty values in the case that auth is disabled
        password = ''
        if auth is not None:
            auth = re.sub('^Basic ', '', auth)
            username, password = base64.decodestring(auth).split(':')
        if not check_auth(username,password):
            return web.Unauthorized()
        try:
            if pleasance.create_node_configuration(instance_name, node_identifier, web.ctx.env.get('CONTENT_TYPE'),
                                                   web.data()):
                return "Updated node Configuration for " + node_identifier + " in " + instance_name
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()
        except pleasance.ConfigurationNotValidJSONError:
            return web.badrequest('Could not parse the JSON supplied')

    @staticmethod
    def DELETE(instance_name, node_identifier):
        try:
            if pleasance.delete_node_configuration(instance_name, node_identifier):
                return "Deleted " + node_identifier + " from " + instance_name
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()


class ConfigurationServiceInstanceHistory:

    @staticmethod
    def GET(instance_name):
        response = ''
        instance_history = pleasance.service_instance_configuration_history(instance_name)
        if 'HTTP_ACCEPT' in web.ctx.environ and web.ctx.environ['HTTP_ACCEPT'].startswith("application/json"):
            response = json.dumps(instance_history, sort_keys=True, indent=2, separators=(',', ': '))
        else:
            web.header('Content-Type', 'text/html')
            response = '<html><head><title>Available Applications</title></head><body>'
            response += '<h1>Version history for ' + instance_name + '</h1>'
            response += '<table><tr><th>Snapshot Time</th><th>Replaced By</th></tr>'
            for version in instance_history:
                readable_time = strftime('%Y-%m-%d %H:%M:%S', localtime(version['datestamp']))
                response += '<tr><td><a href="' + web.ctx.home + '/configuration/' + instance_name + '/history/' + \
                            str(version['datestamp']) + '">' + readable_time + '</a> </td><td>' + \
                            version['username'] + '</td></tr>'
            response += "</table></body></html>"
        return response


class ConfigurationServiceInstanceHistoricVersion:

    @staticmethod
    def GET(instance_name, version):
        try:
            web.header('Content-Type', 'application/json')
            historic_version = pleasance.service_instance_historic_version(instance_name, version)['content']
            del historic_version['_id']
            return json.dumps(historic_version['globalConfiguration'], sort_keys=True, indent=2, separators=(',', ': '))
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()

    @staticmethod
    def PUT(instance_name, version):
        return web.nomethod()

    @staticmethod
    def DELETE(instance_name, version):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        username = ''  # We need to initialise these to empty values in the case that auth is disabled
        password = ''
        if auth is not None:
            try:
                auth = re.sub('^Basic ', '', auth)
                username, password = base64.decodestring(auth).split(':')
            except ValueError:
                return web.unauthorized()
        if not check_auth(username, password):
            return web.unauthorized()
        try:
            pleasance.delete_historic_version(instance_name, version)
            return 'Configuration ' + version + ' for ' + instance_name + ' deleted'
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()


################################################################################
# Packages: Store different versions of a deployment package
################################################################################

class ShowAllPackages:
    @staticmethod
    def GET(path_identifier):  # List available packages
        response = ''
        if 'HTTP_ACCEPT' in web.ctx.environ and web.ctx.environ['HTTP_ACCEPT'].startswith("application/json"):
            web.header('Content-Type', 'application/json')
            response = json.dumps(sorted(pleasance.list_objects("packages")))
        else:
            web.header('Content-Type', 'text/html')
            response = "<html><head><title>Available Applications</title></head><body>"
            for packageName in sorted(pleasance.list_objects("packages")):
                response += "<a href='" + web.ctx.home + "/package" + path_identifier + \
                            "/" + packageName + "'>" + packageName + "</a><br/>"
            response += "</body></html>"
        return response


class PackageInstances:  # create / delete new package, list available package versions
    @staticmethod
    def GET(package_name):
        if package_name in pleasance.list_objects("packages"):
            if 'HTTP_ACCEPT' in web.ctx.environ and web.ctx.environ['HTTP_ACCEPT'].startswith("application/json"):
                web.header('Content-Type', 'application/json')
                response = json.dumps(pleasance.list_package_versions(package_name))
            else:
                web.header('Content-Type', 'text/html')
                response = "<html><head><title>Available Application Versions</title></head><body>"
                for packageVersion in sorted(pleasance.list_package_versions(package_name)):
                    response += "<a href='" + web.ctx.home + "/packages/" + package_name + "/" \
                                + packageVersion + "'>" + packageVersion + "</a><br/>"
                response += "</body></html>"
            return response
        else:
            return web.notfound("Application does not exist")

    @staticmethod
    def PUT(package_name):
        try:
            if pleasance.create_package(package_name):
                return "Created package " + package_name
            else:
                return web.internalerror()
        except pleasance.PackageIsPromotedError:
            return web.forbidden()

    @staticmethod
    def DELETE( package_name):
        try:
            if pleasance.delete_package(package_name):
                return "Deleted package " + package_name
            else:
                return web.badrequest()
        except pleasance.PackageNotFoundError:
            return "Package does not exist - no action taken"


class PackageInstancesInfo:
    @staticmethod
    def GET(package_name):
        if package_name in pleasance.list_objects("packages"):
            package_versions_details = {}
            for package_version in sorted(pleasance.list_package_versions(package_name)):
                package_versions_details[package_version] = json.loads(
                    pleasance.retrieve_package_details(package_name, package_version))
            if 'HTTP_ACCEPT' in web.ctx.environ and web.ctx.environ['HTTP_ACCEPT'].startswith("application/json"):
                web.header('Content-Type', 'application/json')
                response = json.dumps(package_versions_details, sort_keys=True, indent=2, separators=(',', ': '))
            else:
                web.header('Content-Type', 'text/html')
                response = "<html><head><title>Available Application Versions</title></head><body>"
                response += "<table border=1><th>Package</th><th>Version</th><th>Timestamp</th><th>Promoted</th></tr>"
                for package_version in sorted(package_versions_details.keys()):
                    response += '<tr><td>' + package_name + '</td><td>' + \
                                '<a href="' + web.ctx.home + '/packageinfo/' + package_name + '/' + \
                                package_version + '">' + package_version + '</a></td><td>' + \
                                strftime('%Y-%m-%d %H:%M:%S',
                                         localtime(package_versions_details[package_version]["created"])) + \
                                "</td><td>"
                    if "promoted" in package_versions_details[package_version] and \
                            package_versions_details[package_version]["promoted"] is True:
                        response += "<font color='red'>True</font></td></tr>"
                    else:
                        response += "False</td></tr>"
                response += "</table></body></html>"
            return response
        else:
            return web.notfound("Application does not exist")

    @staticmethod
    def PUT(_):
        return web.nomethod()

    @staticmethod
    def DELETE(_):
        return web.nomethod


class PackageVersionPromote:  # Flag a package so that it shouldn't be cleaned up automatically
    def GET(self, package_name, package_version):  # Not RESTful. Still here for historical reasons.
        return self.promote_package_version(package_name, package_version)

    def POST(self, package_name, package_version):
        return self.promote_package_version(package_name, package_version)

    @staticmethod
    def promote_package_version(package_name, package_version):
        try:
            if pleasance.set_promotion_flag(package_name, package_version, True):
                return "Promoted " + package_name + " version " + package_version
        except pleasance.PackageNotFoundError:
            return web.notfound()
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


class PackageVersionUnpromote:  # Flag a package for automatic deletion
    def GET(self, package_name, package_version):
        return self.unpromote_package_version(package_name, package_version)

    def POST(self, package_name, package_version):
        return self.unpromote_package_version(package_name, package_version)

    @staticmethod
    def unpromote_package_version(package_name, package_version):
        try:
            if pleasance.set_promotion_flag(package_name, package_version, False):
                return "Unpromoted " + package_name + " version " + package_version
        except pleasance.PackageNotFoundError:
            return web.notfound()
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


class PackageInstanceVersions:  # Create / Update / Delete given version of a package
    @staticmethod
    def GET(package_name, package_version):
        try:
            (content_type, package_contents) = pleasance.retrieve_package_version(package_name, package_version)
            web.header('Content-Type', content_type)
            web.header('Content-Length', len(package_contents))
            return package_contents
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()
        except pleasance.CannotUpdatePackageError:
            return web.internalerror()

    @staticmethod
    def PUT(package_name, package_version):
        content_type = ''
        if web.ctx.env.get('CONTENT_TYPE'):
            content_type = web.ctx.env.get('CONTENT_TYPE')
        try:
            return pleasance.update_package_version(package_name, package_version, content_type, web.data())
        except pleasance.PackageNotFoundError:
            return web.notfound()

    @staticmethod
    def DELETE(package_name, package_version):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        username = ''  # We need to initialise these to empty values in the case that auth is disabled
        password = ''
        try:
            if auth is not None:
                auth = re.sub('^Basic ', '', auth)
                username, password = base64.decodestring(auth).split(':')
        except ValueError:
            return web.Unauthorized()
        if not check_auth(username, password):
            return web.Unauthorized()
        try:
            if pleasance.delete_package_version(package_name, package_version):
                return package_name + " version " + package_version + " has been deleted.\n"
            else:
                return web.forbidden()
        except pleasance.PackageNotFoundError:
            return web.notfound()


class PackageVersionInfo:
    @staticmethod
    def GET(package_name, package_version):
        try:
            package_details = pleasance.retrieve_package_details(package_name, package_version)
            web.header('Content-Type', 'application/json')
            return package_details
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


class PackageExportVersion:
    @staticmethod
    def GET(package_name, package_version):
        try:
            package_details = pleasance.retrieve_package_details(package_name, package_version)
            (content_type, package_contents) = pleasance.retrieve_package_version(package_name, package_version)
            export_package = {'metadata': package_details, 'content-type': content_type,
                              'contents': base64.b64encode(package_contents), 'name': package_name,
                              'version': package_version}
            web.header('Content-Type', 'application/pleasance-package')
            web.header('Content-Disposition', 'attachment; filename=' + package_name + '.' + package_version + '.pnc')
            response = zlib.compress(json.dumps(export_package))
            web.header('Content-Length', len(response))
            return response
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


class PackageImportVersion:
    @staticmethod
    def POST():
        try:
            package_object = json.loads(zlib.decompress(web.data()))
            if not pleasance.create_package(package_object['name']):
                return web.internalerror()
            if not pleasance.update_package_version(package_object['name'], package_object['version'],
                                                    package_object['content-type'],
                                                    base64.b64decode(package_object['contents'])):
                return web.internalerror()
            else:
                pleasance.update_package_metadata(package_object['name'], package_object['version'],
                                                  json.loads(package_object['metadata']))
                web.header('Location',
                           web.ctx.home + '/packages/' + package_object['name'] + '/' + package_object['version'])
                return web.created()
        except pleasance.PackageIsPromotedError:
            return web.HTTPError(status='309 Conflict', headers={'Content-Type': 'text/plain'},
                                 data='Cannot overwrite a promoted package')
        except (zlib.error, ValueError):
            return web.UnsupportedMediaType()


################################################################################
# Bootstrap: Returns the bootstrap script
################################################################################

# The bootstrap script fetches the installation script plus Configuration for it.
# It doesn't install the application directly. Why? The installation executable
# could be written in anything (java, shell, chef, puppet...). The bootstrap's
# job is to invoke that correctly rather than install anything itself.
# Valid osNames are likely to be windows (Powershell) and linux (bash)
#
# Example URL: # /bootstrap/linux/eqc-pm-service-int/eqc-pm/1.0

class BootStrap:
    @staticmethod
    def GET():
        response = ''
        if 'HTTP_ACCEPT' in web.ctx.environ and web.ctx.environ['HTTP_ACCEPT'].startswith("application/json"):
            web.header('Content-Type', 'application/json')
            response = json.dumps(sorted(pleasance.list_objects("bootstraps")))
        else:
            web.header('Content-Type', 'text/html')
            response = "<html><head><title>Available Bootstraps</title></head><body>"
            for osName in sorted(pleasance.list_objects("bootstraps")):
                response += "<a href='" + web.ctx.home + "/bootstrap/" + osName + "'>" + osName + "</a><br/>"
            response += "</body></html>"
        return response


class BootstrapServer:
    @staticmethod
    def GET(context):
        if context.lstrip('/').split('/').__len__() == 4:
            (platform, environment, application, application_version) = context.lstrip('/').split('/', 4)
            configuration_url = web.ctx.home + "/configuration/" + environment
            package_url = web.ctx.home + "/packages/" + application + "/" + application_version
            try:
                installer_url = web.ctx.home + "/installer/" + pleasance.get_installer_type(
                    environment) + "/" + platform
                (bootstrap, content_type) = pleasance.retrieve_bootstrap(platform)
            except pleasance.EnvironmentNotFoundError:
                return web.notfound()
            except pleasance.BootStrapNotFoundError:
                return web.notfound()
            bootstrap = bootstrap.replace("{{packageURL}}", package_url)
            bootstrap = bootstrap.replace("{{environmentConfiguration}}", configuration_url)
            bootstrap = bootstrap.replace("{{installerPath}}", installer_url)
            bootstrap = bootstrap.replace("{{packageVersion}}", application_version)
            bootstrap = bootstrap.replace("{{packageName}}", application)
        else:
            try:
                (bootstrap, content_type) = pleasance.retrieve_bootstrap(context)
            except pleasance.BootStrapNotFoundError:
                return web.notfound()
        web.header('Content-Type', content_type)
        return bootstrap

    @staticmethod
    def PUT(context):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        username = ''  # We need to initialise these to empty values in the case that auth is disabled
        password = ''
        if auth is not None:
            try:
                auth = re.sub('^Basic ', '', auth)
                username, password = base64.decodestring(auth).split(':')
            except ValueError:
                return web.unauthorized()
        if not check_auth(username, password):
            return web.unauthorized()
        if context.lstrip('/').split('/').__len__() > 1:
            return web.badrequest(context + " " + str(context.lstrip('/').split('/')) + " greater than 1")
        else:
            content_type = ""
            if web.ctx.env.get('CONTENT_TYPE'):
                content_type = web.ctx.env.get('CONTENT_TYPE')
            if pleasance.store_bootstrap(context, content_type, web.data()):
                return "Created bootstrap " + context
            raise Exception

    @staticmethod
    def DELETE(context):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        username = ''  # We need to initialise these to empty values in the case that auth is disabled
        password = ''
        if auth is not None:
            try:
                auth = re.sub('^Basic ', '', auth)
                username, password = base64.decodestring(auth).split(':')
            except ValueError:
                return web.Unauthorized()
        if not check_auth(username, password):
            return web.Unauthorized()
        if context.lstrip('/').split('/').__len__() > 1:
            return web.badrequest(context + " " + str(context.lstrip('/').split('/')) + " greater than 1")
        else:
            try:
                if pleasance.delete_bootstrap(context):
                    return "Deleted Bootstrap " + context
            except pleasance.BootStrapNotFoundError:
                return web.notfound()

################################################################################
# Installers: container-specific installers go here
################################################################################

class Installers:
    @staticmethod
    def GET():
        response = ''
        if 'HTTP_ACCEPT' in web.ctx.environ and web.ctx.environ['HTTP_ACCEPT'].startswith("application/json"):
            web.header('Content-Type', 'application/json')
            response = json.dumps(sorted(pleasance.list_objects("installers")))
        else:
            web.header('Content-Type', 'text/html')
            response = "<html><head><title>Available Installers</title></head><body>"
            for installer_name in sorted(pleasance.list_objects("installers")):
                response += "<a href='" + web.ctx.home + "/installer/" + installer_name + "'>" + \
                            installer_name + "</a><br/>"
            response += "</body></html>"
        return response


class InstallerInstances:
    @staticmethod
    def GET(installer_name):
        try:
            response = ''
            if 'HTTP_ACCEPT' in web.ctx.environ and web.ctx.environ['HTTP_ACCEPT'].startswith("application/json"):
                web.header('Content-Type', 'application/json')
                response = json.dumps(sorted(pleasance.list_installer_instances(installer_name)))
            else:
                web.header('Content-Type', 'text/html')
                response = "<html><head><title>Available Installers</title></head><body>"
                for platformName in sorted(pleasance.list_installer_instances(installer_name)):
                    response += "<a href='" + web.ctx.home + "/installer/" + installer_name + "/" + platformName + "'>" + \
                                platformName + "</a><br/>"
                response += "</body></html>"
            return response
        except pleasance.InstallerNotFoundError:
            return web.notfound()
    @staticmethod
    def PUT(installer_name):
        if pleasance.create_installer(installer_name):
            return "Created installer " + installer_name


class InstallerInstanceSpecific:
    @staticmethod
    def GET(installer_name, target_os):
        try:
            (content_type, installer_data) = pleasance.retrieve_installer_instance(installer_name, target_os)
            web.header('Content-Type', content_type)
            return installer_data
        except pleasance.InstallerInstanceNotFoundError:
            return web.notfound()

    @staticmethod
    def PUT(installer_name, target_os):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        username = ''  # We need to initialise these to empty values in the case that auth is disabled
        password = ''
        try:
            if auth is not None:
                auth = re.sub('^Basic ', '', auth)
                username, password = base64.decodestring(auth).split(':')
        except ValueError:
            return web.unauthorized()
        if not check_auth(username, password):
            return web.unauthorized()
        content_type = ''
        if web.ctx.env.get('CONTENT_TYPE'):
            content_type = web.ctx.env.get('CONTENT_TYPE')
        try:
            if pleasance.update_installer_specific(installer_name, target_os, content_type, web.data()):
                return "Created Installer for " + installer_name + " on platform: " + target_os
        except pleasance.InstallerNotFoundError:
            return web.notfound()

    @staticmethod
    def DELETE(installer_name, target_os):
        try:
            if pleasance.delete_installer_specific(installer_name, target_os):
                return "Deleted Installer for " + installer_name + " on platform: " + target_os
        except pleasance.InstallerNotFoundError:
            return web.notfound()


def check_auth(username, password):
    if configuration["auth_type"] == 'LDAP':
        if username is not '' and password is not '':
            try:
                slime_session.login(username, password)
                return True
            except Slime.LDAPBindFailed:
                return False
        else:
            return False
    elif configuration["auth_type"] == 'disabled':
        return True
    else:
        return False


################################################################################
# Startup Here
################################################################################

with open('./pleasance.json') as configuration_file:
    configuration = json.load(configuration_file)

if configuration["auth_type"] == "LDAP":
    slime_session = Slime(configuration["auth_options"]["ldap_url"],
                          configuration["auth_options"]["ldap_bind_dn_pattern"])

if configuration["storage_type"] == 'MongoDB':
    pleasance = PleasanceMongo(configuration["storage_options"]["hostname"],
                               configuration["storage_options"]["port"])

elif configuration["storage_type"] == 'shelve':
    pleasance = PleasanceShelf(configuration["storage_options"]["package_path"],
                               configuration["storage_options"]["configuration_path"])
else:
    raise Exception

if __name__ == "__main__":
    app.run()
