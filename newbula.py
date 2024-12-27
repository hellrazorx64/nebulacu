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

        self.load_config()

        # Configuration UI Elements
        self.create_config_ui()
        self.create_firewall_ui()
        self.console_output = tk.Text(self.console_tab, wrap=tk.WORD, state=tk.DISABLED)
        self.console_output.pack(expand=1, fill='both')

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
            for rule in self.config['firewall']['inbound']:
                self.firewall_listbox.insert(tk.END, f"Inbound: {rule}")
            for rule in self.config['firewall']['outbound']:
                self.firewall_listbox.insert(tk.END, f"Outbound: {rule}")

    def save_config(self):
        # Save the updated configuration to config.yaml
        self.config['pki']['ca'] = self.ca_entry.get()
        self.config['pki']['cert'] = self.cert_entry.get()
        self.config['pki']['key'] = self.key_entry.get()

        # Remove the static host map entirely
        if 'static_host_map' in self.config:
            del self.config['static_host_map']

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
            threading.Thread(target=update_tray_icon, args=(True,), daemon=True).start()
        else:
            self.stop_nebula()
            threading.Thread(target=update_tray_icon, args=(False,), daemon=True).start()

    def start_nebula(self):
        self.status_label.config(text="Status: Connecting")
        self.connect_button.config(text="Disconnect")
        
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
        # Monitor the output from the Nebula process
        for line in iter(self.process.stdout.readline, ''):
            self.console_output.config(state=tk.NORMAL)
            self.console_output.insert(tk.END, line)
            self.console_output.see(tk.END)  # Scroll to the end
            self.console_output.config(state=tk.DISABLED)

    def check_nebula_status(self):
        # Check if the nebula process is running
        if self.process.poll() is None:  # Process is still running
            self.status_label.config(text="Status: Connected")
            self.connect_button.config(text="Disconnect")
        else:
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

# Global variable to hold the tray icon and a lock for thread safety
tray_icon = None
icon_lock = threading.Lock()

def update_tray_icon(active):
    global tray_icon
    with icon_lock:  # Ensure thread safety
        if tray_icon is None:
            tray_icon = pystray.Icon("Nebula")
            tray_icon.icon = Image.open("active.ico" if active else "inactive.ico")
            tray_icon.menu = pystray.Menu(
                pystray.MenuItem("Connect", on_connect),
                pystray.MenuItem("Disconnect", on_disconnect),
                pystray.MenuItem("Exit", on_exit)
            )
            threading.Thread(target=tray_icon.run, daemon=True).start()  # Start the icon in a new thread
        else:
            tray_icon.icon = Image.open("active.ico" if active else "inactive.ico")

def on_connect(icon, item):
    app.toggle_connection()  # Call the toggle connection method

def on_disconnect(icon, item):
    app.stop_nebula()  # Call the stop method

def on_exit(icon, item):
    app.stop_nebula()  # Ensure nebula.exe is terminated
    if tray_icon:
        tray_icon.stop()  # Stop the icon

def setup(icon):
    icon.visible = True

if __name__ == "__main__":
    run_as_admin()  # Check for admin rights and relaunch if necessary
    root = tk.Tk()
    app = NebulaGui(root)
    update_tray_icon(False)  # Start the tray icon
    root.mainloop()
