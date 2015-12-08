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

reload(sys)
sys.setdefaultencoding('utf8')

packageFile = './packagefile'
configurationFile = './environmentSetup'
debugging_enabled = False
devnull = open('/dev/null', 'w')

suffix_blacklist = ['ar', 'class', 'jks', 'pfx', 'ser']

configurationData = json.load(open(configurationFile))
if 'debug' in configurationData:
    if configurationData['debug'] is True:
        debugging_enabled = True
    elif not isinstance(configurationData['debug'], bool):
        print('WARNING: debug flag is not boolean. Assuming debug flag is set to false')

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
    # Replace double backslashes with single ones
    if "\\\\" in configurationData['deploymentDictionary'][dictionaryKey]:
        configurationData['deploymentDictionary'][dictionaryKey] = configurationData['deploymentDictionary'][
            dictionaryKey].replace('\\\\', '\\')

if 'serviceName' not in configurationData:
    print('Warning: No service name defined.')
else:
    startServiceCommand = ['/sbin/service', configurationData['serviceName'], 'start']
    stopServiceCommand = ['/sbin/service', configurationData['serviceName'], 'stop']
    if 'serviceInstance' in configurationData:
        startServiceCommand.append(configurationData['serviceInstance'])
        stopServiceCommand.append(configurationData['serviceInstance'])
        configurationData['targetDirectory'] += '/' + configurationData['serviceInstance']

if 'serviceUser' not in configurationData:
    if 'serviceName' not in configurationData:
        print('FATAL: serviceUser attribute not defined')
        exit(1)
    else:
        configurationData['serviceUser'] = configurationData['serviceName']


# Delete any aborted previous installation
if os.path.isdir(configurationData['targetDirectory'] + '.new'):
    print('Deleted old working directory at ' + configurationData['targetDirectory'] + '.new')
    shutil.rmtree(configurationData['targetDirectory'] + '.new')

os.makedirs(configurationData['targetDirectory'] + '.new', 0755)
print('Created ' + configurationData['targetDirectory'] + '.new')

try:
    packageZip = zipfile.ZipFile('./packagefile', 'r')
    packageZip.extractall(configurationData['targetDirectory'] + '.new')
    packageZip.close()
except zipfile.BadZipfile:
    print('FATAL: Package supplied does not appear to be a Zip archive.')
    exit(1)

packagedFiles = []

for dirPath, dirName, fileNames in os.walk(configurationData['targetDirectory'] + '.new'):
    for fileName in fileNames:
        blacklisted = False
        for suffix in suffix_blacklist:
            if fileName.endswith(suffix):
                blacklisted = True
        if blacklisted is False:
            packagedFiles.append(dirPath + '/' + fileName)
        elif debugging_enabled is True:
            print('DEBUG: Blackisted suffix. Not scanning placeholders in file: ' + dirPath + '/' + fileName)


foundTokens = []
templatedFiles = []

for packagedFile in packagedFiles:
    fileContents = open(packagedFile, 'r').read()
    tokenList = []
    for token in fileContents.split('}}'):
        if token.find('{{') >= 0:
            tokenList.append(token.partition('{{')[2])
            templatedFiles.append(packagedFile)
    foundTokens = foundTokens + tokenList
    if packagedFile.endswith('password'):
        os.chmod(packagedFile, 0500)  # If the file contains passwords, it shouldn't be generally readable

foundTokens = list(set(foundTokens))  # Remove duplicates
templatedFiles = list(set(templatedFiles))

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
    repofile.write('[expedia-pleasance]\nname=expedia-pleasance\nbaseurl=' + configurationData[
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
            '-fcs.x86_64.rpm', '--oldpackage', '--relocate',
            '/etc/init.d/jexec=/etc/init.d/jexec-' + configurationData['deploymentDictionary'][
            'javaVersion'], '--badreloc'], stdout=devnull, stderr=devnull)
        if exitCode == 0:
            print('OK')
        else:
            print('Failed')
            exit(1)
        for CACert in ['ExpediaRootCA', 'ExpediaInternal1C']:
            print('Adding ' + CACert + ' certificate to trust store: ', end='')
            certRequest = subprocess.Popen(['curl', '-k', '-s', configurationData['RepositoryURL'] + configurationData[
                'certificatePath'] + '/' + CACert + '.crt'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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

# Install Tomcat
if 'tomcatVersion' in configurationData['deploymentDictionary'] and \
        'yumRepositoryPath' in configurationData and 'RepositoryURL' in configurationData:
    print('Checking for Tomcat version ' + configurationData['deploymentDictionary']['tomcatVersion'] + ': ', end='')
    if subprocess.call(
            ['rpm', '-q', 'tomcat-deployit' + '-' + configurationData['deploymentDictionary']['tomcatVersion']],
            stdout=devnull, stderr=devnull) != 0:
        print('Not found. Installing it. ', end='')
        if subprocess.call(['yum', '-yq', 'install',
                            'tomcat-deployit' + '-' + configurationData['deploymentDictionary']['tomcatVersion']],
                           stdout=devnull, stderr=devnull) != 0:
            print('FAILED')
            exit(1)
        else:
            print('OK')
    else:
        print('Found')

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

if 'certificatePath' in configurationData and \
        'certificateName' in configurationData and 'certificatePassPhrase' in configurationData:
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
    #  if there's a log dir in the deployment artifact, delete it in favour of the existing directory
    if os.path.isdir(configurationData['targetDirectory'] + '/logs'):
        shutil.rmtree(configurationData['targetDirectory'] + '/logs')
    os.rename(configurationData['targetDirectory'] + '.bak' + '/logs', configurationData['targetDirectory'] + '/logs')
elif not os.path.isdir(configurationData['targetDirectory'] + '/logs'):
    os.mkdir(configurationData['targetDirectory'] + '/logs', 0755)
    os.chown(configurationData['targetDirectory'] + '/logs', pwd.getpwnam(configurationData['serviceUser']).pw_uid,
             pwd.getpwnam(configurationData['serviceUser']).pw_gid)

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
