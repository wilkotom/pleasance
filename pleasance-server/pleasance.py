#!/usr/bin/env python


__author__ = 'twilkinson'

import web
from pleasanceShelf import PleasanceShelf


urls = (
    '/dump', 'dump',
    '/dump/(.*)$', 'dumpObject',
    '/packages', 'ShowAllPackages',
    '/packages/([A-Za-z0-9\-_]*)$', 'packageInstances',
    '/packages/([A-Za-z0-9\-_]*)/(.*)', 'packageInstanceVersions',
    '/promote/([A-Za-z0-9\-_]*)/(.*)', 'packageVersionPromote',
    '/unpromote/([A-Za-z0-9\-_]*)/(.*)', 'packageVersionUnpromote',
    '/configuration', 'configuration',
    '/configuration/([A-Za-z0-9\-_]*)$', 'configurationServiceInstance',  # eg /configuration/eqc-pm-service-int
    '/configuration/([A-Za-z0-9\-_]*)/(.*)', 'configurationServiceInstanceHosts',  # eg ...-int/cheiconeqc001-95
    '/bootstrap', 'bootstrap',
    '/bootstrap/(.*)', 'bootstrapServer',  # /bootstrap/linux/eqc-pm-service-int/eqc-pm/1.0
    '/installer', 'installers',
    '/installer/([A-Za-z0-9\-_]*)$', 'installerInstances',  # /installer/expediaApplicationFolder
    '/installer/([A-Za-z0-9\-_]*)/(.*)', 'installerInstanceSpecific'  # /installer/expediaApplicationFolder/linux
)

# Define the application
app = web.application(urls, globals())

###############################################################################
###  Dump Class. Throws whatever is in memory to the browser, for debugging ###
###############################################################################


class dump:
    def GET(self):
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Objects</title></head><body>"
        for objectName in pleasance.configurationObjects():
            response += "<a href='" + web.ctx.home + "/dump/" + objectName + "'>" + objectName + "</a><br/>"
        response += "</body></html>"
        return response


class dumpObject:
    def GET(self, objectName):
        objectName = str(objectName)
        web.header('Content-Type', 'application/json')
        web.header('X-Object-Name', objectName)
        return pleasance.dumpConfigurationObject(objectName)


##############################################################################
####### Configuration - Consists of global settings and per-server ones ######
##############################################################################

class configuration:  # List available configurations (aka service instances)
    def GET(self):
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Applications</title></head><body>"
        for environmentName in pleasance.listObjects("environments"):
            response += "<a href='" + web.ctx.home + "/configuration/" + environmentName + "'>"
            response += environmentName + "</a><br/>"
        response += "</body></html>"
        return response


class configurationServiceInstance:  # Get / Update / Delete global configuration for a given service instance
    def GET(self, instanceName):
        try:
            web.header('Content-Type', 'application/json')
            return pleasance.retrieveConfiguration(instanceName)
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()

    def PUT(self, instanceName):
        try:
            if pleasance.updateConfiguration(instanceName, web.ctx.env.get('CONTENT_TYPE'), web.data()):
                return "Updated Environment " + instanceName
        except pleasance.ConfigurationNotJSONError:
            return web.webapi.UnsupportedMediaType()
        except pleasance.ConfigurationNotValidJSONError:
            return web.badrequest('Could not parse the JSON supplied')

    def DELETE(self, instanceName):
        return pleasance.deleteConfiguration(instanceName)


class configurationServiceInstanceHosts:  # Get / Update / Delete individual server configuration for a given instance
    def GET(self, instanceName, nodeIdentifier):
        try:
            web.header('Content-Type', 'application/json')
            return pleasance.retrieveNodeConfiguration(instanceName, nodeIdentifier)
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()

    def PUT(self, instanceName, nodeIdentifier):
        try:
            if pleasance.createNodeConfiguration(instanceName, nodeIdentifier, web.ctx.env.get('CONTENT_TYPE'),
                                                 web.data()):
                return "Updated node configuration for " + nodeIdentifier + " in " + instanceName
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()
        except pleasance.ConfigurationNotValidJSONError:
            return web.badrequest('Could not parse the JSON supplied')

    def DELETE(self, instanceName, nodeIdentifier):
        try:
            if pleasance.deleteNodeConfiguration(instanceName, nodeIdentifier):
                return "Deleted " + nodeIdentifier + " from " + instanceName
        except pleasance.EnvironmentNotFoundError:
            return web.notfound()


################################################################################
######## Packages: Store different versions of a deployment package ############
################################################################################

class ShowAllPackages:
    def GET(self):  # List available packages
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Applications</title></head><body>"
        for packageName in pleasance.listObjects("packages"):
            response += "<a href='" + web.ctx.home + "/packages/" + packageName + "'>" + packageName + "</a><br/>"
        response += "</body></html>"
        return response


class packageInstances:  # create / delete new package, list available package versions
    def GET(self, packageName):
        if packageName in pleasance.listObjects("packages"):
            web.header('Content-Type', 'text/html')
            response = "<html><head><title>Available Application Versions</title></head><body>"
            for packageVersion in pleasance.listPackageVersions(packageName):
                response += "<a href='" + web.ctx.home + "/packages/" + packageName + "/" \
                            + packageVersion + "'>" + packageVersion + "</a><br/>"
            response += "</body></html>"
            return response
        else:
            return web.notfound("Application does not exist")

    def PUT(self, packageName):
        if pleasance.createPackage(packageName):
            return "Created package " + packageName
        else:
            return web.internalerror()

    def DELETE(self, packageName):
        try:
            if pleasance.deletePackage(packageName):
                return "Deleted package " + packageName
            else:
                return web.badrequest()
        except pleasance.PackageNotFoundError:
            return "Package does not exist - no action taken"


class packageVersionPromote:  # Flag a package so that it shouldn't be cleaned up automatically
    def GET(self, packageName, packageVersion):
        try:
            if pleasance.promotePackageVersion(packageName, packageVersion, True):
                return "Promoted " + packageName + " version " + packageVersion
        except pleasance.PackageNotFoundError:
            return web.notfound()
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


class packageVersionUnpromote:  # Flag a package for automatic deletion
    def GET(self, packageName, packageVersion):
        try:
            if pleasance.promotePackageVersion(packageName, packageVersion, False):
                return "Unpromoted " + packageName + " version " + packageVersion
        except pleasance.PackageNotFoundError:
            return web.notfound()
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()


class packageInstanceVersions:  # Create / Update / Delete given version of a package
    def GET(self, packageName, packageVersion):
        try:
            (contentType, packageContents) = pleasance.retrievePackageVersion(packageName, packageVersion)
            web.header('Content-Type', contentType)
            return packageContents
        except pleasance.PackageInstanceNotFoundError:
            return web.notfound()
        except pleasance.CannotUpdatePackageError:
            return web.internalerror()

    def PUT(self, packageName, packageVersion):
        contentType = ''
        if web.ctx.env.get('CONTENT_TYPE'):
            contentType = web.ctx.env.get('CONTENT_TYPE')
        try:
            return pleasance.updatePackageVersion(packageName, packageVersion, contentType, web.data())
        except pleasance.PackageNotFoundError:
            return web.notfound()

    def DELETE(self, packageName, packageVersion):
        try:
            if pleasance.deletePackageVersion(packageName, packageVersion):
                return packageName + " has been deleted"
        except pleasance.PackageNotFoundError:
            return web.notfound()


################################################################################
################## Bootstrap: Returns the bootstrap script #####################
################################################################################

# The bootstrap script fetches the installation script plus configuration for it.
# It doesn't install the application directly. Why? The installation executable
# could be written in anything (java, shell, chef, puppet...). The bootstrap's
# job is to invoke that correctly rather than install anything itself.
# Valid osNames are likely to be windows (Powershell) and linux (bash)
#
# Example URL: # /bootstrap/linux/eqc-pm-service-int/eqc-pm/1.0

class bootstrap:
    def GET(self):
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Bootstraps</title></head><body>"
        for osName in pleasance.listObjects("bootstraps"):
            response += "<a href='" + web.ctx.home + "/bootstrap/" + osName + "'>" + osName + "</a><br/>"
        response += "</body></html>"
        return response


class bootstrapServer:
    def GET(self, context):
        platform = context
        if context.lstrip('/').split('/').__len__() == 4:
            (platform, environment, application, applicationVersion) = context.lstrip('/').split('/', 4)
            configurationUrl = web.ctx.home + "/configuration/" + environment
            packageUrl = web.ctx.home + "/packages/" + application + "/" + applicationVersion
            try:
                installerUrl = web.ctx.home + "/installer/" + pleasance.getInstallerType(environment) + "/" + platform
            except pleasance.EnvironmentNotFoundError:
                return web.notfound()
        try:
            (bootStrap, contentType) = pleasance.retrieveBootStrap(platform)
        except pleasance.bootStrapNotFoundError:
            return web.notfound()
        web.header('Content-Type', contentType)
        if context.lstrip('/').split('/').__len__() == 4:
            bootStrap = bootStrap.replace("{{packageURL}}", packageUrl)
            bootStrap = bootStrap.replace("{{environmentConfiguration}}", configurationUrl)
            bootStrap = bootStrap.replace("{{installerPath}}", installerUrl)
            bootStrap = bootStrap.replace("{{packageVersion}}", applicationVersion)
            bootStrap = bootStrap.replace("{{packageName}}", application)
        web.header('Content-Type', contentType)
        return bootStrap


    def PUT(self, context):
        if context.lstrip('/').split('/').__len__() > 1:
            return web.badrequest(context + " " + str(context.lstrip('/').split('/')) + " greater than 1")
        else:
            contentType = ""
            if web.ctx.env.get('CONTENT_TYPE'):
                contentType = web.ctx.env.get('CONTENT_TYPE')
            if pleasance.storeBootstrap(context, contentType, web.data()):
                return "Created bootstrap " + context
            raise Exception

    def DELETE(self, context):
        if context.lstrip('/').split('/').__len__() > 1:
            return web.badrequest(context + " " + str(context.lstrip('/').split('/')) + " greater than 1")
        else:
            if pleasance.deleteBootstrap(context):
                return "Deleted Bootstrap " + context


################################################################################
############# Installers: container-specific installers go here ################
################################################################################

class installers:
    def GET(self):
        web.header('Content-Type', 'text/html')
        response = "<html><head><title>Available Installers</title></head><body>"
        for installerName in pleasance.listObjects("installers"):
            response += "<a href='" + web.ctx.home + "/installer/" + installerName + "'>" + installerName + "</a><br/>"
        response += "</body></html>"
        return response


class installerInstances:
    def GET(self, installerName):
        try:
            web.header('Content-Type', 'text/html')
            response = "<html><head><title>Available Installers</title></head><body>"
            for platformName in pleasance.listInstallerInstances(installerName):
                response += "<a href='" + web.ctx.home + "/installer/" + installerName + "/" + platformName + "'>" + \
                            platformName + "</a><br/>"
            response += "</body></html>"
            return response
        except pleasance.InstallerNotFoundError:
            return web.notfound()

    def PUT(self, installerName):
        if pleasance.createInstaller(installerName):
            return "Created installer " + installerName


class installerInstanceSpecific:
    def GET(self, installerName, targetOS):
        try:
            (contentType, installerData) = pleasance.retrieveInstallerInstance(installerName, targetOS)
            web.header('Content-Type', contentType)
            return installerData
        except pleasance.InstallerInstanceNotFoundError:
            return web.notfound()

    def PUT(self, installerName, targetOS):
        contentType = ''
        if web.ctx.env.get('CONTENT_TYPE'):
            contentType = web.ctx.env.get('CONTENT_TYPE')
        try:
            if pleasance.updateInstallerSpecific(installerName, targetOS, contentType, web.data()):
                return "Created Installer for " + installerName + " on platform: " + targetOS
        except pleasance.InstallerNotFoundError:
            return web.notfound()

    def DELETE(self, installerName, targetOS):
        try:
            if pleasance.deleteInstallerSpecific(installerName, targetOS):
                return "Deleted Installer for " + installerName + " on platform: " + targetOS
        except pleasance.InstallerNotFoundError:
            return web.notfound()



################################################################################
########################### Startup Here #######################################
################################################################################

############ Settings here  ###################

packageRepositoryLocation = "./packages"
configurationRepositoryLocation = "./configuration"
pleasance = PleasanceShelf('./packages', './configuration')

############### End Settings ##################

if __name__ == "__main__":
    app.run()
