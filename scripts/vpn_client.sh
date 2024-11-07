#!/bin/bash

# Directory where client configurations will be stored
CONFIG_DIR="/path/to/openvpn-manager/clients"
CCD_DIR="/etc/openvpn/ccd" 
# Ensure the CONFIG_DIR exists
mkdir -p "$CONFIG_DIR"
chmod 774 "$CONFIG_DIR"

# Get the client name, password option, and password from command line arguments
CLIENT=$1
PASS_OPTION=$2  # "nopass" or "withpass"
CLIENT_PASSWORD=$3  # Password, if provided

# Validate the client name
if [[ ! $CLIENT =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Invalid client name. Use only alphanumeric characters, dashes, or underscores."
    exit 1
fi

# Check if the client already exists
CLIENT_EXISTS=$(grep -c -E "/CN=$CLIENT\$" /etc/openvpn/easy-rsa/pki/index.txt)
if [[ $CLIENT_EXISTS == '1' ]]; then
    echo "Client $CLIENT already exists. Choose a different name."
    exit 1
fi

# Generate the client certificate
cd /etc/openvpn/easy-rsa/ || exit
if [[ "$PASS_OPTION" == "nopass" ]]; then
    EASYRSA_CERT_EXPIRE=3650 ./easyrsa --batch build-client-full "$CLIENT" nopass
else
   EASYRSA_PASSOUT=pass:$CLIENT_PASSWORD EASYRSA_CERT_EXPIRE=3650 ./easyrsa --batch build-client-full "$CLIENT"
   
# Use expect to provide the password non-interactively
fi

echo "Client $CLIENT added successfully."

# Generate the client .ovpn file
OVPN_FILE="$CONFIG_DIR/$CLIENT.ovpn"
cp /etc/openvpn/client-template.txt "$OVPN_FILE"

{
    echo "<ca>"
    cat "/etc/openvpn/easy-rsa/pki/ca.crt"
    echo "</ca>"

    echo "<cert>"
    awk '/BEGIN/,/END CERTIFICATE/' "/etc/openvpn/easy-rsa/pki/issued/$CLIENT.crt"
    echo "</cert>"

    echo "<key>"
    cat "/etc/openvpn/easy-rsa/pki/private/$CLIENT.key"
    echo "</key>"

    if grep -qs "^tls-crypt" /etc/openvpn/server.conf; then
        echo "<tls-crypt>"
        cat /etc/openvpn/tls-crypt.key
        echo "</tls-crypt>"
    elif grep -qs "^tls-auth" /etc/openvpn/server.conf; then
        echo "key-direction 1"
        echo "<tls-auth>"
        cat /etc/openvpn/tls-auth.key
        echo "</tls-auth>"
    fi
} >> "$OVPN_FILE"
touch "$CCD_DIR/$CLIENT"
echo "Configuration file created: $OVPN_FILE"
echo "You can now download the .ovpn file and import it into your OpenVPN client."
exit 0


