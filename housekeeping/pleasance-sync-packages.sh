#!/bin/bash

#Places new versions of packages on the share for alternate instance to slurp


# Where to put the exported packages
SHARE=/mnt/ewelab2ch/Pleasance

# When the importer on the other end has slurped a package, it will add its 
# name to this file so it can be deleted
IMPORTLIST=/mnt/ewech2lab/Pleasance/successful-imports

cd ${SHARE}/packages

STARTTIME=$(date +%s)

for file in $(cat ${IMPORTLIST}); do
  [ -f $file ] && rm $file
done

# The sempahore file contains the time since the Epoch when the last export ran
# We only need to export packages newer than this.
LASTSEMAPHORE=$(cat ${SHARE}/semaphore)

for application in $(cat /usr/local/etc/pleasance-cleaner-packages); do
  for package in $(/usr/local/bin/packageListUpdatedVersions --application ${application} \
                   --connect https://127.0.0.1/pleasance/v1 --newer ${LASTSEMAPHORE}); do
    wget --content-disposition $package --no-check-certificate > /dev/null 2>&1
  done
done

echo ${STARTTIME} > ${SHARE}/semaphore

