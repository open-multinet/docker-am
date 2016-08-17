#!/bin/bash -e

echo '***** This will generate an AM server SSL certificate *****'

read -p "DNS of the AM? (Leave this empty to not add DNS name. It is strongly recommended to provide the DNS name!) " server_dns
read -p "URN of the server? (leave empty to not add URN to certificate) " server_urn

if [ ! -e 'generate-certs.sh' ]
then
    echo 'You need to run this script in the DIR the script is in (generate-certs)'
fi

#set -xv
set -x

ROOT_DIR="${PWD}/"

SERVER_DIR="${ROOT_DIR}server/"
mkdir -p "${SERVER_DIR}"

cd "${SERVER_DIR}"
SERVER_CERTS_DIR="${SERVER_DIR}certs/"
SERVER_CRL_DIR="${SERVER_DIR}crl/"
SERVER_NEWCERTS_DIR="${SERVER_DIR}newcerts/"
SERVER_PRIVATE_DIR="${SERVER_DIR}private/"
mkdir -p "${SERVER_CERTS_DIR}" "${SERVER_CRL_DIR}" "${SERVER_NEWCERTS_DIR}" "${SERVER_PRIVATE_DIR}"
chmod 700 "${SERVER_PRIVATE_DIR}"
INDEX_FILE="${SERVER_DIR}index.txt"
touch "${INDEX_FILE}"
SERIAL_FILE="${SERVER_DIR}serial"
echo 1000 > "${SERIAL_FILE}"

CONFIG_FILE="${SERVER_DIR}server_openssl.cnf"
cp -v "${ROOT_DIR}template_server_openssl.cnf" "${CONFIG_FILE}"
ESCAPED_SERVER_DIR=`echo "${SERVER_DIR}" | sed -e 's/\\//\\\\\\//g'`
sed -i -e "s/#SERVER_DIR#/${ESCAPED_SERVER_DIR}/" "${CONFIG_FILE}"

if [ -z "${server_dns}" ]
then
    sed -i -e '/#DNS#/d' "${CONFIG_FILE}"
else
    sed -i -e "s/#DNS#/${server_dns}/" "${CONFIG_FILE}"
fi

if [ -z "${server_urn}" ]
then
    sed -i -e '/#URI#/d' "${CONFIG_FILE}"
else
    ESCAPED_SERVER_URN=`echo "${server_urn}" | sed -e 's/\\//\\\\\\//g'`
    sed -i -e "s/#URI#/${ESCAPED_SERVER_URN}/" "${CONFIG_FILE}"
fi

if [ -z "${server_urn}" -a -z "${server_dns}" ]
then
    sed -i -e '/@server_alternate_names/d' "${CONFIG_FILE}"
fi

ROOT_KEY_FILE="${SERVER_PRIVATE_DIR}server.key.pem"
openssl genrsa -out "${ROOT_KEY_FILE}" 4096
chmod 400 "${ROOT_KEY_FILE}"

ROOT_CERT_FILE="${SERVER_CERTS_DIR}server.cert.pem"
cd "${SERVER_DIR}"
openssl req -config "${CONFIG_FILE}" \
      -key "${ROOT_KEY_FILE}" \
      -new -x509 -days 730 -sha256 -extensions server_cert \
      -out "${ROOT_CERT_FILE}"

chmod 444 "${ROOT_CERT_FILE}"
set +x

echo 
echo 
echo 'Key and cert generation complete.' 
echo 
echo "Server SSL Key: ${ROOT_KEY_FILE}"
echo "Server SSL Certificate: ${ROOT_CERT_FILE}"
echo 
echo "To see the certificates content, use:"
echo "     openssl x509 -text -in ${ROOT_CERT_FILE}"
echo 

