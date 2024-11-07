from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import os
import subprocess
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from config import config

app = Flask(__name__)

env = os.getenv('FLASK_ENV', 'development')
app.config.from_object(config[env])  # Load the configuration based on FLASK_ENV

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


CONFIG_DIR = "clients"  # Directory where client .ovpn files are stored
STATUS_FILE = "/var/log/openvpn/status.log"  # Example file storing client status (IP, etc.)
CCD_DIR = "/etc/openvpn/ccd"
IPP_FILE = "/etc/openvpn/ipp.txt"  # Path to the ipp.txt file

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
# Routes

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))



# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')



@app.route('/toggle_client_access/<client_name>/<action>')
@login_required
def toggle_client_access(client_name, action):
    """
    Enable or disable client access by creating or deleting the CCD file.
    """
    ccd_file_path = os.path.join(CCD_DIR, client_name)

    if action == 'enable':
        # Create the CCD file to enable access
        try:
            with open(ccd_file_path, "w") as f:
                f.write("")  # CCD file can be empty
            flash(f"Client '{client_name}' enabled successfully.", "success")
        except Exception as e:
            flash(f"Failed to enable client '{client_name}': {e}", "danger")

    elif action == 'disable':
        # Delete the CCD file to disable access
        try:
            os.remove(ccd_file_path)
            flash(f"Client '{client_name}' disabled successfully.", "success")
        except FileNotFoundError:
            flash(f"Client '{client_name}' is already disabled.", "warning")
        except Exception as e:
            flash(f"Failed to disable client '{client_name}': {e}", "danger")
    try:
        # Run the restart command
        subprocess.run(['sudo', 'systemctl', 'restart', 'openvpn'], check=True)
        flash("OpenVPN server restarted successfully.", "success")
    except subprocess.CalledProcessError:
        flash("Failed to restart OpenVPN server.", "danger")
   # return redirect(url_for('dashboard'))
    return redirect(url_for('dashboard'))



def get_all_configured_clients():
    """Retrieve all configured clients based on the .ovpn files in CONFIG_DIR."""
    clients = []
    if os.path.exists(CONFIG_DIR):
        for filename in os.listdir(CONFIG_DIR):
            if filename.endswith(".ovpn"):
                client_name = filename.rsplit('.', 1)[0]  # Remove the .ovpn extension
                clients.append({"name": client_name,"enabled":False, "ip": "N/A","real_ip":"N/A", "active": False})
    return clients

@app.route('/restart_server', methods=['POST'])
@login_required
def restart_server():
    try:
        # Run the restart command
        subprocess.run(['sudo', 'systemctl', 'restart', 'openvpn'], check=True)
        flash("OpenVPN server restarted successfully.", "success")
    except subprocess.CalledProcessError:
        flash("Failed to restart OpenVPN server.", "danger")
    return redirect(url_for('dashboard'))

def add_vpn_client(client_name, pass_option, client_password=None):
    """Call the VPN shell script to add a new client with or without a password."""
    try:
        # Build the command based on whether password is needed
        command = ['./scripts/vpn_client.sh', client_name, pass_option]
        if pass_option == "withpass" and client_password:
            # Set the password as an environment variable (or pass securely to the script)
            command.append(client_password)

        # Run the command
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return e.output

def revoke_client(client_name):
    try:
        result = subprocess.run(
            ['./scripts/revoke_client.sh', client_name],
            text=True,
            capture_output=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return e.output
  

@app.route('/revoke_client/<client_name>', methods=['POST'])
@login_required
def revoke_client_route(client_name):
    # Call the revoke function
    result = revoke_client(client_name)
    
    # Display the result to the user
    flash(result)
    
    # Redirect to the dashboard or any other relevant page
    return redirect(url_for('dashboard'))



def get_all_users():
    """Retrieve all users and their assigned IPs from ipp.txt."""
    users = []
    if os.path.exists(IPP_FILE):
        with open(IPP_FILE, "r") as file:
            for line in file:
                # Skip empty lines
                if line.strip():
                    # Split by comma to separate the client name and IP address
                    parts = line.strip().split(',')
                    client_name = parts[0].strip()
                    client_ip = parts[1].strip() if len(parts) > 1 else "N/A"
                    # Append user with IP and inactive status by default
                    users.append({"name": client_name,"enabled":False, "ip": client_ip,"real_ip":"N/A", "active": False})
    #print("Parsed users from ipp.txt:", users)  # Debug print
    return users

def get_active_users():
    """Get a list of active users and their virtual IPs from the OpenVPN status log."""
    active_users = {}
    with open(STATUS_FILE, "r") as file:
        lines = file.readlines()
        
        # Flag for identifying the sections
        in_client_list = False
        in_routing_table = False

        # Temporary storage for virtual IPs
        client_virtual_ips = {}

        for line in lines:
            # Detect the beginning of the CLIENT LIST section
            if line.startswith("OpenVPN CLIENT LIST"):
                in_client_list = True
                in_routing_table = False
                continue
            
            # Detect the beginning of the ROUTING TABLE section
            if line.startswith("ROUTING TABLE"):
                in_client_list = False
                in_routing_table = True
                continue

            # Detect the end of relevant sections
            if line.startswith("GLOBAL STATS") or line.startswith("END"):
                in_client_list = False
                in_routing_table = False
                continue

            # Parse client list section
            if in_client_list and line and not line.startswith("Common Name"):
                parts = line.split(',')
                client_name = parts[0].strip()
                real_address = parts[1].split(':')[0]  # Extract IP only from Real Address
                active_users[client_name] = {"real_address": real_address, "virtual_ip": None}

            # Parse routing table section to get virtual IPs
            if in_routing_table and line and not line.startswith("Virtual Address"):
                parts = line.split(',')
                virtual_ip = parts[0].strip()
                client_name = parts[1].strip()
                if client_name in active_users:
                    active_users[client_name]["virtual_ip"] = virtual_ip

    return active_users


@app.route('/')
@login_required
def dashboard():
    # Get all users from ipp.txt (users who have connected at least once)
    all_users = get_all_users()
    # Get active users from status.log
    active_users = get_active_users()
    # Get all configured clients based on .ovpn files
    configured_clients = get_all_configured_clients()

    # Convert all_users to a dictionary for quick lookup by name
    all_users_dict = {user["name"]: user for user in all_users}

    # Update the status of each user based on active users
    for user in all_users:
        ccd_file_path = os.path.join(CCD_DIR, user['name'])
        user['enabled'] = os.path.isfile(ccd_file_path)
        if user["name"] in active_users:
            user["active"] = True
            user["real_ip"] = active_users[user["name"]]["real_address"]

    # Add any configured clients that are not in all_users
    for client in configured_clients:
        client_name = client["name"]
        if client_name not in all_users_dict:
            # Add missing client with default inactive status
            client["active"] = False
            client["real_ip"] = "N/A"  # Default value if no IP is available
            all_users.append(client)  # Append to the main list

    #print("Final user list:", all_users)
    return render_template('dashboard.html', clients=all_users)




@app.route('/add_client', methods=['GET', 'POST'])
@login_required
def add_client():
    if request.method == 'POST':
        client_name = request.form['client_name']
        pass_option = request.form['pass_option']  # 'nopass' or 'withpass'
        client_password = request.form.get('client_password', None)  # Password (if provided)

        if not client_name:
            flash('Client name is required!', 'danger')
            return redirect(url_for('add_client'))
        
        # Call the add_vpn_client function with the specified password option and password
        output = add_vpn_client(client_name, pass_option, client_password)
        flash(f'Client added: {output}', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_client.html')




@app.route('/download/<client_name>')
@login_required
def download_config(client_name):
    config_path = os.path.join(CONFIG_DIR, f"{client_name}.ovpn")
    if os.path.exists(config_path):
        return send_from_directory(CONFIG_DIR, f"{client_name}.ovpn", as_attachment=True)
    else:
        flash("Configuration file not found.")
        return redirect(url_for('dashboard'))

if __name__ == "__main__":
    app.run(port=5000, debug=True)

