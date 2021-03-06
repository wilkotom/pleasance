#!/usr/bin/env python
__author__ = 'twilkinson'

'''Removes older unpromoted versions of a particular package, retaining a fixed number
It can be invoked like this:
  PackageCleaner.py --application ari --connect https://pleasance.idx.expedmz.com/pleasance/v1 --number 20 \
   --username twilkinson'''

import httplib
import json
from getpass import getpass
from optparse import OptionParser
from base64 import b64encode


usage = "usage: %prog [options]"
parser = OptionParser(usage)
parser.add_option("-a", "--application", dest="application", help="Application to execute cleanup on")
parser.add_option("-c", "--connect", dest="connect", help="URL of Pleasance service")
parser.add_option("-n", "--number", type="int", dest="number", help="Number of unpromoted packages to retain")
parser.add_option("-u", "--username", dest="username", help="Username for Pleasance authentication")
parser.add_option("-p", "--password", dest="password", help="Password for Pleasance authentication")
(options, args) = parser.parse_args()

exitcode = 0

if options.application is None:
    print "Option --application is required."
    exitcode = 1

if options.connect is None:
    print "Option --connect is required."
    exitcode = 1

if options.number is None:
    print "Option --number is required."
    exitcode = 1

if options.username is None:
    print "Option --username is required."
    exitcode = 1

if exitcode > 0:
    exit(exitcode)

if options.password is None:
    options.password = getpass("Please enter password for user " + options.username + ": ")

credentials = b64encode(options.username + ":" + options.password)
request_headers = {"Accept": "application/json", "User-Agent": "Pleasance Package Cleaner/0.1",
                   "Authorization": "Basic " + credentials}

(protocol, _, hostname, path) = options.connect.split('/', 3)

# print "Connecting to " + protocol + "//" + hostname + "/" + path

if 'https' in protocol:
    pleasance_service = httplib.HTTPSConnection(hostname)
else:
    pleasance_service = httplib.HTTPConnection(hostname)

pleasance_service.request("GET", "/" + path + "/packageinfo/" + options.application, None, request_headers)
response = pleasance_service.getresponse()
if response.status != 200:
    print "Package not found on service " + options.connect

package_list = json.loads(response.read())

mtimes = {}

for package in package_list:
    if package_list[package]['promoted'] is False:
        mtimes[package_list[package]['created']] = package
    else:
        print "Excluding promoted " + options.application + " version " + package + " from clean up"

mtimelist = sorted(mtimes)
items_to_delete = len(mtimelist) - options.number
if items_to_delete < 0:
    items_to_delete = 0
mtimelist = mtimelist[0:items_to_delete]

print "Will delete " + str(items_to_delete) + " of " + str(
    len(mtimelist)) + " qualifying " + options.application + " packages"

for mtime in mtimelist:
    print "Deleting " + options.application + " " + mtimes[mtime]
    pleasance_service.request("DELETE", "/" + path + "/packages/" + options.application + '/' + mtimes[mtime], None,
                              request_headers)
    response = pleasance_service.getresponse()
    if response.status != 200:
        exitcode = 1
        print "Couldn't delete " + options.application + " version " + mtimes[mtime]

exit(exitcode)
