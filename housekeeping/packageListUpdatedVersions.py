import httplib
import json
from optparse import OptionParser

'''Lists versions of a particular export package newer than a given datestamp
We can wrap this in a cron job to periodically grab files like this:
  for package in $(packageListUpdatedVersions.py --application ari \
       --connect https://pleasance.idx.expedmz.com/pleasance/v1 --newer $(stat -c %Y /path/to/semaphore)); do
    wget --content-disposition ${package};
  done
  touch /path/to/semaphore'''


usage = "usage: %prog [options]"
parser = OptionParser(usage)
parser.add_option("-a", "--application", dest="application", help="Application to search for updates")
parser.add_option("-c", "--connect", dest="connect", help="URL of Pleasance service")
parser.add_option("-n", "--newer", type="int", dest="newer", help="Starting date to list packages from")
(options, args) = parser.parse_args()

exitcode = 0

if options.application is None:
    print "Option --application is required."
    exitcode = 1

if options.connect is None:
    print "Option --connect is required."
    exitcode = 1

if options.newer is None:
    print "Option --newer is required."
    exitcode = 1


if exitcode > 0:
    exit(exitcode)

request_headers = {"Accept": "application/json", "User-Agent": "Pleasance Package Cleaner/0.1"}

(protocol, _, hostname, path) = options.connect.split('/', 3)

if 'https' in protocol:
    pleasance_service = httplib.HTTPSConnection(hostname)
else:
    pleasance_service = httplib.HTTPConnection(hostname)

pleasance_service.request("GET", "/" + path + "/packageinfo/" + options.application, None, request_headers)
response = pleasance_service.getresponse()
if response.status != 200:
    print "Package " + options.application + " not found on service " + options.connect
    exit(1)

version_list = json.loads(response.read())

for version in version_list:
    if version_list[version]["created"] > options.newer:
        print protocol + "//" + hostname + "/" + path + "/packageexport/" + options.application + "/" + version
