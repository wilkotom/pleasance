#!/bin/bash 

SUDOPREFIX=''

if [ ${UID} != 0 ]; then
        # If the script isn't running as root, we need to prepend certain commands with sudo 
	SUDOPREFIX="sudo"
fi

if [ ${POSIXLY_CORRECT} ]; then
	echo "ERROR: Pleasance Bootstrap must be invoked through /bin/bash, not /bin/sh" >&2
	exit 1
fi

workdir=$(mktemp -d)

cd ${workdir}
echo "$(date): Pleasance Bootstrap initiated for {{packageName}} version {{packageVersion}} on server ${HOSTNAME}" | tee >(exec logger -t pleasance-agent)
curl -k -s {{packageURL}} > ./packagefile
curl -k -s {{environmentConfiguration}} > ./environmentSetup
curl -k -s {{installerPath}} > ./installer
chmod 755 ./installer
${SUDOPREFIX} ./installer | tee >(exec logger -t pleasance-agent)
exitcode=${PIPESTATUS[0]}
${SUDOPREFIX} mkdir -p /var/db/pleasance
[ ${exitcode} == 0 ] && echo "{{packageVersion}}" | ${SUDOPREFIX} tee /var/db/pleasance/{{packageName}}.version >/dev/null
${SUDOPREFIX} rm -rf ${workdir}
exit ${exitcode}
