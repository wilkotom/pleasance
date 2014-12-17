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

    def __init__(self, package_repository_directory, configuration_database_file):
        self.configurationRepository = self.shelve.open(configuration_database_file, writeback=True)
        self.packageRepositoryDirectory = package_repository_directory
        if not self.os.path.exists(package_repository_directory):
            self.os.mkdir(package_repository_directory)
        if "packages" not in self.configurationRepository:
            self.configurationRepository["packages"] = {}
        if "environments" not in self.configurationRepository:
            self.configurationRepository["environments"] = {}
        if "bootstraps" not in self.configurationRepository:
            self.configurationRepository["bootstraps"] = {}
        if "installers" not in self.configurationRepository:
            self.configurationRepository["installers"] = {}

    def configuration_objects(self):
        return self.configurationRepository.keys()

    def dump_configuration_object(self, object_name):
        return self.json.dumps(self.configurationRepository[object_name], sort_keys=True, indent=2,
                               separators=(',', ': '))

    def list_objects(self, object_type):
        return self.configurationRepository[object_type].keys()

    def create_package(self, package_name):
        if package_name not in self.configurationRepository["packages"]:
            self.configurationRepository["packages"][package_name] = {}
            self.configurationRepository.sync()
        return True

    def delete_package(self, package_name):
        if package_name in self.configurationRepository["packages"]:
            if self.configurationRepository["packages"][package_name]:
                # We won't delete a package if it has existing versions
                return False
            else:
                del self.configurationRepository["packages"][package_name]
                return True
        else:
            raise self.PackageNotFoundError

    def list_package_versions(self, package_name):
        return self.configurationRepository["packages"][package_name].keys()

    def retrieve_package_version(self, package_name, package_version):
        if package_name in self.configurationRepository["packages"] and (
                package_version in self.configurationRepository["packages"][
                package_name] or package_version == 'latest'):
            if package_version == 'latest':
                package_version = sorted(self.configurationRepository["packages"][package_name])[-1]
            file_name = self.configurationRepository["packages"][package_name][package_version]["checksum"]
            file_handle = open(self.packageRepositoryDirectory + '/' + file_name, "r")
            return self.configurationRepository["packages"][package_name][package_version]["type"], file_handle.read()
        else:
            raise self.PackageInstanceNotFoundError

    def update_package_version(self, package_name, package_version, content_type, package_data):
        if package_name in self.configurationRepository["packages"]:
            filename = self.hashlib.sha1(package_data).hexdigest()
            response = ''
            old_file_name = 'NonExistent'
            # Delete the old version, if it exists
            if package_version in self.configurationRepository["packages"][package_name]:
                response += "Deleted " + self.configurationRepository["packages"][package_name][package_version][
                    "checksum"]
                old_file_name = self.configurationRepository["packages"][package_name][package_version]["checksum"]
                self.os.rename(self.packageRepositoryDirectory + '/' + old_file_name,
                               self.packageRepositoryDirectory + '/' + old_file_name + '.old')
                # Note: if we have 2 files with the same contents, this will break.
                # Need a better test to see if a file is OK to release. Periodic garbage collection?
            try:
                file_handle = open(self.packageRepositoryDirectory + '/' + filename, "w")
                file_handle.write(package_data)
                file_handle.close()
                response += "Created " + package_name + " " + package_version + " with checksum " + filename + '\n'
            except:
                self.os.rename(self.packageRepositoryDirectory + '/' + old_file_name + '.old',
                               self.packageRepositoryDirectory + '/' + old_file_name)
                raise self.CannotUpdatePackageError
            if content_type == '':
                content_type = self.magic.from_buffer(package_data, mime=True)
            new_version = {"checksum": filename, "type": content_type, "promoted": False, "created": self.time()}
            self.configurationRepository["packages"][package_name][package_version] = new_version
            self.configurationRepository.sync()
            if self.os.path.exists(self.packageRepositoryDirectory + '/' + old_file_name + '.old'):
                self.os.remove(self.packageRepositoryDirectory + '/' + old_file_name + '.old')
            response = response + "Current Versions available:" + '\n'.join(
                self.configurationRepository["packages"][package_name].keys())
            return response
        else:
            raise self.PackageNotFoundError

    def promote_package_version(self, package_name, package_version, promotion_flag):
        if package_name in self.configurationRepository["packages"]:
            if package_version in self.configurationRepository["packages"][package_name]:
                self.configurationRepository["packages"][package_name][package_version]["promoted"] = promotion_flag
                self.configurationRepository.sync()
                return True
            else:
                raise self.PackageInstanceNotFoundError
        else:
            raise self.PackageNotFoundError

    def delete_package_version(self, package_name, package_version):
        promoted = False
        if package_name in self.configurationRepository["packages"]:
            if package_version in self.configurationRepository["packages"][package_name].keys():
                if "promoted" in self.configurationRepository["packages"][package_name][package_version]:
                    promoted = self.configurationRepository["packages"][package_name][package_version]["promoted"]
                if promoted:
                    return False  # Can't delete a promoted build
                filename = self.configurationRepository["packages"][package_name][package_version]["checksum"]
                self.os.remove(self.packageRepositoryDirectory + '/' + filename)  # same note as above re: collisions
                del self.configurationRepository["packages"][package_name][package_version]
                self.configurationRepository.sync()
            return True
        else:
            raise self.PackageNotFoundError

    def retrieve_configuration(self, instance_name):
        if instance_name in self.configurationRepository["environments"]:
            if "globalConfiguration" in self.configurationRepository["environments"][instance_name]:
                return self.json.dumps(
                    self.configurationRepository["environments"][instance_name]["globalConfiguration"],
                    sort_keys=True, indent=2, separators=(',', ': '))
            else:
                raise self.EnvironmentNotFoundError
        else:
            raise self.EnvironmentNotFoundError

    def update_configuration(self, instance_name, content_type, payload):
        if content_type == "application/json":
            try:
                configuration_data = self.json.loads(payload)
            except ValueError:
                raise self.ConfigurationNotValidJSONError
            if instance_name in self.configurationRepository["environments"] and "hostOverrides" in \
                    self.configurationRepository["environments"][instance_name]:
                # Preserve existing host overrides
                host_overrides = self.configurationRepository["environments"][instance_name]["hostOverrides"]
            else:
                host_overrides = {}
            self.configurationRepository["environments"][instance_name] = {"globalConfiguration": configuration_data,
                                                                           "hostOverrides": host_overrides}
            self.configurationRepository.sync()
            return True
        else:
            raise self.ConfigurationNotJSONError

    def delete_configuration(self, instance_name):
        if self.configurationRepository["environments"][instance_name]:
            del self.configurationRepository["environments"][instance_name]
            self.configurationRepository.sync()
            return "Deleted Environment " + instance_name
        else:
            return "Environment does not exist - no action taken"

    def retrieve_node_configuration(self, instance_name, node_name):
        if instance_name in self.configurationRepository["environments"].keys():
            if node_name in self.configurationRepository["environments"][instance_name]["hostOverrides"]:
                return self.json.dumps(
                    self.configurationRepository["environments"][instance_name]["hostOverrides"][node_name],
                    sort_keys=True, indent=2, separators=(',', ': '))
            else:
                return {}  # For valid environments, we want to return an empty dictionary unless we know better
        else:
            raise self.EnvironmentNotFoundError

    def create_node_configuration(self, instance_name, node_name, content_type, payload):
        if content_type == "application/json":
            try:
                configuration_data = self.json.loads(payload)
            except ValueError:
                raise self.ConfigurationNotValidJSONError
            host_overrides = configuration_data
            self.configurationRepository["environments"][instance_name]["hostOverrides"][node_name] = host_overrides
            self.configurationRepository.sync()
            return True
        else:
            raise self.ConfigurationNotJSONError

    def delete_node_configuration(self, instance_name, node_name):
        if instance_name in self.configurationRepository["environments"].keys():
            if node_name in self.configurationRepository["environments"][instance_name]["hostOverrides"]:
                del self.configurationRepository["environments"][instance_name]["hostOverrides"][node_name]
            return True
        else:
            raise self.EnvironmentNotFoundError

    def store_bootstrap(self, bootstrap_name, content_type, bootstrap_data):
        self.configurationRepository["bootstraps"][bootstrap_name] = {}
        self.configurationRepository["bootstraps"][bootstrap_name]["script"] = bootstrap_data
        if content_type == '':
            content_type = self.magic.from_buffer(bootstrap_data, mime=True)
        self.configurationRepository["bootstraps"][bootstrap_name]["type"] = content_type
        return True

    def retrieve_bootstrap(self, bootstrap_name):
        if bootstrap_name in self.configurationRepository["bootstraps"]:
            return (self.configurationRepository["bootstraps"][bootstrap_name]["script"],
                    self.configurationRepository["bootstraps"][bootstrap_name]["type"])
        else:
            raise self.BootStrapNotFoundError

    def delete_bootstrap(self, bootstrap_name):
        if bootstrap_name in self.configurationRepository["bootstraps"]:
            del self.configurationRepository["bootstraps"][bootstrap_name]
        return True

    def get_installer_type(self, instance_name):
        if self.configurationRepository["environments"][instance_name]:
            return self.configurationRepository["environments"][instance_name]["globalConfiguration"]["deploymentType"]
        else:
            raise self.EnvironmentNotFoundError

    def list_installer_instances(self, installer_name):
        if installer_name in self.configurationRepository["installers"]:
            return self.configurationRepository["installers"][installer_name].keys()
        else:
            raise self.InstallerNotFoundError

    def create_installer(self, installer_name):
        if installer_name in self.configurationRepository["installers"]:
            return True
        else:
            self.configurationRepository["installers"][installer_name] = {}
            self.configurationRepository.sync()
            return True

    def retrieve_installer_instance(self, installer_name, target_os):
        if installer_name in self.configurationRepository["installers"] and target_os in \
                self.configurationRepository["installers"][installer_name]:
            filename = self.configurationRepository["installers"][installer_name][target_os]["checksum"]
            file_handle = open(self.packageRepositoryDirectory + '/' + filename, "r")
            return self.configurationRepository["installers"][installer_name][target_os]["type"], file_handle.read()
        else:
            raise self.InstallerInstanceNotFoundError

    def update_installer_specific(self, installer_name, target_os, content_type, installer_data):
        old_filename = ''
        if installer_name in self.configurationRepository["installers"]:
            if content_type == '':
                content_type = self.magic.from_buffer(installer_data, mime=True)
            filename = self.hashlib.sha1(installer_data).hexdigest()
            if target_os in self.configurationRepository["installers"][installer_name].keys():
                old_filename = self.configurationRepository["installers"][installer_name][target_os]["checksum"]
                if old_filename == filename:
                    return True  # The existing installer is the same as the one uploaded.
            file_handle = open(self.packageRepositoryDirectory + '/' + filename, "w")
            file_handle.write(installer_data)
            file_handle.close()
            if old_filename != '':
                self.os.remove(self.packageRepositoryDirectory + '/' + old_filename)
            self.configurationRepository["installers"][installer_name][target_os] = {'checksum': filename,
                                                                                     'type': content_type}
            self.configurationRepository.sync()
            return True
        else:
            raise self.InstallerNotFoundError

    def delete_installer_specific(self, installer_name, target_os):
        if installer_name in self.configurationRepository["installers"]:
            if target_os in self.configurationRepository["installers"][installer_name]:
                filename = self.configurationRepository["installers"][installer_name][target_os]["checksum"]
                self.os.remove(filename)
                del self.configurationRepository["installers"][installer_name][target_os]
                self.configurationRepository.sync()
            return True
        else:
            raise self.InstallerNotFoundError

    class PackageNotFoundError(Exception):
        """The package specified does not exist"""

    class PackageInstanceNotFoundError(Exception):
        """The particular package instance specified is missing"""

    class ConfigurationNotJSONError(Exception):
        """The Configuration uploaded is not specified as JSON"""

    class ConfigurationNotValidJSONError(Exception):
        """The Configuration uploaded does not parse as JSON"""

    class EnvironmentNotFoundError(Exception):
        """The specified Environment does not exist """

    class BootStrapNotFoundError(Exception):
        """The specified bootstrap does not exist"""

    class InstallerNotFoundError(Exception):
        """The Specified installer does not exist"""

    class InstallerInstanceNotFoundError(Exception):
        """The specified instance of an installer does not exist"""

    class CannotUpdatePackageError(Exception):
        """Package could not be updated"""