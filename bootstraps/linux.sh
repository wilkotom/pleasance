#!/bin/bash 

if [ ${UID} != 0 ]; then
	sudo $0
	exit $?
fi

if [ ${POSIXLY_CORRECT} ]; then
	echo "ERROR: Pleasance Bootstrap must be invoked through /bin/bash, not /bin/sh" >&2
	exit 1
fi

workdir=$(mktemp -d)

cd ${workdir}
echo "$(date): Pleasance Bootstrap initiated for {{packageName}} version {{packageVersion}} on server ${HOSTNAME}" | tee >(exec logger -t pleasance-agent)
curl -s {{packageURL}} > ./packagefile
curl -s {{environmentConfiguration}} > ./environmentSetup
curl -s {{installerPath}} > ./installer
chmod 755 ./installer
./installer | tee >(exec logger -t pleasance-agent)
mkdir -p /var/db/pleasance
exitcode=${PIPESTATUS[0]}
[ ${exitcode} == 0 ] && echo "{{packageVersion}}" | sudo tee /var/db/pleasance/{{packageName}}.version >/dev/null
rm -rf ${workdir}
exit ${exitcode}
