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
devnull = open('/dev/null', 'w')
package_modified = False
templatedFiles = []

suffix_blacklist = ['ar', 'class', 'jks', 'pfx', 'ser']

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
                    exit(1)

if not flattened_dictionary:
    # TODO: list the dictionary tokens that are still outstanding.
    print('FATAL: Could not flatten dictionary in 10 iterations')
    exit(1)

for dictionary_key in configuration_data['deploymentDictionary']:
    if dictionary_key.endswith('.password'):
        try:
            configuration_data['deploymentDictionary'][dictionary_key] = base64.b64decode(
                configuration_data['deploymentDictionary'][dictionary_key])
        except TypeError:
            print('FATAL: ' + dictionary_key + ' cannot be decoded.')
            exit(1)

if 'serviceName' not in configuration_data:
    print('FATAL: serviceName attribute not defined')
    exit(1)

if 'jarName' not in configuration_data:
    print('FATAL: Jar Name not defined')
    exit(1)

if 'instanceProperties' not in configuration_data:
    print('FATAL: Instance Properties not specified')
    exit(1)

if 'serviceUser' not in configuration_data:
    configuration_data['serviceUser'] = configuration_data['serviceName']

startServiceCommand = ['/sbin/service', configuration_data['serviceName'], 'start']
stopServiceCommand = ['/sbin/service', configuration_data['serviceName'], 'stop']

if 'serviceInstance' in configuration_data:
    startServiceCommand.append(configuration_data['serviceInstance'])
    stopServiceCommand.append(configuration_data['serviceInstance'])
    configuration_data['targetDirectory'] += '/' + configuration_data['serviceInstance']

instanceProperties = subprocess.Popen(['curl', '-k', '-s', configuration_data['instanceProperties']],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

instancePropertiesText = instanceProperties.communicate()[0]
if instanceProperties.returncode != 0:
    print("FATAL: Couldn't fetch " + configuration_data['instanceProperties'])
    exit(1)
instancePropertiesFileHandle = open('./instance.properties', 'w')
instancePropertiesFileHandle.write(instancePropertiesText)
instancePropertiesFileHandle.close()

# Delete any aborted previous installation
if os.path.isdir(configuration_data['targetDirectory'] + '.new'):
    print('Deleted old working directory at ' + configuration_data['targetDirectory'] + '.new')
    shutil.rmtree(configuration_data['targetDirectory'] + '.new')

try:
    os.mkdir('./explodedJar')
    packageZip = zipfile.ZipFile('./packagefile', 'r')
    packageZip.extractall('./explodedJar')
    packageZip.close()
except zipfile.BadZipfile:
    print('FATAL: Package supplied does not appear to be a Zip archive.')
    exit(1)

packageFiles = []
for dirPath, dirName, fileNames in os.walk('./explodedJar'):
    for fileName in fileNames:
        blacklisted = False
        for suffix in suffix_blacklist:
            if fileName.endswith(suffix):
                blacklisted = True
        if blacklisted is False:
            packageFiles.append(dirPath + '/' + fileName)
        elif debugging_enabled is True:
            print('DEBUG: Blackisted suffix. Not scanning placeholders in file: ' + dirPath + '/' + fileName)

foundTokens = []

templatedFiles.append('./instance.properties')

for templatedFile in packageFiles:
    if debugging_enabled is True:
        print('DEBUG: Checking ' + templatedFile + ' for templated values:')
    fileContents = open(templatedFile, 'r').read()
    token_list = []
    for token in fileContents.split('}}'):
        if token.find('{{') >= 0:
            token_list.append(token.partition('{{')[2])
            templatedFiles.append(templatedFile)
            if debugging_enabled is True:
                print('DEBUG:     Found templated value: ' + token.partition('{{')[2])

    foundTokens = foundTokens + token_list

templatedFiles = list(set(templatedFiles))  # remove duplicate entreies

foundTokens = (list(set(foundTokens)))  # Remove duplicates
if '' in foundTokens:
    foundTokens.remove('')  # remove the empty token, if present

foundTokensCopy = list(foundTokens)  # Don't manipulate a data structure while you're iterating over it...

for token in foundTokensCopy:
    if token in configuration_data['deploymentDictionary']:
        foundTokens.remove(token)

if foundTokens:
    print('The following tokens could not be expanded: ', end='')
    for token in foundTokens:
        print(token + ', ', end='')
    print('')
    exit(1)
# If we get this far, we've been able to flatten the dictionary, and ensure that all tokens can be expanded.
# We can go ahead and install.


# Create the YUM repo

if 'yumRepositoryPath' in configuration_data and 'RepositoryURL' in configuration_data:
    yum_repo_definition = '[expedia-delite]\nname=expedia-delite\nbaseurl=' + configuration_data[
        'RepositoryURL'] + configuration_data['yumRepositoryPath'] + '\nenabled=1\npriority=1\ngpgcheck=0\n'
    if os.path.exists('/etc/yum.repos.d/expedia.repo'):
        if debugging_enabled is True:
            print('DEBUG: Removing legacy yum repository /etc/yum.repos.d/expedia.repo')
        os.remove('/etc/yum.repos.d/expedia.repo')
    if debugging_enabled is True:
        print('DEBUG: Updating Yum Repository config with contents: \n' + yum_repo_definition)
    repofile = open('/etc/yum.repos.d/delite.repo', 'w')
    repofile.write(yum_repo_definition)
    repofile.close()
    if subprocess.call(['yum', 'clean', 'all'], stdout=devnull, stderr=devnull) != 0:
        print('DEBUG: Failed to clean yum caches')
        exit(1)
    else:
        if debugging_enabled is True:
            print('DEBUG: Successfully cleared yum caches')

# Install Java
if 'javaVersion' in configuration_data['deploymentDictionary'] and \
                'yumRepositoryPath' in configuration_data and 'RepositoryURL' in configuration_data:
    print('Checking for Java version ' + configuration_data['deploymentDictionary']['javaVersion'] + ': ', end='')
    rpmList = subprocess.Popen(['rpm', '-qa'], stdout=subprocess.PIPE).communicate()[0]
    if rpmList.find(configuration_data['deploymentDictionary']['javaVersion']) < 0:
        print('Not Found. Installing it... ', end='')
        exitCode = subprocess.call(['rpm', '-i', configuration_data['RepositoryURL'] + configuration_data[
            'yumRepositoryPath'] + '/jdk-' + configuration_data['deploymentDictionary']['javaVersion'] +
                                    '-fcs.x86_64.rpm', '--oldpackage', '--relocate',
                                    '/etc/init.d/jexec=/etc/init.d/jexec-' +
                                    configuration_data['deploymentDictionary']['javaVersion'], '--badreloc'],
                                   stdout=devnull, stderr=devnull)
        if exitCode == 0:
            print('OK')
        else:
            print('Failed')
            exit(1)
        for CACert in ['ExpediaRootCA', 'ExpediaInternal1C', 'ExpediaRoot2015', 'ExpediaInternal1C2015']:
            print('Adding ' + CACert + ' certificate to trust store: ', end='')
            certRequest = subprocess.Popen(
                ['curl', '-k', '-s', configuration_data['RepositoryURL'] + configuration_data[
                    'certificatePath'] + '/' + CACert + '.crt'], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            certResponseBody = certRequest.communicate()[0]
            if certRequest.returncode != 0:
                print('FAILED. Could not fetch certificate at ' + configuration_data['RepositoryURL'] +
                      configuration_data['certificatePath'] + '/' + CACert + '.crt')
                print('curl return code was: ' + str(certRequest.returncode))
                print('curl errors follow: ')
                print(certRequest.communicate()[1])
                exit(1)
            certificateFileHandle = open('./' + CACert + '.crt', 'w')
            certificateFileHandle.write(certResponseBody)
            certificateFileHandle.close()
            if subprocess.call(['/usr/java/jdk' + configuration_data['deploymentDictionary']['javaVersion'] +
                                '/bin/keytool', '-import', '-keystore', '/usr/java/jdk' +
                                configuration_data['deploymentDictionary']['javaVersion'] +
                                '/jre/lib/security/cacerts', '-storepass', 'changeit', '-noprompt', '-file',
                                './' + CACert + '.crt', '-alias', CACert], stdout=devnull, stderr=devnull) != 0:
                print('FAILED')
                exit(1)
            print('OK')
    else:
        print('Found.')

# Install RPM dependencies

for rpmName in configuration_data['packagesRequired']:
    if subprocess.call(['rpm', '-q', rpmName], stdout=devnull, stderr=devnull) != 0:
        yum_action = 'install'
    else:
        yum_action = 'upgrade'
    print('Updating RPM: ' + rpmName)
    if subprocess.call(['yum', '-y', yum_action, rpmName], stdout=devnull, stderr=devnull) != 0:
        print('Failed to ' + yum_action + ' ' + rpmName)
        exit(1)

# Clean up unwanted cron entry

if os.path.exists('/etc/cron.d/update_pdnsd.cron'):
    if debugging_enabled is True:
        print('DEBUG: removing legacy cron entry /etc/cron.d/update_pdnsd.cron')
    os.remove('/etc/cron.d/update_pdnsd.cron')
# Create SSL Certificates

if 'certificatePath' in configuration_data and 'certificateName' in configuration_data and \
                'certificatePassPhrase' in configuration_data:
    print('Updating certificate: ' + configuration_data['certificateName'] + ' ', end='')
    decodedPassPhrase = ''
    try:
        decodedPassPhrase = base64.b64decode(configuration_data['certificatePassPhrase'])
    except TypeError:
        print('FATAL: Passphrase cannot be decoded.')
        exit(1)
    certRequest = subprocess.Popen(['curl', '-k', '-s', '--user', configuration_data['certificateName'] + ':' +
                                    decodedPassPhrase,
                                    configuration_data['RepositoryURL'] + configuration_data['certificatePath'] + '/' +
                                    configuration_data['certificateName']], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    certificateContents = certRequest.communicate()[0]
    if certRequest.returncode != 0:
        print('FAILED. Could not fetch certificate at ' + configuration_data['RepositoryURL'] +
              configuration_data['certificatePath'] + '/' + configuration_data['certificateName'])
        print('curl return code was: ' + str(certRequest.returncode))
        print('curl errors follow:')
        print(certRequest.communicate()[1])
        exit(1)
    if not os.path.isdir('/opt/expedia/security'):
        if os.path.exists('/opt/expedia/security'):
            print('FATAL: /opt/expedia/security exists and is not a directory')
            exit(1)
        else:
            os.mkdir('/opt/expedia/security')
    certificateFileHandle = open('/opt/expedia/security/' + configuration_data['certificateName'], 'w')
    certificateFileHandle.write(certificateContents)
    certificateFileHandle.close()
    print('OK')

for templatedfileName in templatedFiles:
    if debugging_enabled is True:
        print('DEBUG: Replacing templated values in ' + templatedfileName)
    template = open(templatedfileName, 'r')
    outputData = template.read()
    template.close()
    for dictionary_key in configuration_data['deploymentDictionary']:
        outputData = outputData.replace('{{' + dictionary_key + '}}',
                                        configuration_data['deploymentDictionary'][dictionary_key])
    os.rename(templatedfileName, templatedfileName + '~')
    outputFile = open(templatedfileName, 'w')
    outputFile.write(outputData)
    outputFile.close()
    os.remove(templatedfileName + '~')
    if templatedfileName.endswith('password'):
        os.chmod(templatedfileName, 0500)  # If the file contains passwords, it shouldn't be generally readable
    if templatedfileName is not './instance.properties':
        package_modified = True

os.mkdir(configuration_data['targetDirectory'] + '.new')
os.mkdir(configuration_data['targetDirectory'] + '.new' + '/etc')
os.mkdir(configuration_data['targetDirectory'] + '.new' + '/bin')
os.mkdir(configuration_data['targetDirectory'] + '.new' + '/temp')
if not os.path.isdir(configuration_data['targetDirectory'] + '.bak' + '/logs'):
    os.mkdir(configuration_data['targetDirectory'] + '.new' + '/logs')
shutil.move('./instance.properties', configuration_data['targetDirectory'] + '.new' + '/etc/instance.properties')

if package_modified is True:
    if debugging_enabled is True:
        print('DEBUG: creating new jar file as the original artifact contained templated files')
    os.chdir('explodedJar')
    targetJar = zipfile.ZipFile(
        configuration_data['targetDirectory'] + '.new' + '/bin/' + configuration_data['jarName'], 'w')
    for dirname, subdirs, files in os.walk('./'):
        targetJar.write(dirname)
        for fileName in files:
            targetJar.write(os.path.join(dirname, fileName))
    targetJar.close()
else:
    if debugging_enabled is True:
        print('DEBUG: Using original deployment artifact as no templated files were detected')
    shutil.move('./packagefile',
                configuration_data['targetDirectory'] + '.new' + '/bin/' + configuration_data['jarName'])

if subprocess.call(['chown', '-R', configuration_data['serviceUser'] + ':',
                    configuration_data['targetDirectory'] + '.new']) != 0:
    print("FATAL: Couldn't change ownership of target directory " + configuration_data['targetDirectory'])
    exit(1)

# if we've got this far, then we're ready to shut down and restart with the new version
if 'serviceName' in configuration_data:
    print('Stopping ' + configuration_data['serviceName'] + ' ', end='')
    if 'serviceInstance' in configuration_data:
        print('instance ' + configuration_data['serviceInstance'], end='')
    if subprocess.call(stopServiceCommand, stdout=devnull, stderr=devnull) != 0:
        print(': FAILED')
        exit(1)
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
    os.rename(configuration_data['targetDirectory'] + '.bak' + '/logs', configuration_data['targetDirectory'] + '/logs')

if 'serviceName' in configuration_data:
    print('Starting ' + configuration_data['serviceName'] + ' ', end='')
    if 'serviceInstance' in configuration_data:
        print('instance ' + configuration_data['serviceInstance'], end='')
    if subprocess.call(startServiceCommand, stdout=devnull, stderr=devnull) != 0:
        print(': FAILED')
        exit(1)
    print(': OK')

# Clean up old version
if os.path.isdir(configuration_data['targetDirectory'] + '.bak'):
    shutil.rmtree(configuration_data['targetDirectory'] + '.bak')
