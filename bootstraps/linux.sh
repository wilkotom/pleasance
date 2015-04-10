#!/bin/bash

if [ ${POSIXLY_CORRECT} ]; then
	echo "ERROR: Pleasance Bootstrap must be invoked through /bin/bash, not /bin/sh" >&2
	exit 1
fi

workdir=$(mktemp -d)

cd ${workdir}
echo "$(date): Pleasance Bootstrap initiated for {{packageName}} version {{packageVersion}}" | tee >(exec logger -t pleasance-agent)
curl -s {{packageURL}} > ./packagefile
curl -s {{environmentConfiguration}} > ./environmentSetup
curl -s {{installerPath}} > ./installer
chmod 755 ./installer
if [ ${UID} == 0 ]; then
	./installer | tee >(exec logger -t pleasance-agent)
	exitcode=$?
	mkdir -p /var/db/pleasance
	[ ${exitcode} == 0 ] && echo "{{packageVersion}}" > /var/db/pleasance/{{packageName}}.version
	cd
	rm -rf ${workdir}
else
	sudo ./installer | tee >(exec logger -t pleasance-agent)
	exitcode=$?
	sudo mkdir -p /var/db/pleasance
	[ ${exitcode} == 0 ] && echo "{{packageVersion}}" | sudo tee /var/db/pleasance/{{packageName}}.version >/dev/null
	sudo rm -rf ${workdir}
fi
exit ${exitcode}

