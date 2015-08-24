#!/bin/bash
cd /mnt/ewelab2ch/Pleasance/packages
for package in $(find . -name *.pnc); do 
  curl -s -k -X POST https://127.0.0.1/pleasance/v1/packageimport --upload-file $package | \
        grep -E -q '201|409' && echo $package >> /mnt/ewech2lab/Pleasance/successful-imports; 
done
