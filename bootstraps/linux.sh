#!/bin/bash

workdir=$(mktemp -d)

cd ${workdir}

curl -s {{packageURL}} > ./packagefile
curl -s {{environmentConfiguration}} > ./environmentSetup
curl -s {{installerPath}} > ./installer
chmod 755 ./installer
if [ ${UID} == 0 ]; then
	./installer
	exitcode=$?
	mkdir -p /var/db/pleasance
	echo "{{packageVersion}}" > /var/db/pleasance/{{packageName}}.version
	cd
	rm -rf ${workdir}
else
	sudo ./installer
	exitcode=$?
	sudo mkdir -p /var/db/pleasance
	echo "{{packageVersion}}" | sudo tee /var/db/pleasance/{{packageName}}.version >/dev/null
	cd
	sudo rm -rf ${workdir}
fi
exit ${exitcode}

