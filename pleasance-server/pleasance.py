#!/usr/bin/env python


__author__ = 'twilkinson'

import web
from pleasanceShelf import PleasanceShelf
from PleasanceMongoDB import PleasanceMongo



urls = (
    '/dump', 'Dump',
    '/dump/(.*)$', 'DumpObject',
    '/package(s|info)', 'ShowAllPackages',
    '/package(s|info)/([A-Za-z0-9\-_]*)$', 'PackageInstances',
    '/packages/([A-Za-z0-9\-_]*)/(.*)', 'PackageInstanceVersions',
    '/packageinfo/([A-Za-z0-9\-_]*)/(.*)', 'PackageVersionInfo',
    '/promote/([A-Za-z0-9\-_]*)/(.*)', 'PackageVersionPromote',
    '/unpromote/([A-Za-z0-9\-_]*)/(.*)', 'PackageVersionUnpromote',
    '/configuration', 'Configuration',
    '/configuration/([A-Za-z0-9\-_]*)$', 'ConfigurationServiceInstance',  # eg /configuration/eqc-pm-service-int
    '/configuration/([A-Za-z0-9\-_]*)/(.*)', 'ConfigurationServiceInstanceHosts',  # eg ...-int/cheiconeqc001-95
    '/bootstrap', 'BootStrap',
    '/bootstrap/(.*)', 'BootstrapServer',  # /bootstrap/linux/eqc-pm-service-int/eqc-pm/1.0
    '/installer', 'Installers',
    '/installer/([A-Za-z0-9\-_]*)$', 'InstallerInstances',  # /installer/expediaApplicationFolder
    '/installer/([A-Za-z0-9\-_]*)/(.*)', 'InstallerInstanceSpecific',  # /installer/expediaApplicationFolder/linux
    '/(.*)', 'PrintBadURL'
)

# Define the application
app = web.application(urls, globals())


###############################################################################
# If we get a request for an object we don't recognise, throw some debugging
# data back
###############################################################################

class PrintBadURL:
    def GET(self, uri):
        output = 'Calling URI:' + uri + '\n'
        for setting in web.ctx.env:
            output = output + setting + ' ' + str(web.ctx.env[setting]) + '\n'
        output = output + "Path: " + web.ctx.path + " Homepath: " + web.ctx.homepath + " Fullpath: " + web.ctx.fullpath
        return output


###############################################################################
#  Dump Class. Throws whatever is in memory to the browser, for debugging ###
###############################################################################

class Dump:
    def GET(self):
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Objects</title></head><body>"
        for objectName in pleasance.configuration_objects():
            response += "<a href='" + web.ctx.home + "/dump/" + objectName + "'>" + objectName + "</a><br/>"
        response += "</body></html>"
        return response


class DumpObject:
    def GET(self, object_name):
        object_name = str(object_name)
        web.header('Content-Type', 'application/json')
        web.header('X-Object-Name', object_name)
        return pleasance.dump_configuration_object(object_name)


##############################################################################
# Configuration - Consists of global settings and per-server ones
##############################################################################

class Configuration:  # List available configurations (aka service instances)
    def GET(self):
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Applications</title></head><body>"
        for environmentName in sorted(pleasance.list_objects("environments")):
            response += "<a href='" + web.ctx.home + "/configuration/" + environmentName + "'>"
            response += environmentName + "</a><br/>"
        response += "</body></html>"
        return response


class ConfigurationServiceInstance:  # Get / Update / Delete global Configuration for a given service instance
    def GET(self, instance_name):
        try:
            web.header('Content-Type', 'application/json')
            return pleasance.retrieve_configuration(instance_name)
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()

    def PUT(self, instance_name):
        try:
            if pleasance.update_configuration(instance_name, web.ctx.env.get('CONTENT_TYPE'), web.data()):
                return "Updated Environment " + instance_name
        except pleasance.ConfigurationNotJSONError:
            return web.webapi.UnsupportedMediaType()
        except pleasance.ConfigurationNotValidJSONError:
            return web.badrequest('Could not parse the JSON supplied')

    def DELETE(self, instance_name):
        return pleasance.delete_configuration(instance_name)


class ConfigurationServiceInstanceHosts:  # Get / Update / Delete individual server Configuration for a given instance
    def GET(self, instance_name, node_identifier):
        try:
            web.header('Content-Type', 'application/json')
            return pleasance.retrieve_node_configuration(instance_name, node_identifier)
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()

    def PUT(self, instance_name, node_identifier):
        try:
            if pleasance.create_node_configuration(instance_name, node_identifier, web.ctx.env.get('CONTENT_TYPE'),
                                                   web.data()):
                return "Updated node Configuration for " + node_identifier + " in " + instance_name
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()
        except pleasance.ConfigurationNotValidJSONError:
            return web.badrequest('Could not parse the JSON supplied')

    def DELETE(self, instance_name, node_identifier):
        try:
            if pleasance.delete_node_configuration(instance_name, node_identifier):
                return "Deleted " + node_identifier + " from " + instance_name
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()


################################################################################
# Packages: Store different versions of a deployment package
################################################################################

class ShowAllPackages:
    def GET(self, path_identifier):  # List available packages
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Applications</title></head><body>"
        for packageName in sorted(pleasance.list_objects("packages")):
            response += "<a href='" + web.ctx.home + "/package" + path_identifier + \
                        "/" + packageName + "'>" + packageName + "</a><br/>"
        response += "</body></html>"
        return response


class PackageInstances:  # create / delete new package, list available package versions
    def GET(self, path_identifier, package_name):
        if package_name in pleasance.list_objects("packages"):
            web.header('Content-Type', 'text/html')
            response = "<html><head><title>Available Application Versions</title></head><body>"
            for packageVersion in sorted(pleasance.list_package_versions(package_name)):
                response += "<a href='" + web.ctx.home + "/package" + path_identifier + "/" + package_name + "/" \
                            + packageVersion + "'>" + packageVersion + "</a><br/>"
            response += "</body></html>"
            return response
        else:
            return web.notfound("Application does not exist")

    def PUT(self, path_identifier, package_name):
        if path_identifier == 'info':
            # Can't modify objects in the /packageinfo path
            return web.nomethod()
        if pleasance.create_package(package_name):
            return "Created package " + package_name
        else:
            return web.internalerror()

    def DELETE(self, path_identifier, package_name):
        if path_identifier == 'info':
            # Can't modify objects in the /packageinfo path
            return web.nomethod()
        try:
            if pleasance.delete_package(package_name):
                return "Deleted package " + package_name
            else:
                return web.badrequest()
        except pleasance.PackageNotFoundError:
            return "Package does not exist - no action taken"


class PackageVersionPromote:  # Flag a package so that it shouldn't be cleaned up automatically
    def GET(self, package_name, package_version):
        try:
            if pleasance.promote_package_version(package_name, package_version, True):
                return "Promoted " + package_name + " version " + package_version
        except pleasance.PackageNotFoundError:
            return web.notfound()
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


class PackageVersionUnpromote:  # Flag a package for automatic deletion
    def GET(self, package_name, package_version):
        try:
            if pleasance.promote_package_version(package_name, package_version, False):
                return "Unpromoted " + package_name + " version " + package_version
        except pleasance.PackageNotFoundError:
            return web.notfound()
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


class PackageInstanceVersions:  # Create / Update / Delete given version of a package
    def GET(self, package_name, package_version):
        try:
            (content_type, package_contents) = pleasance.retrieve_package_version(package_name, package_version)
            web.header('Content-Type', content_type)
            web.header('Content-Length', len(package_contents))
            return package_contents
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()
        except pleasance.CannotUpdatePackageError:
            return web.internalerror()

    def PUT(self, package_name, package_version):
        content_type = ''
        if web.ctx.env.get('CONTENT_TYPE'):
            content_type = web.ctx.env.get('CONTENT_TYPE')
        try:
            return pleasance.update_package_version(package_name, package_version, content_type, web.data())
        except pleasance.PackageNotFoundError:
            return web.notfound()

    def DELETE(self, package_name, package_version):
        try:
            if pleasance.delete_package_version(package_name, package_version):
                return package_name + " version " + package_version + " has been deleted.\n"
            else:
                return web.forbidden()
        except pleasance.PackageNotFoundError:
            return web.notfound()

class PackageVersionInfo:
    def GET(self, package_name, package_version):
        try:
            package_details = pleasance.retrieve_package_details(package_name, package_version)
            web.header('Content-Type', 'application/json')
            return package_details
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


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
    def GET(self):
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Bootstraps</title></head><body>"
        for osName in sorted(pleasance.list_objects("bootstraps")):
            response += "<a href='" + web.ctx.home + "/bootstrap/" + osName + "'>" + osName + "</a><br/>"
        response += "</body></html>"
        return response


class BootstrapServer:
    def GET(self, context):
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

    def PUT(self, context):
        if context.lstrip('/').split('/').__len__() > 1:
            return web.badrequest(context + " " + str(context.lstrip('/').split('/')) + " greater than 1")
        else:
            content_type = ""
            if web.ctx.env.get('CONTENT_TYPE'):
                content_type = web.ctx.env.get('CONTENT_TYPE')
            if pleasance.store_bootstrap(context, content_type, web.data()):
                return "Created bootstrap " + context
            raise Exception

    def DELETE(self, context):
        if context.lstrip('/').split('/').__len__() > 1:
            return web.badrequest(context + " " + str(context.lstrip('/').split('/')) + " greater than 1")
        else:
            if pleasance.delete_bootstrap(context):
                return "Deleted Bootstrap " + context


################################################################################
# Installers: container-specific installers go here
################################################################################

class Installers:
    def GET(self):
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Installers</title></head><body>"
        for installer_name in sorted(pleasance.list_objects("installers")):
            response += "<a href='" + web.ctx.home + "/installer/" + installer_name + "'>" + installer_name + "</a><br/>"
        response += "</body></html>"
        return response


class InstallerInstances:
    def GET(self, installer_name):
        try:
            web.header('Content-Type', 'text/html')
            response = "<html><head><title>Available Installers</title></head><body>"
            for platformName in sorted(pleasance.list_installer_instances(installer_name)):
                response += "<a href='" + web.ctx.home + "/installer/" + installer_name + "/" + platformName + "'>" + \
                            platformName + "</a><br/>"
            response += "</body></html>"
            return response
        except pleasance.InstallerNotFoundError:
            return web.notfound()

    def PUT(self, installer_name):
        if pleasance.create_installer(installer_name):
            return "Created installer " + installer_name


class InstallerInstanceSpecific:
    def GET(self, installer_name, target_os):
        try:
            (content_type, installer_data) = pleasance.retrieve_installer_instance(installer_name, target_os)
            web.header('Content-Type', content_type)
            return installer_data
        except pleasance.InstallerInstanceNotFoundError:
            return web.notfound()

    def PUT(self, installer_name, target_os):
        content_type = ''
        if web.ctx.env.get('CONTENT_TYPE'):
            content_type = web.ctx.env.get('CONTENT_TYPE')
        try:
            if pleasance.update_installer_specific(installer_name, target_os, content_type, web.data()):
                return "Created Installer for " + installer_name + " on platform: " + target_os
        except pleasance.InstallerNotFoundError:
            return web.notfound()

    def DELETE(self, installer_name, target_os):
        try:
            if pleasance.delete_installer_specific(installer_name, target_os):
                return "Deleted Installer for " + installer_name + " on platform: " + target_os
        except pleasance.InstallerNotFoundError:
            return web.notfound()

################################################################################
# Startup Here
################################################################################

############ Settings here  ###################

#package_repository_location = "./packages"
#configuration_repository_location = "./Configuration"
#pleasance = PleasanceShelf(package_repository_location, configuration_repository_location)
pleasance = PleasanceMongo('chsxplsnce001.idx.expedmz.com',27017)


############### End Settings ##################

if __name__ == "__main__":
    app.run()
