#!/bin/bash
CONFIG_DIR="/path/to/openvpn-manager/clients"
CCD_DIR="/etc/openvpn/ccd" 
# Define the client to revoke
CLIENT="$1"

# Check if a client name was provided
if [ -z "$CLIENT" ]; then
    echo "Please provide a client name."
    exit 1
fi

# Change to EasyRSA directory
cd /etc/openvpn/easy-rsa/ || return

# Revoke the client certificate
./easyrsa --batch revoke "$CLIENT"

# Generate a new CRL with extended validity
EASYRSA_CRL_DAYS=3650 ./easyrsa gen-crl

# Update the CRL in the OpenVPN directory
rm -f /etc/openvpn/crl.pem
cp /etc/openvpn/easy-rsa/pki/crl.pem /etc/openvpn/crl.pem
chmod 644 /etc/openvpn/crl.pem

# Delete the client configuration file in the specific clients directory
rm -f "$CONFIG_DIR/$CLIENT.ovpn"
rm -f "$CCD_DIR/$CLIENT"
# Remove client IP mapping from ipp.txt
sed -i "/^$CLIENT,.*/d" /etc/openvpn/ipp.txt

# Backup the index file
cp /etc/openvpn/easy-rsa/pki/index.txt{,.bk}

# Restart the OpenVPN service to apply changes
sudo systemctl restart openvpn

# Display success message
echo ""
echo "Certificate for client $CLIENT revoked and OpenVPN server restarted."
exit 0