#!/bin/bash

workdir=$(mktemp -d)

cd ${workdir}

curl -s {{packageURL}} > ./packagefile
curl -s {{environmentConfiguration}} > ./environmentSetup
curl -s {{installerPath}} > ./installer
chmod 755 ./installer
if [ ${UID} == 0 ]; then
	./installer > ./pleasance-agent.log
	exitcode=$?
	mkdir -p /var/db/pleasance
	[ ${exitcode} == 0 ] && echo "{{packageVersion}}" > /var/db/pleasance/{{packageName}}.version
	cat ./pleasance-agent.log | logger -t pleasance-agent
        cat ./pleasance-agent.log
	cd
	rm -rf ${workdir}
else
	sudo ./installer > ./pleasance-agent.log
	exitcode=$?
	sudo mkdir -p /var/db/pleasance
	[ ${exitcode} == 0 ] && echo "{{packageVersion}}" | sudo tee /var/db/pleasance/{{packageName}}.version >/dev/null
	cat ./pleasance-agent.log | logger -t pleasance-agent
	cat ./pleasance-agent.log
	sudo rm -rf ${workdir}
fi
exit ${exitcode}

