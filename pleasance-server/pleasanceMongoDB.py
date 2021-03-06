#!/usr/bin/env python

__author__ = 'twilkinson'

import json
import hashlib
import magic
from time import time
import sys
from pymongo import MongoClient
import gridfs

class PleasanceMongo:

    def __init__(self, mongo_server, mongo_port):
        self.mongo_server = mongo_server
        self.mongo_port = mongo_port
        self.mongo_database = MongoClient(mongo_server, mongo_port).pleasance
        self.packages = self.mongo_database.packages
        self.environments = self.mongo_database.environments
        self.bootstraps = self.mongo_database.bootstraps
        self.installers = self.mongo_database.installers
        self.history = self.mongo_database.history
        self.filestore = gridfs.GridFS(self.mongo_database)

    def __str__(self):
        return "Pleasance Mongo DB instance connected to {0}:{1}".format(self.mongo_server, self.mongo_port)

    def configuration_objects(self):
        """Lists Internal configuration Objects"""
        return ['environments', 'bootstraps', 'installers', 'packages']

    def dump_configuration_object(self, object_name):
        """Returns a JSON object containing the contents of the specified object type,
        stripped of internal references"""
        output = {}
        if object_name == 'packages':
            for result in self.packages.find():
                del result['_id']
                name = result['name']
                version = result['version']
                del result['name']
                del result['version']
                if 'file_id' in result:
                    del result['file_id']
                if name not in output:
                    output[name] = {}
                output[name][version] = result
        elif object_name == 'installers':
            for result in self.installers.find():
                del result['_id']
                del result['file_id']
                name = result['name']
                platform = result['platform']
                del result['name']
                del result['platform']
                if name not in output:
                    output[name] = {}
                output[name][platform] = result
        elif object_name == 'bootstraps':
            for result in self.bootstraps.find():
                del result["_id"]
                platform = result['platform']
                del result['platform']
                output[platform] = result
        elif object_name == 'environments':
            for result in self.environments.find():
                del result["_id"]
                name = result['name']
                del result['name']
                if 'deploymentDictionary' in result['globalConfiguration']:
                    for key in result['globalConfiguration']['deploymentDictionary'].keys():
                        if '%2E' in key:  # Because BSON doesn't allow periods in key names, they're encoded to %2E
                            new_key_name = key.replace('%2E', '.')
                            result['globalConfiguration']['deploymentDictionary'][new_key_name] = \
                                result['globalConfiguration']['deploymentDictionary'].pop(key)
                output[name] = result

        return json.dumps(output, sort_keys=True, indent=2, separators=(',', ': '))

    def list_objects(self, object_type):
        """Returns a list of available Pleasance objects of the specified type"""
        object_list = {}
        if object_type == 'packages':
            for result in self.packages.find():
                object_list[result['name']] = ''
        elif object_type == 'bootstraps':
            for result in self.bootstraps.find():
                object_list[result['platform']] = ''
        elif object_type == 'environments':
            for result in self.environments.find():
                object_list[result['name']] = ''
        elif object_type == 'installers':
            for result in self.installers.find():
                object_list[result['name']] = ''
        return object_list.keys()

    def list_package_versions(self, package_name):
        """Returns a list of the available versions of a named package"""
        version_list = []
        for package in self.packages.find({"name": package_name}):
            version_list.append(package['version'])
        return version_list

    def create_package(self, package_name):
        # Because the schema is different under MongoDB, we don't need to create a package before an instance of it
        """Creates the top-level entry for a given named package"""
        return True

    def delete_package(self, package_name):
        """Deletes the top-level entry for a given named package"""
        # This is really meaningless, it's a No-Op regardless but it's here for compatibility.
        # There's no concept of a package with no versions in the underlying DB, we just want this function
        # to behave in the same way as other implementations.
        if package_name in self.list_objects("packages"):
            return False  # If a package is in the list, there's at least one version of it. So we can't delete it.
        else:
            raise self.PackageNotFoundError

    def update_package_version(self, package_name, package_version, content_type, package_data):
        """Stores the supplied version of a package. If it already exists, replaces the existing
        package of the same version"""
        filename = hashlib.sha1(package_data).hexdigest()
        response = ''
        existing_package = self.packages.find_one({"name": package_name, "version": package_version})

        if content_type == '':
            try:
                content_type = magic.from_buffer(package_data[:1024], mime=True)
            except magic.MagicException as magic_exception:
                content_type = 'application/octet-stream'
                sys.stderr.write(
                    'Warning: Exception raised by Magic Library, falling back to application/octet-stream')
                sys.stderr.write(str(magic_exception))
        if existing_package is not None:
            if existing_package['promoted'] is True:
                raise self.PackageIsPromotedError
            if existing_package['checksum'] != filename:
                new_file_id = self.filestore.put(package_data)
                old_file_id = existing_package['file_id']
                self.filestore.delete(old_file_id)
                response += "Deleted old package with same version number, checksum: " + existing_package['checksum']
                self.packages.update({"name": package_name, "version": package_version}, {
                    "$set": {"checksum": filename, "type": content_type, "promoted": False, "created": time(),
                             "file_id": new_file_id}})
            else:
                response += "Package version already uploaded. No action taken.\n"
        else:
            new_file_id = self.filestore.put(package_data)
            self.packages.insert(
                {"name": package_name, "version": package_version, "checksum": filename, "type": content_type,
                 "promoted": False, "created": time(), "file_id": new_file_id})
            response += "Created " + package_name + " " + package_version + " with checksum " + filename + '\n'
        response = response + "Current Versions available:" + '\n'.join(self.list_package_versions(package_name))
        return response

    def update_package_metadata(self, package_name, package_version, new_metadata):
        """Updates the metadata associated with a given package version"""
        new_metadata['name'] = package_name
        new_metadata['version'] = package_version
        if self.packages.find_one({"name": package_name, "version": package_version}):
            self.packages.update({"name": package_name, "version": package_version}, {"$set": new_metadata})
        else:
            self.packages.insert(new_metadata)
        return True

    def set_promotion_flag(self, package_name, package_version, promotion_flag):
        """Sets a given package version's promotion flag. Promoted packages cannot be updated or deleted"""
        package = self.packages.find_one({"name": package_name, "version": package_version})
        if package is not None:
            self.packages.update({"name": package_name, "version": package_version},
                                 {"$set": {"promoted": promotion_flag}})
            return True
        else:
            raise self.PackageInstanceNotFoundError

    def delete_package_version(self, package_name, package_version):
        """Deletes a specific version of a package from the database"""
        package = self.packages.find_one({"name": package_name, "version": package_version})
        if package is not None:
            if package["promoted"]:
                return False
            else:
                self.filestore.delete(package["file_id"])
                self.packages.remove({"name": package_name, "version": package_version})
                return True
        else:
            raise self.PackageNotFoundError

    def retrieve_package_version(self, package_name, package_version):
        """Retrieves the Content-Type and content for a given version of a package"""
        package = self.packages.find_one({"name": package_name, "version": package_version})
        if package_version == 'latest':
            raise self.PackageInstanceNotFoundError
        if package is not None:
            return package['type'], self.filestore.get(package['file_id']).read()
        else:
            raise self.PackageInstanceNotFoundError

    def retrieve_package_details(self, package_name, package_version):
        """Retrieves metadata for a given version of a package, in JSON form"""
        package = self.packages.find_one({"name": package_name, "version": package_version})
        if package is not None:
            del package['name']
            del package['version']
            del package['file_id']  # Don't expose internal data
            del package['_id']
            return json.dumps(package)
        else:
            raise self.PackageInstanceNotFoundError

    def retrieve_configuration(self, instance_name):
        instance = self.environments.find_one({"name": instance_name})
        if instance is not None:
            if "globalConfiguration" in instance:
                for key in instance['globalConfiguration']['deploymentDictionary'].keys():
                    if '%2E' in key:  # Because BSON doesn't allow periods in key names, they're encoded to %2E
                        new_key_name = key.replace('%2E', '.')
                        instance['globalConfiguration']['deploymentDictionary'][new_key_name] = \
                            instance['globalConfiguration']['deploymentDictionary'].pop(key)
                return json.dumps(instance["globalConfiguration"], sort_keys=True, indent=2,
                                  separators=(',', ': '))
            else:
                raise self.EnvironmentNotFoundError
        else:
            raise self.EnvironmentNotFoundError

    def update_configuration(self, instance_name, content_type, payload, username):
        """Stores an environment configuration (JSON string). In the event it already
        existed, store a copy of the old configuration in the object's history along
        with who changed it."""
        new_record = {}
        if content_type == "application/json":
            try:
                configuration_data = json.loads(payload)
            except ValueError:
                raise self.ConfigurationNotValidJSONError
            if 'deploymentDictionary' in configuration_data:
                for key in configuration_data['deploymentDictionary'].keys():
                    if '.' in key:  # Because BSON doesn't allow periods in key names, they're encoded to %2E
                        new_key_name = key.replace('.', '%2E')
                        configuration_data['deploymentDictionary'][new_key_name] = \
                            configuration_data['deploymentDictionary'].pop(key)
            environment = self.environments.find_one({'name': instance_name})
            if environment is not None:
                self.history.insert({"datestamp": int(time()), "objectType": "environment", "content": environment,
                                     "serviceInstance": instance_name, "userName": username})
                host_overrides = environment["hostOverrides"]
                old_environment_id = environment["_id"]
                new_record["hostOverrides"] = host_overrides
                new_record["name"] = instance_name
                new_record["globalConfiguration"] = configuration_data
                self.environments.insert(new_record)
                self.environments.remove(old_environment_id)
            else:
                new_record["hostOverrides"] = {}
                new_record["name"] = instance_name
                new_record["globalConfiguration"] = configuration_data
                self.environments.insert(new_record)
            return True
        else:
            raise self.ConfigurationNotJSONError

    def delete_configuration(self, instance_name):
        """Deletes an enviroment configuration"""
        environment = self.environments.find_one({'name': instance_name})
        if environment is not None:
            self.environments.remove({'name': instance_name})
            return "Deleted Environment " + instance_name
        else:
            return "Environment does not exist - no action taken"

    def retrieve_node_configuration(self, instance_name, node_name):
        """Retrieves a set of node-specific overrides for an environment configuration"""
        environment = self.environments.find_one({'name': instance_name})
        if environment is not None:
            if node_name in environment["hostOverrides"]:
                return json.dumps(environment["hostOverrides"][node_name],
                                  sort_keys=True, indent=2, separators=(',', ': '))
            else:
                return {}  # For valid environments, we want to return an empty dictionary unless we know better
        else:
            raise self.EnvironmentNotFoundError

    def create_node_configuration(self, instance_name, node_name, content_type, payload):
        """Creates a set of node-specific overrides for an environment configuration,
        supplied as a JSON string"""
        if content_type == "application/json":
            try:
                configuration_data = json.loads(payload)
            except ValueError:
                raise self.ConfigurationNotValidJSONError
            for key in configuration_data.keys():
                if '.' in key:  # Because BSON doesn't allow periods in key names, they're encoded to %2E
                    new_key_name = key.replace('.', '%2E')
                    configuration_data[new_key_name] = configuration_data.pop(key)
            environment = self.environments.find_one({'name': instance_name})
            if environment is not None:
                environment["hostOverrides"][node_name] = configuration_data
                self.environments.update({"name": instance_name},
                                         {"$set": {"hostOverrides": environment["hostOverrides"]}})
                return True
            else:
                return self.EnvironmentNotFoundError
        else:
            raise self.ConfigurationNotJSONError

    def delete_node_configuration(self, instance_name, node_name):
        """Deletes a set of node-specific overrides for an environment configuration"""
        environment = self.environments.find_one({'name': instance_name})
        if environment is not None:
            if node_name in environment["hostOverrides"]:
                del environment["hostOverrides"][node_name]
                self.environments.update({"name": instance_name},
                                         {"$set": {"hostOverrides": environment["hostOverrides"]}})
                return True
        else:
            raise self.EnvironmentNotFoundError

    def service_instance_configuration_history(self, instance_name):
        configuration_history = []
        for version in self.history.find({"serviceInstance": instance_name}):
            if "userName" in version:
                configuration_history.append({"datestamp": version["datestamp"], "username": version["userName"]})
            else:
                configuration_history.append({"datestamp": version["datestamp"], "username": "N/A"})
        return configuration_history

    def service_instance_historic_version(self, instance_name, version):
        historic_config = self.history.find_one(
            {'serviceInstance': instance_name, "datestamp": int(version), "objectType": "environment"})
        if historic_config is not None:
            if "deploymentDictionary" in historic_config['content']['globalConfiguration'].keys():
                for key in historic_config['content']['globalConfiguration']['deploymentDictionary'].keys():
                    if '%2E' in key:  # Because BSON doesn't allow periods in key names, they're encoded to %2E
                        new_key_name = key.replace('%2E', '.')
                        historic_config['content']['globalConfiguration']['deploymentDictionary'][new_key_name] = \
                            historic_config['content']['globalConfiguration']['deploymentDictionary'].pop(key)
            return historic_config
        else:
            raise self.EnvironmentNotFoundError

    def delete_historic_version(self, instance_name, version):
        """Delete an instance configuration from the history table. This might be useful if
        sensitive data were accidentally included in a change and it needs deleting."""
        self.history.remove({'serviceInstance': instance_name, "datestamp": int(version), "objectType": "environment"})
        return True

    def store_bootstrap(self, bootstrap_name, content_type, bootstrap_data):
        existing_bootstrap = self.bootstraps.find_one({"platform": bootstrap_name})
        if content_type == '':
            content_type = magic.from_buffer(bootstrap_data, mime=True)
        if existing_bootstrap is not None:
            self.bootstraps.remove({"platform": bootstrap_name})
        self.bootstraps.insert({"platform": bootstrap_name, "type": content_type, "script": bootstrap_data})
        return True

    def retrieve_bootstrap(self, bootstrap_name):
        bootstrap = self.bootstraps.find_one({"platform": bootstrap_name})
        if bootstrap is not None:
            return bootstrap["script"], bootstrap["type"]
        else:
            raise self.BootStrapNotFoundError

    def delete_bootstrap(self, bootstrap_name):
        bootstrap = self.bootstraps.find_one({"platform": bootstrap_name})
        if bootstrap is not None:
            self.bootstraps.remove({"platform": bootstrap_name})
        else:
            raise self.BootStrapNotFoundError

    def get_installer_type(self, instance_name):
        """Returns the deployment tyoe for a given environment definition"""
        instance = self.environments.find_one({'name': instance_name})
        if instance is not None:
            return instance["globalConfiguration"]["deploymentType"]
        else:
            raise self.EnvironmentNotFoundError

    def list_installer_instances(self, installer_name):
        installer_instances = []
        for installer in self.installers.find({'name': installer_name}):
            installer_instances.append(installer['platform'])
        if installer_instances == []:
            raise self.InstallerNotFoundError
        else:
            return installer_instances

    def create_installer(self, installer_name):
        # Present for compatibility
        return True

    def retrieve_installer_instance(self, installer_name, target_os):
        installer_props = self.installers.find_one({'name': installer_name, 'platform': target_os})
        if installer_props is not None:
            return installer_props['type'], self.filestore.get(installer_props['file_id']).read()
        else:
            raise self.InstallerInstanceNotFoundError

    def update_installer_specific(self, installer_name, target_os, content_type, installer_data):
        new_file_id = self.filestore.put(installer_data)
        existing_installer = self.installers.find_one({'name': installer_name, 'platform': target_os})
        if content_type == '':
            content_type = magic.from_buffer(installer_data, mime=True)
        checksum = hashlib.sha1(installer_data).hexdigest()
        installer_object = {'name': installer_name, 'platform': target_os, 'file_id': new_file_id,
                            'type': content_type, 'checksum': checksum}

        if existing_installer is None:
            self.installers.insert(installer_object)
        else:
            old_file_id = existing_installer['file_id']
            self.installers.remove({'name': installer_name, 'platform': target_os})
            self.installers.insert(installer_object)
            self.filestore.delete(old_file_id)
        return True

    def delete_installer_specific(self, installer_name, target_os):
        installer = self.installers.find_one({'name': installer_name, "platform": target_os})
        if installer is not None:
            self.installers.remove({'name': installer_name, "platform": target_os})
            # Delete it
            return True
        else:
            if self.installers.find_one({'name': installer_name}) is not None:
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

    class PackageIsPromotedError(Exception):
        """Package is promoted and cannot be overwritten by an import"""
