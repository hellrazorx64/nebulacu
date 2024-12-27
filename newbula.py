import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import subprocess
import os
import psutil
import yaml
import threading
import ctypes
import sys

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

        tk.Label(self.config_tab, text="Host Certificate Path:").grid(row=1, column=0)
        self.cert_entry = tk.Entry(self.config_tab, width=50)
        self.cert_entry.grid(row=1, column=1)
        self.cert_entry.insert(0, self.config['pki']['cert'])

        tk.Label(self.config_tab, text="Host Key Path:").grid(row=2, column=0)
        self.key_entry = tk.Entry(self.config_tab, width=50)
        self.key_entry.grid(row=2, column=1)
        self.key_entry.insert(0, self.config['pki']['key'])

        tk.Label(self.config_tab, text="Lighthouse Host:").grid(row=3, column=0)
        self.lighthouse_entry = tk.Entry(self.config_tab, width=50)
        self.lighthouse_entry.grid(row=3, column=1)
        self.lighthouse_entry.insert(0, list(self.config['static_host_map'].keys())[0])

        tk.Button(self.config_tab, text="Save Config", command=self.save_config).grid(row=4, columnspan=2)

    def create_firewall_ui(self):
        # Create UI elements for firewall rules
        tk.Label(self.firewall_tab, text="Firewall Rules:").pack(pady=10)
        self.firewall_listbox = tk.Listbox(self.firewall_tab, width=80, height=10)
        self.firewall_listbox.pack(pady=10)

        # Load firewall rules from config
        self.load_firewall_rules()

        # Button to add a new rule
        tk.Button(self.firewall_tab, text="Add Rule", command=self.open_add_rule_dialog).pack(pady=5)
        tk.Button(self.firewall_tab, text="Remove Rule", command=self.remove_rule).pack(pady=5)

    def load_firewall_rules(self):
        # Load firewall rules from the configuration
        self.firewall_listbox.delete(0, tk.END)  # Clear existing rules
        if 'firewall' in self.config:
            for rule in self.config['firewall']['inbound']:
                self.firewall_listbox.insert(tk.END, f"Inbound: {rule}")
            for rule in self.config['firewall']['outbound']:
                self.firewall_listbox.insert(tk.END, f"Outbound: {rule}")

    def open_add_rule_dialog(self):
        """Open a dialog to add a new firewall rule."""
        dialog = tk.Toplevel(self.master)
        dialog.title("Add Firewall Rule")

        tk.Label(dialog, text="Comment:").grid(row=0, column=0)
        comment_entry = tk.Entry(dialog, width=50)
        comment_entry.grid(row=0, column=1)

        tk.Label(dialog, text="Direction:").grid(row=1, column=0)
        direction_var = tk.StringVar(value="Inbound")
        tk.Radiobutton(dialog, text="Inbound", variable=direction_var, value="Inbound").grid(row=1, column=1, sticky=tk.W)
        tk.Radiobutton(dialog, text="Outbound", variable=direction_var, value="Outbound").grid(row=1, column=1, sticky=tk.E)

        tk.Label(dialog, text="Port:").grid(row=2, column=0)
        port_entry = tk.Entry(dialog, width=50)
        port_entry.grid(row=2, column=1)

        tk.Label(dialog, text="Protocol:").grid(row=3, column=0)
        proto_entry = tk.Entry(dialog, width=50)
        proto_entry.grid(row=3, column=1)

        tk.Label(dialog, text="Host:").grid(row=4, column=0)
        host_entry = tk.Entry(dialog, width=50)
        host_entry.grid(row=4, column=1)

        tk.Label(dialog, text="Group:").grid(row=5, column=0)
        group_entry = tk.Entry(dialog, width=50)
        group_entry.grid(row=5, column=1)

        def add_rule():
            comment = comment_entry.get()
            direction = direction_var.get()
            port = port_entry.get()
            proto = proto_entry.get()
            host = host_entry.get()
            group = group_entry.get()

            if not all([comment, direction, port, proto, host, group]):
                messagebox.showerror("Error", "All fields must be filled out.")
                return

            rule = f"{direction}: {comment} (Port: {port}, Proto: {proto}, Host: {host}, Group: {group})"
            self.firewall_listbox.insert(tk.END, rule)
            dialog.destroy()

        tk.Button(dialog, text="Add Rule", command=add_rule).grid(row=6, columnspan=2, pady=10)

    def remove_rule(self):
        selected_rule_index = self.firewall_listbox.curselection()
        if selected_rule_index:
            self.firewall_listbox.delete(selected_rule_index)

    def save_config(self):
        # Save the updated configuration to config.yaml
        self.config['pki']['ca'] = self.ca_entry.get()
        self.config['pki']['cert'] = self.cert_entry.get()
        self.config['pki']['key'] = self.key_entry.get()
        self.config['static_host_map'] = {self.lighthouse_entry.get(): ['lh1.neb.primeghz.com:4242']}

        # Save firewall rules
        self.config['firewall']['inbound'] = []
        self.config['firewall']['outbound'] = []
        for rule in self.firewall_listbox.get(0, tk.END):
            if rule.startswith("Inbound:"):
                self.config['firewall']['inbound'].append(rule[9:])  # Remove "Inbound: " prefix
            elif rule.startswith("Outbound:"):
                self.config['firewall']['outbound'].append(rule[10:])  # Remove "Outbound: " prefix

        with open('nebula/config.yaml', 'w') as file:
            yaml.dump(self.config, file)
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
        else:
            self.stop_nebula()

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

if __name__ == "__main__":
    run_as_admin()  # Check for admin rights and relaunch if necessary
    root = tk.Tk()
    app = NebulaGui(root)
    root.mainloop()
