import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, filedialog
import subprocess
import os
import psutil
import yaml
import threading
import ctypes
import sys
import pystray
from PIL import Image, ImageDraw
from plyer import notification
import logging

# Set up logging
logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Log the start of the program
logging.debug("Program started.")

def is_admin():
    """Check if the script is running with admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Relaunch the script with admin privileges."""
    if not is_admin():
        # Relaunch the script with admin rights
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

class NebulaGui:
    def __init__(self, master):
        self.master = master
        self.master.title("Nebula Mesh Client Control")
        
        # Override window close button (X)
        self.master.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        
        # Initialize notifications_enabled
        self.notifications_enabled = tk.BooleanVar(value=True)
        
        self.connect_button = tk.Button(master, text="Connect", command=self.toggle_connection, state=tk.DISABLED)
        self.connect_button.pack(pady=20)

        self.status_label = tk.Label(master, text="Status: Disconnected")
        self.status_label.pack(pady=10)

        self.tab_control = ttk.Notebook(master)
        self.config_tab = ttk.Frame(self.tab_control)
        self.firewall_tab = ttk.Frame(self.tab_control)
        self.console_tab = ttk.Frame(self.tab_control)

        self.tab_control.add(self.config_tab, text='Configuration')
        self.tab_control.add(self.firewall_tab, text='Firewall')
        self.tab_control.add(self.console_tab, text='Console')
        self.tab_control.pack(expand=1, fill='both')

        # Initialize console output
        self.console_output = tk.Text(self.console_tab, wrap=tk.WORD, state=tk.DISABLED)
        self.console_output.pack(expand=1, fill='both')

        self.load_config()
        self.create_config_ui()
        self.create_firewall_ui()

        # Add a variable to store the lighthouse hostnames from static_host_map
        self.lighthouse_hosts = set()
        self.load_lighthouse_hosts()

    def create_config_ui(self):
        # Create UI elements for configuration
        tk.Label(self.config_tab, text="CA Certificate Path:").grid(row=0, column=0)
        self.ca_entry = tk.Entry(self.config_tab, width=50)
        self.ca_entry.grid(row=0, column=1)
        self.ca_entry.insert(0, self.config['pki']['ca'])
        tk.Button(self.config_tab, text="Browse", command=self.browse_ca).grid(row=0, column=2)

        tk.Label(self.config_tab, text="Host Certificate Path:").grid(row=1, column=0)
        self.cert_entry = tk.Entry(self.config_tab, width=50)
        self.cert_entry.grid(row=1, column=1)
        self.cert_entry.insert(0, self.config['pki']['cert'])
        tk.Button(self.config_tab, text="Browse", command=self.browse_cert).grid(row=1, column=2)

        tk.Label(self.config_tab, text="Host Key Path:").grid(row=2, column=0)
        self.key_entry = tk.Entry(self.config_tab, width=50)
        self.key_entry.grid(row=2, column=1)
        self.key_entry.insert(0, self.config['pki']['key'])
        tk.Button(self.config_tab, text="Browse", command=self.browse_key).grid(row=2, column=2)

        # Checkbox for notifications
        tk.Checkbutton(self.config_tab, text="Enable Notifications", variable=self.notifications_enabled).grid(row=3, columnspan=3)

        tk.Button(self.config_tab, text="Save Config", command=self.save_config).grid(row=4, columnspan=3)

    def create_firewall_ui(self):
        # Create UI elements for firewall rules
        tk.Label(self.firewall_tab, text="Firewall Rules:").pack(pady=10)
        self.firewall_listbox = tk.Listbox(self.firewall_tab, width=80, height=10)
        self.firewall_listbox.pack(pady=10)

        # Load firewall rules from config
        self.load_firewall_rules()

    def load_firewall_rules(self):
        # Load firewall rules from the configuration
        self.firewall_listbox.delete(0, tk.END)  # Clear existing rules
        if 'firewall' in self.config:
            if 'inbound' in self.config['firewall']:
                for rule in self.config['firewall']['inbound']:
                    self.firewall_listbox.insert(tk.END, f"Inbound: {rule}")
            if 'outbound' in self.config['firewall']:
                for rule in self.config['firewall']['outbound']:
                    self.firewall_listbox.insert(tk.END, f"Outbound: {rule}")

    def save_config(self):
        # Save the updated configuration to config.yaml
        self.config['pki']['ca'] = self.ca_entry.get()
        self.config['pki']['cert'] = self.cert_entry.get()
        self.config['pki']['key'] = self.key_entry.get()

        # Write the configuration to the YAML file
        with open('nebula/config.yaml', 'w') as file:
            yaml.dump(self.config, file, default_flow_style=False)  # Ensure proper YAML formatting
        messagebox.showinfo("Info", "Configuration saved successfully.")

    def load_config(self):
        # Load configuration from config.yaml
        try:
            with open('nebula/config.yaml', 'r') as file:
                self.config = yaml.safe_load(file)
                self.connect_button.config(state=tk.NORMAL)  # Enable button if config loads
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load config: {e}")

    def toggle_connection(self):
        if self.connect_button['text'] == "Connect":
            self.start_nebula()
            self.notify_user("Connected to Nebula.")
            threading.Thread(target=update_tray_icon, args=(True,), daemon=True).start()
        else:
            self.stop_nebula()
            self.notify_user("Disconnected from Nebula.")
            threading.Thread(target=update_tray_icon, args=(False,), daemon=True).start()

    def start_nebula(self):
        self.status_label.config(text="Status: Connecting")
        self.connect_button.config(text="Disconnect")
        
        # Reload lighthouse hosts in case config has changed
        self.load_lighthouse_hosts()
        
        # Construct the command to launch nebula.exe with the config file
        current_folder = os.getcwd()  # Get the current working directory
        command = [os.path.join(current_folder, 'nebula', 'nebula.exe'), 
                   '-config', 
                   os.path.join(current_folder, 'nebula', 'config.yaml')]
        
        # Launch the process
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Start a thread to monitor the output
        threading.Thread(target=self.monitor_output, daemon=True).start()
        self.master.after(1000, self.check_nebula_status)

    def monitor_output(self):
        """Monitor the output from the Nebula process"""
        for line in iter(self.process.stdout.readline, ''):
            self.console_output.config(state=tk.NORMAL)
            self.console_output.insert(tk.END, line)
            self.console_output.see(tk.END)
            self.console_output.config(state=tk.DISABLED)

            # Parse the line for connection status
            self.parse_nebula_output(line)

    def parse_nebula_output(self, line):
        """Parse nebula output for connection status changes"""
        try:
            # Check for handshake message
            if "msg=\"Handshake message received\"" in line:
                for host in self.lighthouse_hosts:
                    if f"certName={host}" in line:
                        self.status_label.config(text="Status: Connected")
                        self.connect_button.config(text="Disconnect")
                        return

            # Check for tunnel closing message
            if "msg=\"Close tunnel received, tearing down.\"" in line:
                for host in self.lighthouse_hosts:
                    if f"certName={host}" in line:
                        self.status_label.config(text="Status: Disconnected")
                        self.connect_button.config(text="Stop")
                        self.notify_user("Connection lost. Attempting to reconnect...")
                        # Update tray icon to warning state
                        threading.Thread(target=update_tray_icon, args=("warning",), daemon=True).start()
                        return

        except Exception as e:
            logging.error(f"Error parsing nebula output: {e}")

    def check_nebula_status(self):
        # Only check if process is running, status changes are handled by parse_nebula_output
        if self.process.poll() is not None:  # Process has terminated
            self.status_label.config(text="Status: Disconnected")
            self.connect_button.config(text="Connect")
        
        # Check again after 1 second
        self.master.after(1000, self.check_nebula_status)

    def stop_nebula(self):
        self.status_label.config(text="Status: Disconnecting")
        self.connect_button.config(state=tk.DISABLED)
        if self.process:
            self.process.terminate()  # Terminate the process
            self.process.wait()  # Wait for the process to terminate
        self.status_label.config(text="Status: Disconnected")
        self.connect_button.config(state=tk.NORMAL)  # Re-enable the connect button
        threading.Thread(target=update_tray_icon, args=(False,), daemon=True).start()

    def browse_ca(self):
        filename = filedialog.askopenfilename(title="Select CA Certificate", filetypes=[("Certificate Files", "*.crt")])
        if filename:
            self.ca_entry.delete(0, tk.END)
            self.ca_entry.insert(0, filename)

    def browse_cert(self):
        filename = filedialog.askopenfilename(title="Select Host Certificate", filetypes=[("Certificate Files", "*.crt")])
        if filename:
            self.cert_entry.delete(0, tk.END)
            self.cert_entry.insert(0, filename)

    def browse_key(self):
        filename = filedialog.askopenfilename(title="Select Host Key", filetypes=[("Key Files", "*.key")])
        if filename:
            self.key_entry.delete(0, tk.END)
            self.key_entry.insert(0, filename)

    def notify_user(self, message):
        if self.notifications_enabled.get():
            notification.notify(
                title="Nebula Mesh Client",
                message=message,
                app_name="Nebula",
                timeout=10
            )

    def minimize_to_tray(self):
        """Minimize the window to system tray instead of closing"""
        self.master.withdraw()  # Hide the window
        self.notify_user("Application minimized to tray")

    def show_window(self):
        """Show the window when requested from tray"""
        self.master.deiconify()  # Show the window
        self.master.lift()  # Bring it to front
        self.master.focus_force()  # Force focus

    def load_lighthouse_hosts(self):
        """Load lighthouse hostnames from static_host_map in config"""
        if 'static_host_map' in self.config:
            for hosts in self.config['static_host_map'].values():
                for host in hosts:
                    # Extract hostname from host:port format
                    hostname = host.split(':')[0]
                    self.lighthouse_hosts.add(hostname)

# Global variable to hold the tray icon and a lock for thread safety
tray_icon = None
icon_lock = threading.Lock()

def update_tray_icon(state):
    global tray_icon
    with icon_lock:  # Ensure thread safety
        if tray_icon is None:
            tray_icon = pystray.Icon("Nebula")
            # Choose icon based on state
            if state == "warning":
                tray_icon.icon = Image.open("warning.ico")
            else:
                tray_icon.icon = Image.open("active.ico" if state else "inactive.ico")
            tray_icon.menu = pystray.Menu(
                pystray.MenuItem("Show", lambda: app.show_window()),
                pystray.MenuItem("Connect/Disconnect", on_connect),
                pystray.MenuItem("Exit", on_exit)
            )
            threading.Thread(target=tray_icon.run, daemon=True).start()
        else:
            # Update existing icon based on state
            if state == "warning":
                tray_icon.icon = Image.open("warning.ico")
            else:
                tray_icon.icon = Image.open("active.ico" if state else "inactive.ico")

def on_connect(icon, item):
    app.toggle_connection()  # Call the toggle connection method

#def on_disconnect(icon, item):
#    app.stop_nebula()  # Call the stop method

def on_exit(icon, item):
    app.stop_nebula()  # Ensure nebula.exe is terminated
    if tray_icon:
        tray_icon.stop()  # Stop the icon
    app.master.destroy()  # Close the GUI window
    sys.exit()  # Ensure complete exit

def setup(icon):
    icon.visible = True

if __name__ == "__main__":
    try:
        # Check for admin rights first
        if not is_admin():
            run_as_admin()
        else:
            # Only create the GUI if we're running as admin
            logging.debug("Starting application with admin privileges")
            root = tk.Tk()
            app = NebulaGui(root)
            update_tray_icon(False)  # Start the tray icon
            root.mainloop()
    except Exception as e:
        logging.error("An error occurred: %s", e)
        # Keep the window open if there's an error
        input("Press Enter to exit...")
