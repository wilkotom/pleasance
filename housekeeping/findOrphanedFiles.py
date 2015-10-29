__author__ = 'twilkinson'

from pymongo import MongoClient
from optparse import OptionParser
import gridfs


usage = "usage: %prog [options]"
parser = OptionParser(usage)
parser.add_option("-s", "--server", dest="mongo_server", help="Host for Mongo DB database (default: localhost)", default="localhost")
parser.add_option("-p", "--port", dest="mongo_port", help="Port fopr Mongo DB database (default: 27017)", default=27017)
parser.add_option("-d", "--delete", action="store_true", dest="delete_files", help="Delete Files?", default=False)

(options, args) = parser.parse_args()

mongo_db = MongoClient(options.mongo_server, options.mongo_port).pleasance
filestore = gridfs.GridFS(mongo_db)
packages = mongo_db.packages
installers = mongo_db.installers

valid_package_mappings = []
valid_installer_mappings = []
orphaned_files = []

for file_metadata in filestore.find():
    if packages.find_one({'file_id': file_metadata._id}):
        valid_package_mappings.append(file_metadata)
    else:
        if installers.find_one({'file_id': file_metadata._id}):
            valid_installer_mappings.append(file_metadata)
        else:
            orphaned_files.append(file_metadata)

print "Non-Orphan files:"
print "Packages:"
for file_metadata in valid_package_mappings:
    package = packages.find_one({'file_id': file_metadata._id})
    print str(file_metadata._id) + " " + package["name"] + " " + package["version"]

print "Installers:"
for file_metadata in valid_installer_mappings:
    installer = installers.find_one({'file_id': file_metadata._id})
    print str(file_metadata._id) + " " + installer["name"] + " " + installer["platform"]


print "=============================="
print str(orphaned_files.__len__()) + " Orphan files:"
for file_metadata in orphaned_files:
    print str(file_metadata._id)
    if options.delete_files is True:
        print "Deleting Orphaned file"
        filestore.delete(file_metadata._id)
