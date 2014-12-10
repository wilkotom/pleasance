#!/usr/bin/env python

__author__ = 'twilkinson'


class PleasanceShelf:
    import json
    import os
    import hashlib
    import shelve
    import magic
    import re
    from time import time
    import sys

    def __init__(self, packageRepositoryDirectory, configurationDatabaseFile):
        self.configurationRepository = self.shelve.open(configurationDatabaseFile, writeback=True)
        self.packageRepositoryDirectory = packageRepositoryDirectory
        if not self.os.path.exists(packageRepositoryDirectory):
            self.os.mkdir(packageRepositoryDirectory)
        if not "packages" in self.configurationRepository:
            self.configurationRepository["packages"] = {}
        if not "environments" in self.configurationRepository:
            self.configurationRepository["environments"] = {}
        if not "bootstraps" in self.configurationRepository:
            self.configurationRepository["bootstraps"] = {}
        if not "installers" in self.configurationRepository:
            self.configurationRepository["installers"] = {}

    def configurationObjects(self):
        return self.configurationRepository.keys()

    def dumpConfigurationObject(self, objectName):
        return self.json.dumps(self.configurationRepository[objectName], sort_keys=True, indent=2,
                               separators=(',', ': '))

    def listObjects(self, objectType):
        return self.configurationRepository[objectType].keys()

    def createPackage(self, packageName):
        if not packageName in self.configurationRepository["packages"]:
            self.configurationRepository["packages"][packageName] = {}
            self.configurationRepository.sync()
        return True

    def deletePackage(self, packageName):
        if packageName in self.configurationRepository["packages"]:
            if self.configurationRepository["packages"][packageName]:
                # We won't delete a package if it has existing versions
                return False
            else:
                del self.configurationRepository["packages"][packageName]
                return True
        else:
            raise self.PackageNotFoundError

    def listPackageVersions(self, packageName):
        return self.configurationRepository["packages"][packageName].keys()

    def retrievePackageVersion(self, packageName, packageVersion):
        if packageName in self.configurationRepository["packages"] and (packageVersion in
                                                                            self.configurationRepository["packages"][
                                                                                packageName] or packageVersion == 'latest'):
            if packageVersion == 'latest':
                packageVersion = sorted(self.configurationRepository["packages"][packageName])[-1]
            fileName = self.configurationRepository["packages"][packageName][packageVersion]["checksum"]
            fileHandle = open(self.packageRepositoryDirectory + '/' + fileName, "r")
            return (self.configurationRepository["packages"][packageName][packageVersion]["type"], fileHandle.read())
        else:
            raise self.PackageInstanceNotFoundError

    def updatePackageVersion(self, packageName, packageVersion, contentType, packageData):
        if packageName in self.configurationRepository["packages"]:
            fileName = self.hashlib.sha1(packageData).hexdigest()
            response = ''
            oldFileName = 'NonExistent'
            # Delete the old version, if it exists
            if packageVersion in self.configurationRepository["packages"][packageName]:
                response += "Deleted " + self.configurationRepository["packages"][packageName][packageVersion][
                    "checksum"]
                oldFileName = self.configurationRepository["packages"][packageName][packageVersion]["checksum"]
                self.os.rename(self.packageRepositoryDirectory + '/' + oldFileName,
                               self.packageRepositoryDirectory + '/' + oldFileName + '.old')
                # Note: if we have 2 files with the same contents, this will break.
                # Need a better test to see if a file is OK to release. Periodic garbage collection?
            try:
                fileHandle = open(self.packageRepositoryDirectory + '/' + fileName, "w")
                fileHandle.write(packageData)
                fileHandle.close()
                response += "Created " + packageName + " " + packageVersion + " with checksum " + fileName + '\n'
            except:
                self.os.rename(self.packageRepositoryDirectory + '/' + oldFileName + '.old',
                               self.packageRepositoryDirectory + '/' + oldFileName)
                raise self.CannotUpdatePackageError
            if contentType == '':
                contentType = self.magic.from_buffer(packageData, mime=True)
            newVersion = {"checksum": fileName, "type": contentType, "promoted": False, "created": self.time()}
            self.configurationRepository["packages"][packageName][packageVersion] = newVersion
            self.configurationRepository.sync()
            if self.os.path.exists(self.packageRepositoryDirectory + '/' + oldFileName + '.old'):
                self.os.remove(self.packageRepositoryDirectory + '/' + oldFileName + '.old')
            response = response + "Current Versions available:" + '\n'.join(
                self.configurationRepository["packages"][packageName].keys())
            return response
        else:
            raise self.PackageNotFoundError

    def promotePackageVersion(self, packageName, packageVersion, promotionFlag):
        if packageName in self.configurationRepository["packages"]:
            if packageVersion in self.configurationRepository["packages"][packageName]:
                self.configurationRepository["packages"][packageName][packageVersion]["promoted"] = promotionFlag
                self.configurationRepository.sync()
                return True
            else:
                raise self.PackageInstanceNotFoundError
        else:
            raise self.PackageNotFoundError

    def deletePackageVersion(self, packageName, packageVersion):
        promoted = False
        if packageName in self.configurationRepository["packages"]:
            if packageVersion in self.configurationRepository["packages"][packageName].keys():
                if "promoted" in  self.configurationRepository["packages"][packageName][packageVersion]:
                    promoted = self.configurationRepository["packages"][packageName][packageVersion]["promoted"]
                if promoted == True:
                    return False # Can't delete a promoted build
                fileName = self.configurationRepository["packages"][packageName][packageVersion]["checksum"]
                self.os.remove(self.packageRepositoryDirectory + '/' + fileName)  # same note as above re: collisions
                del self.configurationRepository["packages"][packageName][packageVersion]
                self.configurationRepository.sync()
            return True
        else:
            raise self.PackageNotFoundError

    def retrieveConfiguration(self, instanceName):
        if instanceName in self.configurationRepository["environments"]:
            if "globalConfiguration" in self.configurationRepository["environments"][instanceName]:
                return self.json.dumps(self.configurationRepository["environments"][instanceName]["globalConfiguration"],
                                  sort_keys=True, indent=2, separators=(',', ': '))
            else:
                raise self.EnvironmentNotFoundError
        else:
            raise self.EnvironmentNotFoundError

    def updateConfiguration(self, instanceName, contentType, payload):
        if contentType == "application/json":
            try:
                configurationData = self.json.loads(payload)
            except ValueError:
                raise self.ConfigurationNotValidJSONError
            if instanceName in self.configurationRepository["environments"] and \
                            "hostOverrides" in self.configurationRepository["environments"][instanceName]:
                # Preserve existing host overrides
                hostOverrides = self.configurationRepository["environments"][instanceName]["hostOverrides"]
            else:
                hostOverrides = {}
            self.configurationRepository["environments"][instanceName] = {"globalConfiguration": configurationData,
                                                                          "hostOverrides": hostOverrides}
            self.configurationRepository.sync()
            return True
        else:
            raise self.ConfigurationNotJSONError

    def deleteConfiguration(self, instanceName):
        if self.configurationRepository["environments"][instanceName]:
            del self.configurationRepository["environments"][instanceName]
            self.configurationRepository.sync()
            return "Deleted Environment " + instanceName
        else:
            return "Environment does not exist - no action taken"

    def retrieveNodeConfiguration(self, instanceName, nodeName):
        if instanceName in self.configurationRepository["environments"].keys():
            if nodeName in self.configurationRepository["environments"][instanceName]["hostOverrides"]:
                return self.json.dumps(self.configurationRepository["environments"][instanceName]["hostOverrides"][nodeName],
                                  sort_keys=True, indent=2, separators=(',', ': '))
            else:
                return {}  # For valid environments, we want to return an empty dictionary unless we know better
        else:
            raise self.EnvironmentNotFoundError

    def createNodeConfiguration(self, instanceName, nodeName, contentType, payload):
        if contentType == "application/json":
            try:
                configurationData = self.json.loads(payload)
            except ValueError:
                raise self.ConfigurationNotValidJSONError
            hostOverrides = configurationData
            self.configurationRepository["environments"][instanceName]["hostOverrides"][nodeName] = hostOverrides
            self.configurationRepository.sync()
            return True
        else:
            raise self.ConfigurationNotJSONError

    def deleteNodeConfiguration(self, instanceName, nodeName):
        if instanceName in self.configurationRepository["environments"].keys():
            if nodeName in self.configurationRepository["environments"][instanceName]["hostOverrides"]:
                del self.configurationRepository["environments"][instanceName]["hostOverrides"][nodeName]
            return True
        else:
            raise self.EnvironmentNotFoundError

    def storeBootstrap(self, bootstrapName, contentType, bootstrapData):
        self.configurationRepository["bootstraps"][bootstrapName] = {}
        self.configurationRepository["bootstraps"][bootstrapName]["script"] = bootstrapData
        if contentType == '':
            contentType = self.magic.from_buffer(bootstrapData, mime=True)
        self.configurationRepository["bootstraps"][bootstrapName]["type"] = contentType
        return True

    def retrieveBootStrap(self, bootstrapName):
        if bootstrapName in self.configurationRepository["bootstraps"]:
            return (self.configurationRepository["bootstraps"][bootstrapName]["script"],
                    self.configurationRepository["bootstraps"][bootstrapName]["type"])
        else:
            raise self.bootStrapNotFoundError

    def deleteBootstrap(self, bootstrapName):
        if bootstrapName in self.configurationRepository["bootstraps"]:
            del self.configurationRepository["bootstraps"][bootstrapName]
        return True

    def getInstallerType(self, instanceName):
        if self.configurationRepository["environments"][instanceName]:
            return self.configurationRepository["environments"][instanceName]["globalConfiguration"]["deploymentType"]
        else:
            raise self.EnvironmentNotFoundError

    def listInstallerInstances(self, installerName):
        if installerName in self.configurationRepository["installers"]:
            return self.configurationRepository["installers"][installerName].keys()
        else:
            raise self.InstallerNotFoundError

    def createInstaller(self, installerName):
        if installerName in self.configurationRepository["installers"]:
            return True
        else:
            self.configurationRepository["installers"][installerName] = {}
            return True

    def retrieveInstallerInstance(self, installerName, targetOS):
        if installerName in self.configurationRepository["installers"] and targetOS in \
                self.configurationRepository["installers"][installerName]:
            fileName = self.configurationRepository["installers"][installerName][targetOS]["checksum"]
            filehandle = open(self.packageRepositoryDirectory + '/' + fileName, "r")
            return (self.configurationRepository["installers"][installerName][targetOS]["type"], filehandle.read())
        else:
            raise self.InstallerInstanceNotFoundError

    def updateInstallerSpecific(self, installerName, targetOS, contentType, installerData):
        oldFileName = ''
        if installerName in self.configurationRepository["installers"]:
            if contentType == '':
                contentType = self.magic.from_buffer(installerData, mime=True)
            fileName = self.hashlib.sha1(installerData).hexdigest()
            if targetOS in self.configurationRepository["installers"][installerName].keys():
                oldFileName = self.configurationRepository["installers"][installerName][targetOS]["checksum"]
                if oldFileName == fileName:
                    return True  # The existing installer is the same as the one uploaded.
            fileHandle = open(self.packageRepositoryDirectory + '/' + fileName, "w")
            fileHandle.write(installerData)
            fileHandle.close()
            if oldFileName != '':
                self.os.remove(self.packageRepositoryDirectory + '/' + oldFileName)
            self.configurationRepository["installers"][installerName][targetOS] = {'checksum': fileName,
                                                                                   'type': contentType}
            self.configurationRepository.sync()
            return True
        else:
            raise self.InstallerNotFoundError

    def deleteInstallerSpecific(self, installerName, targetOS):
        if installerName in self.configurationRepository["installers"]:
            if targetOS in self.configurationRepository["installers"][installerName]:
                fileName = self.configurationRepository["installers"][installerName][targetOS]["checksum"]
                self.os.remove(fileName)
                del self.configurationRepository["installers"][installerName][targetOS]
                self.configurationRepository.sync()
            return True
        else:
            raise self.InstallerNotFoundError

    class PackageNotFoundError(Exception):
        '''The package specified does not exist'''

    class PackageInstanceNotFoundError(Exception):
        '''The particular package instance specified is missing'''

    class ConfigurationNotJSONError(Exception):
        '''The Configuration uploaded is not specified as JSON'''

    class ConfigurationNotValidJSONError(Exception):
        '''The configuration uploaded does not parse as JSON'''

    class EnvironmentNotFoundError(Exception):
        '''The specified Environment does not exist '''

    class bootStrapNotFoundError(Exception):
        '''The specified bootstrap does not exist'''

    class InstallerNotFoundError(Exception):
        '''The Specified installer does not exist'''

    class InstallerInstanceNotFoundError(Exception):
        '''The specified instance of an installer does not exist'''

    class CannotUpdatePackageError(Exception):
        '''Package could not be updated'''