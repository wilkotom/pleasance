#!/usr/bin/env python
from __future__ import print_function

import zipfile
import json
import subprocess
import base64
import os
import shutil
import sys

reload(sys)
sys.setdefaultencoding('utf8')

packageFile = './packagefile'
configurationFile = './environmentSetup'

configurationData = json.load(open(configurationFile))

devnull = open('/dev/null', 'w')

# Flatten the dictionary
loopCounter = 0
flattenedDictionary = False

while loopCounter < 10 and not flattenedDictionary:
    dictionaryContents = ''
    loopCounter += 1
    for dictionaryKey in configurationData['deploymentDictionary']:
        dictionaryContents += configurationData['deploymentDictionary'][dictionaryKey]
    if dictionaryContents.find('}}') < 0:
        flattenedDictionary = True
    for dictionaryKey in configurationData['deploymentDictionary']:
        for rawToken in configurationData['deploymentDictionary'][dictionaryKey].split('}}'):
            tokenList = []
            if rawToken.find('{{') >= 0:
                tokenList.append(rawToken.partition('{{')[2])
            if '' in tokenList:
                tokenList.remove('')
            for token in tokenList:
                if token in configurationData['deploymentDictionary']:
                    configurationData['deploymentDictionary'][dictionaryKey] = configurationData[
                        'deploymentDictionary'][dictionaryKey].replace('{{' + token + '}}',
                        configurationData['deploymentDictionary'][token])
                else:
                    print('FATAL: Undefined Dictionary key ' + token)
                    exit(1)

if not flattenedDictionary:
    # TODO: list the dictionary tokens that are still outstanding.
    print('FATAL: Could not flatten dictionary in 10 iterations')
    exit(1)

for dictionaryKey in configurationData['deploymentDictionary']:
    if dictionaryKey.endswith('.password'):

        try:
            configurationData['deploymentDictionary'][dictionaryKey] = base64.b64decode(
                configurationData['deploymentDictionary'][dictionaryKey])
        except TypeError:
            print('FATAL: ' + dictionaryKey + ' cannot be decoded.')
            exit(1)


if 'serviceName' not in configurationData:
    print('FATAL: serviceName attribute not defined')
    exit(1)

if 'jarName' not in configurationData:
    print('FATAL: Jar Name not defined')
    exit(1)

if 'instanceProperties' not in configurationData:
    print('FATAL: Instance Properties not specified')
    exit(1)

if 'serviceUser' not in configurationData:
    configurationData['serviceUser'] = configurationData['serviceName']

startServiceCommand = ['/sbin/service', configurationData['serviceName'], 'start']
stopServiceCommand = ['/sbin/service', configurationData['serviceName'], 'stop']

if 'serviceInstance' in configurationData:
    startServiceCommand.append(configurationData['serviceInstance'])
    stopServiceCommand.append(configurationData['serviceInstance'])
    configurationData['targetDirectory'] += '/' + configurationData['serviceInstance']


instanceProperties = subprocess.Popen(['curl', '-k', '-s', configurationData['instanceProperties']],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

instancePropertiesText = instanceProperties.communicate()[0]
if instanceProperties.returncode != 0:
    print("FATAL: Couldn't fetch " + configurationData['instanceProperties'])
    exit(1)
instancePropertiesFileHandle = open('./instance.properties', 'w')
instancePropertiesFileHandle.write(instancePropertiesText)
instancePropertiesFileHandle.close()

# Delete any aborted previous installation
if os.path.isdir(configurationData['targetDirectory'] + '.new'):
    print('Deleted old working directory at ' + configurationData['targetDirectory'] + '.new')
    shutil.rmtree(configurationData['targetDirectory'] + '.new')


try:
    os.mkdir('./explodedJar')
    packageZip = zipfile.ZipFile('./packagefile', 'r')
    packageZip.extractall('./explodedJar')
    packageZip.close()
except zipfile.BadZipfile:
    print('FATAL: Package supplied does not appear to be a Zip archive.')
    exit(1)

templatedFiles = []
for dirPath, dirName, fileNames in os.walk('./explodedJar'):
    for fileName in fileNames:
        if not (fileName.endswith('ar') or fileName.endswith('class') or fileName.endswith('jks') or fileName.endswith(
                'pfx') or fileName.endswith('ser')):
            # No EAR, JAR, WAR or DAR files here thanks!
            # Need to genericise this better.
            templatedFiles.append(dirPath + '/' + fileName)

foundTokens = []

templatedFiles.append('./instance.properties')

for templatedFile in templatedFiles:
    fileContents = open(templatedFile, 'r').read()
    tokenList = []
    for token in fileContents.split('}}'):
        if token.find('{{') >= 0:
            tokenList.append(token.partition('{{')[2])
    foundTokens = foundTokens + tokenList

foundTokens = (list(set(foundTokens)))  # Remove duplicates
if '' in foundTokens:
    foundTokens.remove('')  # remove the empty token, if present

foundTokensCopy = list(foundTokens)  # Don't manipulate a data structure while you're iterating over it...

for token in foundTokensCopy:
    if token in configurationData['deploymentDictionary']:
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

if 'yumRepositoryPath' in configurationData and 'RepositoryURL' in configurationData:
    if os.path.exists('/etc/yum.repos.d/expedia.repo'):
        print('Removing legacy yum repository /etc/yum.repos.d/expedia.repo')
        os.remove('/etc/yum.repos.d/expedia.repo')
    print('Updating Yum Repository config...')
    repofile = open('/etc/yum.repos.d/delite.repo', 'w')
    repofile.write('[expedia-delite]\nname=expedia-delite\nbaseurl=' + configurationData[
        'RepositoryURL'] + configurationData['yumRepositoryPath'] + '\nenabled=1\npriority=1\ngpgcheck=0\n')
    repofile.close()
    if subprocess.call(['yum', 'clean', 'all'], stdout=devnull, stderr=devnull) != 0:
        print('Failed to clean yum caches')
        exit(1)

# Install Java
if 'javaVersion' in configurationData['deploymentDictionary'] and \
        'yumRepositoryPath' in configurationData and 'RepositoryURL' in configurationData:
    print('Checking for Java version ' + configurationData['deploymentDictionary']['javaVersion'] + ': ', end='')
    rpmList = subprocess.Popen(['rpm', '-qa'], stdout=subprocess.PIPE).communicate()[0]
    if rpmList.find(configurationData['deploymentDictionary']['javaVersion']) < 0:
        print('Not Found. Installing it... ', end='')
        exitCode = subprocess.call(['rpm', '-i', configurationData['RepositoryURL'] + configurationData[
            'yumRepositoryPath'] + '/jdk-' + configurationData['deploymentDictionary']['javaVersion'] +
            '-fcs.x86_64.rpm', '--oldpackage', '--relocate', '/etc/init.d/jexec=/etc/init.d/jexec-' +
            configurationData['deploymentDictionary']['javaVersion'], '--badreloc'], stdout=devnull, stderr=devnull)
        if exitCode == 0:
            print('OK')
        else:
            print('Failed')
            exit(1)
        for CACert in ['ExpediaRootCA', 'ExpediaInternal1C']:
            print('Adding ' + CACert + ' certificate to trust store: ', end='')
            certRequest = subprocess.Popen(['curl', '-k', '-s', configurationData['RepositoryURL'] + configurationData[
                                           'certificatePath'] + '/' + CACert + '.crt'], stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
            certResponseBody = certRequest.communicate()[0]
            if certRequest.returncode != 0:
                print('FAILED. Could not fetch certificate at ' + configurationData['RepositoryURL'] +
                      configurationData['certificatePath'] + '/' + CACert + '.crt')
                print('curl return code was: ' + str(certRequest.returncode))
                print('curl errors follow: ')
                print(certRequest.communicate()[1])
                exit(1)
            certificateFileHandle = open('./' + CACert + '.crt', 'w')
            certificateFileHandle.write(certResponseBody)
            certificateFileHandle.close()
            if subprocess.call(['/usr/java/jdk' + configurationData['deploymentDictionary']['javaVersion'] +
                                '/bin/keytool', '-import', '-keystore', '/usr/java/jdk' +
                                configurationData['deploymentDictionary']['javaVersion'] +
                                '/jre/lib/security/cacerts', '-storepass', 'changeit', '-noprompt', '-file',
                                './' + CACert + '.crt', '-alias', CACert], stdout=devnull, stderr=devnull) != 0:
                print('FAILED')
                exit(1)
            print('OK')
    else:
        print('Found.')


# Install RPM dependencies

for rpmName in configurationData['packagesRequired']:
    if subprocess.call(['rpm', '-q', rpmName], stdout=devnull, stderr=devnull) != 0:
        print('Installing RPM: ' + rpmName)
        if subprocess.call(['yum', '-y', 'install', rpmName], stdout=devnull, stderr=devnull) != 0:
            print('Failed to install ' + rpmName)
            exit(1)
    else:
        print('Upgrading RPM: ' + rpmName)
        if subprocess.call(['yum', '-y', 'upgrade', rpmName], stdout=devnull, stderr=devnull) != 0:
            print('Yum call to upgrade ' + rpmName + ' Failed')
            exit(1)

# Clean up unwanted cron entry

if os.path.exists('/etc/cron.d/update_pdnsd.cron'):
    os.remove('/etc/cron.d/update_pdnsd.cron')
# Create SSL Certificates

if 'certificatePath' in configurationData and 'certificateName' in configurationData and \
        'certificatePassPhrase' in configurationData:
    print('Updating certificate: ' + configurationData['certificateName'] + ' ', end='')
    decodedPassPhrase = ''
    try:
        decodedPassPhrase = base64.b64decode(configurationData['certificatePassPhrase'])
    except TypeError:
        print('FATAL: Passphrase cannot be decoded.')
        exit(1)
    certRequest = subprocess.Popen(['curl', '-k', '-s', '--user', configurationData['certificateName'] + ':' +
                                    decodedPassPhrase,
                                    configurationData['RepositoryURL'] + configurationData['certificatePath'] + '/' +
                                    configurationData['certificateName']], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    certificateContents = certRequest.communicate()[0]
    if certRequest.returncode != 0:
        print('FAILED. Could not fetch certificate at ' + configurationData['RepositoryURL'] +
              configurationData['certificatePath'] + '/' + configurationData['certificateName'])
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
    certificateFileHandle = open('/opt/expedia/security/' + configurationData['certificateName'], 'w')
    certificateFileHandle.write(certificateContents)
    certificateFileHandle.close()
    print('OK')

for templatedfileName in templatedFiles:
    template = open(templatedfileName, 'r')
    outputData = template.read()
    template.close()
    for dictionaryKey in configurationData['deploymentDictionary']:
        outputData = outputData.replace('{{' + dictionaryKey + '}}',
                                        configurationData['deploymentDictionary'][dictionaryKey])
    os.rename(templatedfileName, templatedfileName + '~')
    outputFile = open(templatedfileName, 'w')
    outputFile.write(outputData)
    outputFile.close()
    os.remove(templatedfileName + '~')
    if templatedfileName.endswith('password'):
        os.chmod(templatedfileName, 0500)  # If the file contains passwords, it shouldn't be generally readable

os.mkdir(configurationData['targetDirectory'] + '.new')
os.mkdir(configurationData['targetDirectory'] + '.new' + '/etc')
os.mkdir(configurationData['targetDirectory'] + '.new' + '/bin')
os.mkdir(configurationData['targetDirectory'] + '.new' + '/temp')
if not os.path.isdir(configurationData['targetDirectory'] + '.bak' + '/logs'):
    os.mkdir(configurationData['targetDirectory'] + '.new' + '/logs')
shutil.move('./instance.properties', configurationData['targetDirectory'] + '.new' + '/etc/instance.properties')
os.chdir('explodedJar')
targetJar = zipfile.ZipFile(configurationData['targetDirectory'] + '.new' + '/bin/' + configurationData['jarName'], 'w')
for dirname, subdirs, files in os.walk('./'):
    targetJar.write(dirname)
    for fileName in files:
        targetJar.write(os.path.join(dirname, fileName))
targetJar.close()

if subprocess.call(['chown', '-R', configurationData['serviceUser'] + ':',
                    configurationData['targetDirectory'] + '.new']) != 0:
    print("FATAL: Couldn't change ownership of target directory " + configurationData['targetDirectory'])
    exit(1)

# if we've got this far, then we're ready to shut down and restart with the new version
if 'serviceName' in configurationData:
    print('Stopping ' + configurationData['serviceName'] + ' ', end='')
    if 'serviceInstance' in configurationData:
        print('instance ' + configurationData['serviceInstance'], end='')
    if subprocess.call(stopServiceCommand, stdout=devnull, stderr=devnull) != 0:
        print(': FAILED')
        exit(1)
    print(': OK')

# Delete old backups, if any
if os.path.isdir(configurationData['targetDirectory'] + '.bak'):
    print('Deleted old backup at ' + configurationData['targetDirectory'] + '.bak')
    shutil.rmtree(configurationData['targetDirectory'] + '.bak')

# Back up existing directory
if os.path.isdir(configurationData['targetDirectory']):
    os.rename(configurationData['targetDirectory'], configurationData['targetDirectory'] + '.bak')

os.rename(configurationData['targetDirectory'] + '.new', configurationData['targetDirectory'])

# Retain the logs from the old version, if any
if os.path.isdir(configurationData['targetDirectory'] + '.bak' + '/logs'):
    os.rename(configurationData['targetDirectory'] + '.bak' + '/logs', configurationData['targetDirectory'] + '/logs')

if 'serviceName' in configurationData:
    print('Starting ' + configurationData['serviceName'] + ' ', end='')
    if 'serviceInstance' in configurationData:
        print('instance ' + configurationData['serviceInstance'], end='')
    if subprocess.call(startServiceCommand, stdout=devnull, stderr=devnull) != 0:
        print(': FAILED')
        exit(1)
    print(': OK')

# Clean up old version
if os.path.isdir(configurationData['targetDirectory'] + '.bak'):
    shutil.rmtree(configurationData['targetDirectory'] + '.bak')
