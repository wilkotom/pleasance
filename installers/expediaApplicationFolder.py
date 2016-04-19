#!/usr/bin/env python
from __future__ import print_function

import zipfile
import json
import subprocess
import base64
import os
import shutil
import sys
import pwd
from tempfile import TemporaryFile

reload(sys)
sys.setdefaultencoding('utf8')

application_package = './packagefile'
configuration_file = './environmentSetup'
debugging_enabled = False
external_command_output = open('/dev/null', 'w')

suffix_blacklist = ['ar', 'class', 'jks', 'pfx', 'ser', 'zip', 'cacerts']


def exit_script(exit_code):
    # We wrap the exit code so that we can dump the output of any failing command if debugging is enabled.
    if debugging_enabled is True:
        external_command_output.seek(0)
        print("Command output was:")
        print(external_command_output.read())
    exit(exit_code)


configuration_data = json.load(open(configuration_file))
if 'debug' in configuration_data:
    if configuration_data['debug'] is True:
        debugging_enabled = True
        external_command_output.close()
        external_command_output = TemporaryFile()
    elif not isinstance(configuration_data['debug'], bool):
        print('WARNING: debug flag is not boolean. Assuming debug flag is set to false')

# Flatten the dictionary
loop_counter = 0
flattened_dictionary = False

for dictionary_key in configuration_data['deploymentDictionary']:
    if dictionary_key.endswith('.password'):
        try:
            configuration_data['deploymentDictionary'][dictionary_key] = base64.b64decode(
                configuration_data['deploymentDictionary'][dictionary_key])
        except TypeError:
            print('FATAL: ' + dictionary_key + ' cannot be decoded.')
            exit(1)
    # Replace double backslashes with single ones
    if "\\\\" in configuration_data['deploymentDictionary'][dictionary_key]:
        configuration_data['deploymentDictionary'][dictionary_key] = configuration_data['deploymentDictionary'][
            dictionary_key].replace('\\\\', '\\')


while loop_counter < 10 and not flattened_dictionary:
    dictionary_contents = ''
    loop_counter += 1
    for dictionary_key in configuration_data['deploymentDictionary']:
        dictionary_contents += configuration_data['deploymentDictionary'][dictionary_key]
    if dictionary_contents.find('}}') < 0:
        flattened_dictionary = True
    for dictionary_key in configuration_data['deploymentDictionary']:
        for raw_token in configuration_data['deploymentDictionary'][dictionary_key].split('}}'):
            token_list = []
            if raw_token.find('{{') >= 0:
                token_list.append(raw_token.partition('{{')[2])
            if '' in token_list:
                token_list.remove('')
            for token in token_list:
                if token in configuration_data['deploymentDictionary']:
                    configuration_data['deploymentDictionary'][dictionary_key] = configuration_data[
                        'deploymentDictionary'][dictionary_key].replace('{{' + token + '}}',
                                                                        configuration_data['deploymentDictionary'][
                                                                            token])
                else:
                    print('FATAL: Undefined Dictionary key ' + token)
                    exit_script(1)

if not flattened_dictionary:
    # TODO: list the dictionary tokens that are still outstanding.
    print('FATAL: Could not flatten dictionary in 10 iterations')
    exit(1)


if 'serviceName' not in configuration_data:
    print('Warning: No service name defined.')
else:
    service_start_command = ['/sbin/service', configuration_data['serviceName'], 'start']
    service_stop_command = ['/sbin/service', configuration_data['serviceName'], 'stop']
    if 'serviceInstance' in configuration_data:
        service_start_command.append(configuration_data['serviceInstance'])
        service_stop_command.append(configuration_data['serviceInstance'])
        configuration_data['targetDirectory'] += '/' + configuration_data['serviceInstance']

if 'serviceUser' not in configuration_data:
    if 'serviceName' not in configuration_data:
        print('FATAL: serviceUser attribute not defined')
        exit(1)
    else:
        configuration_data['serviceUser'] = configuration_data['serviceName']


# Delete any aborted previous installation
if os.path.isdir(configuration_data['targetDirectory'] + '.new'):
    print('Deleted old working directory at ' + configuration_data['targetDirectory'] + '.new')
    shutil.rmtree(configuration_data['targetDirectory'] + '.new')

os.makedirs(configuration_data['targetDirectory'] + '.new', 0755)
print('Created ' + configuration_data['targetDirectory'] + '.new')

try:
    package_extraction = zipfile.ZipFile(application_package, 'r')
    package_extraction.extractall(configuration_data['targetDirectory'] + '.new')
    package_extraction.close()
except zipfile.BadZipfile:
    print('FATAL: Package supplied does not appear to be a Zip archive.')
    exit(1)

packaged_files = []

for dir_path, dir_name, file_names in os.walk(configuration_data['targetDirectory'] + '.new'):
    for filename in file_names:
        blacklisted_filename = False
        for suffix in suffix_blacklist:
            if filename.endswith(suffix):
                blacklisted_filename = True
        if blacklisted_filename is False:
            packaged_files.append(dir_path + '/' + filename)
        elif debugging_enabled is True:
            print('DEBUG: Blackisted suffix. Not scanning placeholders in file: ' + dir_path + '/' + filename)


found_tokens = []
templated_files = []

for packaged_file in packaged_files:
    if debugging_enabled is True:
        print("Searching for templated values in " + packaged_file)
    file_contents = open(packaged_file, 'r').read()
    token_list = []
    for token in file_contents.split('}}'):
        if token.find('{{') >= 0:
            if debugging_enabled is True:
                print("  Found templated value: " + token.partition('{{')[2])
            token_list.append(token.partition('{{')[2])
            templated_files.append(packaged_file)
    found_tokens = found_tokens + token_list
    if packaged_file.endswith('password'):
        os.chmod(packaged_file, 0500)  # If the file contains passwords, it shouldn't be generally readable

found_tokens = list(set(found_tokens))  # Remove duplicates
templated_files = list(set(templated_files))

if '' in found_tokens:
    found_tokens.remove('')  # remove the empty token, if present

found_tokens_copy = list(found_tokens)  # Don't manipulate a data structure while you're iterating over it...

for token in found_tokens_copy:
    if token in configuration_data['deploymentDictionary']:
        found_tokens.remove(token)

if found_tokens:
    print('The following tokens could not be expanded: ', end='')
    for token in found_tokens:
        print(token + ', ', end='')
    print('')
    exit(1)
# If we get this far, we've been able to flatten the dictionary, and ensure that all tokens can be expanded.
# We can go ahead and install.


# Create the YUM repo

if 'yumRepositoryPath' in configuration_data and 'RepositoryURL' in configuration_data:
    if os.path.exists('/etc/yum.repos.d/expedia.repo'):
        print('Removing legacy yum repository /etc/yum.repos.d/expedia.repo')
        os.remove('/etc/yum.repos.d/expedia.repo')
    print('Updating Yum Repository config...')
    repofile = open('/etc/yum.repos.d/delite.repo', 'w')
    repofile.write('[expedia-pleasance]\nname=expedia-pleasance\nbaseurl=' + configuration_data[
        'RepositoryURL'] + configuration_data['yumRepositoryPath'] + '\nenabled=1\npriority=1\ngpgcheck=0\n')
    repofile.close()
    if subprocess.call(['yum', 'clean', 'all'], stdout=external_command_output, stderr=external_command_output) != 0:
        print('Failed to clean yum caches')
        exit_script(1)

# Install Java
if 'javaVersion' in configuration_data['deploymentDictionary'] and \
        'yumRepositoryPath' in configuration_data and 'RepositoryURL' in configuration_data:
    print('Checking for Java version ' + configuration_data['deploymentDictionary']['javaVersion'] + ': ', end='')
    rpm_list = subprocess.Popen(['rpm', '-qa'], stdout=subprocess.PIPE).communicate()[0]
    if rpm_list.find(configuration_data['deploymentDictionary']['javaVersion']) < 0:
        print('Not Found. Installing it... ', end='')
        exit_code = subprocess.call(['rpm', '-i', configuration_data['RepositoryURL'] + configuration_data[
            'yumRepositoryPath'] + '/jdk-' + configuration_data['deploymentDictionary']['javaVersion'] +
            '-fcs.x86_64.rpm', '--oldpackage', '--relocate',
            '/etc/init.d/jexec=/etc/init.d/jexec-' + configuration_data['deploymentDictionary'][
            'javaVersion'], '--badreloc'], stdout=external_command_output, stderr=external_command_output)
        if exit_code == 0:
            if debugging_enabled is True:
                external_command_output.seek(0)
                print('Yum output as follows:')
                print (external_command_output.read())
                external_command_output.truncate(0)
            print('OK')
        else:
            print('Failed')
            exit_script(1)
        for CACert in ['ExpediaRootCA', 'ExpediaInternal1C']:
            print('Adding ' + CACert + ' certificate to trust store: ', end='')
            certificate_fetch = subprocess.Popen(
                    ['curl', '-k', '-s', configuration_data['RepositoryURL'] + configuration_data[
                        'certificatePath'] + '/' + CACert + '.crt'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            certResponseBody = certificate_fetch.communicate()[0]
            if certificate_fetch.returncode != 0:
                print('FAILED. Could not fetch certificate at ' + configuration_data['RepositoryURL'] +
                      configuration_data['certificatePath'] + '/' + CACert + '.crt')
                print('curl return code was: ' + str(certificate_fetch.returncode))
                print('curl errors follow: ')
                print(certificate_fetch.communicate()[1])
                exit_script(1)
            print('OK')
            if debugging_enabled is True:
                external_command_output.seek(0)
                print('curl output as follows:')
                print(external_command_output.read())
                external_command_output.truncate(0)
            certificate_file = open('./' + CACert + '.crt', 'w')
            certificate_file.write(certResponseBody)
            certificate_file.close()
            if subprocess.call(['/usr/java/jdk' + configuration_data['deploymentDictionary']['javaVersion'] +
                                        '/bin/keytool', '-import', '-keystore', '/usr/java/jdk' +
                                        configuration_data['deploymentDictionary']['javaVersion'] +
                                        '/jre/lib/security/cacerts', '-storepass', 'changeit', '-noprompt', '-file',
                                './' + CACert + '.crt', '-alias', CACert], stdout=external_command_output,
                               stderr=external_command_output) != 0:
                print('FAILED')
                exit_script(1)
            print('OK')
            if debugging_enabled is True:
                print("Successfully imported " + CACert + " into Java certificate store")

    else:
        print('Found.')

# Install Tomcat
if 'tomcatVersion' in configuration_data['deploymentDictionary'] and \
        'yumRepositoryPath' in configuration_data and 'RepositoryURL' in configuration_data:
    print('Checking for Tomcat version ' + configuration_data['deploymentDictionary']['tomcatVersion'] + ': ', end='')
    if subprocess.call(
            ['rpm', '-q', 'tomcat-deployit' + '-' + configuration_data['deploymentDictionary']['tomcatVersion']],
            stdout=external_command_output, stderr=external_command_output) != 0:
        print('Not found. Installing it. ', end='')
        if subprocess.call(['yum', '-yq', 'install',
                            'tomcat-deployit' + '-' + configuration_data['deploymentDictionary']['tomcatVersion']],
                           stdout=external_command_output, stderr=external_command_output) != 0:
            print('FAILED')
            exit_script(1)
        else:
            print('OK')
            if debugging_enabled is True:
                print("Tomcat packages installed via yum:")
                external_command_output.seek(0)
                print(external_command_output.read())
                external_command_output.truncate(0)
    else:
        print('Found')

# Install RPM dependencies

for rpm_name in configuration_data['packagesRequired']:
    if subprocess.call(['rpm', '-q', rpm_name], stdout=external_command_output, stderr=external_command_output) != 0:
        print('Installing RPM: ' + rpm_name)
        if subprocess.call(['yum', '-y', 'install', rpm_name], stdout=external_command_output,
                           stderr=external_command_output) != 0:
            print('Failed to install ' + rpm_name)
            exit_script(1)
        if debugging_enabled is True:
            print("Yum installed " + rpm_name + ":")
            external_command_output.seek(0)
            print(external_command_output.read())
            external_command_output.truncate(0)
    else:
        print('Upgrading RPM: ' + rpm_name)
        if subprocess.call(['yum', '-y', 'upgrade', rpm_name], stdout=external_command_output,
                           stderr=external_command_output) != 0:
            print('Yum call to upgrade ' + rpm_name + ' Failed')
            exit_script(1)
        if debugging_enabled is True:
            print("Yum installed " + rpm_name + ":")
            external_command_output.seek(0)
            print(external_command_output.read())
            external_command_output.truncate(0)

# Clean up unwanted cron entry

if os.path.exists('/etc/cron.d/update_pdnsd.cron'):
    os.remove('/etc/cron.d/update_pdnsd.cron')
# Create SSL Certificates

if 'certificatePath' in configuration_data and \
        'certificateName' in configuration_data and 'certificatePassPhrase' in configuration_data:
    print('Updating certificate: ' + configuration_data['certificateName'] + ' ', end='')
    decodedPassPhrase = ''
    try:
        decodedPassPhrase = base64.b64decode(configuration_data['certificatePassPhrase'])
    except TypeError:
        print('FATAL: Passphrase cannot be decoded.')
        exit_script(1)
    certificate_fetch = subprocess.Popen(['curl', '-k', '-s', '--user', configuration_data['certificateName'] + ':' +
                                    decodedPassPhrase,
                                    configuration_data['RepositoryURL'] + configuration_data['certificatePath'] + '/' +
                                    configuration_data['certificateName']], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    certificate_data = certificate_fetch.communicate()[0]
    if certificate_fetch.returncode != 0:
        print('FAILED. Could not fetch certificate at ' + configuration_data['RepositoryURL'] +
              configuration_data['certificatePath'] + '/' + configuration_data['certificateName'])
        print('curl return code was: ' + str(certificate_fetch.returncode))
        print('curl errors follow:')
        print(certificate_fetch.communicate()[1])
        exit_script(1)
    if not os.path.isdir('/opt/expedia/security'):
        if os.path.exists('/opt/expedia/security'):
            print('FATAL: /opt/expedia/security exists and is not a directory')
            exit_script(1)
        else:
            os.mkdir('/opt/expedia/security')
    certificate_file = open('/opt/expedia/security/' + configuration_data['certificateName'], 'w')
    certificate_file.write(certificate_data)
    certificate_file.close()
    print('OK')

for templated_file_name in templated_files:
    if debugging_enabled is True:
        print("Replacing templated values in " + templated_file_name)
    template = open(templated_file_name, 'r')
    outputData = template.read()
    template.close()
    for dictionary_key in configuration_data['deploymentDictionary']:
        outputData = outputData.replace('{{' + dictionary_key + '}}',
                                        configuration_data['deploymentDictionary'][dictionary_key])
    os.rename(templated_file_name, templated_file_name + '~')
    outputFile = open(templated_file_name, 'w')
    outputFile.write(outputData)
    outputFile.close()
    os.remove(templated_file_name + '~')

if subprocess.call(['chown', '-R', configuration_data['serviceUser'] + ':',
                    configuration_data['targetDirectory'] + '.new']) != 0:
    print("FATAL: Couldn't change ownership of target directory " + configuration_data['targetDirectory'])
    exit_script(1)

# if we've got this far, then we're ready to shut down and restart with the new version
if 'serviceName' in configuration_data:
    print('Stopping ' + configuration_data['serviceName'] + ' ', end='')
    if 'serviceInstance' in configuration_data:
        print('instance ' + configuration_data['serviceInstance'], end='')
    if subprocess.call(service_stop_command, stdout=external_command_output, stderr=external_command_output) != 0:
        print(': FAILED')
        if debugging_enabled is True:
            print("External command output follows:")
            external_command_output.seek(0)
            print(external_command_output.read())
            external_command_output.truncate(0)
        exit_script(1)
    print(': OK')

# Delete old backups, if any
if os.path.isdir(configuration_data['targetDirectory'] + '.bak'):
    print('Deleted old backup at ' + configuration_data['targetDirectory'] + '.bak')
    shutil.rmtree(configuration_data['targetDirectory'] + '.bak')

# Back up existing directory
if os.path.isdir(configuration_data['targetDirectory']):
    os.rename(configuration_data['targetDirectory'], configuration_data['targetDirectory'] + '.bak')

os.rename(configuration_data['targetDirectory'] + '.new', configuration_data['targetDirectory'])

# Retain the logs from the old version, if any
if os.path.isdir(configuration_data['targetDirectory'] + '.bak' + '/logs'):
    #  if there's a log dir in the deployment artifact, delete it in favour of the existing directory
    if os.path.isdir(configuration_data['targetDirectory'] + '/logs'):
        shutil.rmtree(configuration_data['targetDirectory'] + '/logs')
    os.rename(configuration_data['targetDirectory'] + '.bak' + '/logs', configuration_data['targetDirectory'] + '/logs')
elif not os.path.isdir(configuration_data['targetDirectory'] + '/logs'):
    os.mkdir(configuration_data['targetDirectory'] + '/logs', 0755)
    os.chown(configuration_data['targetDirectory'] + '/logs', pwd.getpwnam(configuration_data['serviceUser']).pw_uid,
             pwd.getpwnam(configuration_data['serviceUser']).pw_gid)

if 'serviceName' in configuration_data:
    print('Starting ' + configuration_data['serviceName'] + ' ', end='')
    if 'serviceInstance' in configuration_data:
        print('instance ' + configuration_data['serviceInstance'], end='')
    if subprocess.call(service_start_command, stdout=external_command_output, stderr=external_command_output) != 0:
        print(': FAILED')
        exit_script(1)
    print(': OK')
    if debugging_enabled is True:
        external_command_output.seek(0)
        print(external_command_output.read())
        external_command_output.truncate(0)



# Clean up old version
if os.path.isdir(configuration_data['targetDirectory'] + '.bak'):
    shutil.rmtree(configuration_data['targetDirectory'] + '.bak')

