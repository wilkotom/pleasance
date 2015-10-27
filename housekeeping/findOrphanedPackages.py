__author__ = 'twilkinson'

from pymongo import MongoClient
from optparse import OptionParser
import gridfs


usage = "usage: %prog [options]"
parser = OptionParser(usage)
parser.add_option("-s", "--server", dest="mongo_server", help="Host for Mongo DB database (default: localhost)", default="localhost")
parser.add_option("-p", "--port", dest="mongo_port", help="Port fopr Mongo DB database (default: 27017)", default=27017)
parser.add_option("-d", "--delete", action="store_true", dest="delete_files ", help="Delete Files?", default=False)

(options, args) = parser.parse_args()

mongo_db = MongoClient(options.mongo_server, options.mongo_port).pleasance
filestore = gridfs.GridFS(mongo_db)
packages = mongo_db.packages

valid_file_id_mappings = []
orphaned_files = []

for file in filestore.find():
    if packages.find_one({'file_id': file._id}):
        valid_file_id_mappings.append(file)
    else:
        orphaned_files.append(file)

print "Non-Orphan files:"
for file in valid_file_id_mappings:
    package = packages.find_one({'file_id': file._id})
    print str(file._id) + " " + str(package["name"]) + " " + str(package["version"])

print "=============================="
print str(orphaned_files.__len__()) + " Orphan files:"
for file in orphaned_files:
    print str(file._id)
    if options.delete_files is True:
        print "Deleting Orphaned file"
        filestore.delete(file._id)

