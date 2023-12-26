import os
import sys
from tkinter import filedialog
import yaml # pip install pyyaml
from selenium import webdriver # pip install selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import tkinter as tk  # pip install tk
from tkinter import messagebox
import subprocess
import shutil
import winreg

class SimpleInstaller:
    def __init__(self, config, initial_variables={}) -> None:
        self.config = config
        self.variables = initial_variables
        self.variables.update({
            'GAME_PATH': None,
            'DOWNLOAD_CACHE_PATH': None,
            'MO2_EXE_PATH': None,
            'MO2_APPDATA_PATH': None,
        })
        self.log_file = None
        if "about" in config and "debug_log" in config["about"]:
            # Open with utf8
            self.log_file = open(config["about"]["debug_log"], "w", encoding="utf8")
    
    def _log(self, message, verbose_only_message=False):
        # Log with timestampe
        if not verbose_only_message or "about" in self.config and "verbose" in self.config["about"] and self.config["about"]["verbose"]:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
        
        if self.log_file:
            self.log_file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
            self.log_file.flush()
    
    def _replace_variables(self, string):
        # Replace variables in a string with their values
        #print("VARIABLES:", variables)
        for key, value in self.variables.items():
            if value is None or key is None or not isinstance(value, str) or not isinstance(key, str):
                continue
            string = string.replace(f"<{key}>", value)
        return string
    
    def _action_ask_continue(self, action):
        # Show a OK/Cancel messagebox to the user
        if "message" not in action:
            self._log(f"ERROR: Missing message in ask_continue action {action}")
            raise Exception(f"Missing message in ask_continue action {action}")
        self._log(f"INFO: Showing ask/continue message: {action['message']}")
        
        if not messagebox.askokcancel("Confirmation", self._replace_variables(action['message'])):
            self._log(f"INFO: User cancelled the dialog.")
            raise Exception(f"User cancelled the dialog.")
        else:
            self._log(f"INFO: User confirmed the dialog.")

        return

    def _message(self, message):
        # Show a OK messagebox to the user
        self._log(f"INFO: Showing message: {message}")
        #messagebox.showinfo("Information", self._replace_variables(message))
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Information", self._replace_variables(message))
        root.destroy()

    def _action_message(self, action):
        # Show a OK messagebox to the user
        if "message" not in action:
            self._log(f"ERROR: Missing message in message action {action}")
            raise Exception(f"Missing message in message action {action}")
        self._message(self._replace_variables(action['message']))

    def _action_find_folder(self, action):
        """
        Executes the 'find_folder' action defined in the configuration.

        This function iterates through various methods specified in the 'find_methods' list of the action argument.
        It attempts to locate a folder either by checking predefined file paths or by asking the user to select a folder manually.
        If a valid folder is found, the path is saved to the variable specified in 'save_path_to_variable'.
        In case of failure, the function processes the defined 'error_actions'.

        Args:
            action (dict): A dictionary containing the 'find_folder' action details, including 'find_methods',
                        'save_path_to_variable', and 'error_actions'.

        Returns:
            str: The path of the found folder, or raises an exception if the folder is not found.

        Raises:
            Exception: If the folder is not found and the 'abort' action is specified in 'error_actions'.
        """
        if "find_methods" not in action:
            self._log(f"ERROR: Missing find_methods in find_folder action {action}")
            raise Exception(f"Missing find_methods in find_folder action {action}")
        if "save_path_to_variable" not in action:
            self._log(f"ERROR: Missing save_path_to_variable in find_folder action {action}")
            raise Exception(f"Missing save_path_to_variable in find_folder action {action}")

        find_methods = action['find_methods']
        result_folder = None
        for method in find_methods:
            if 'file_path' in method:
                self._log(f"INFO: Checking if fixed path is valid folder: {method['file_path']}")
                file_path = method['file_path']
                if os.path.exists(file_path):
                    # Convert the filepath to just the folder
                    result_folder = os.path.dirname(file_path)
                    break
            
            elif "uninstall_display_name" in method:
                # Path is usually:
                #   Computer\HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 489830
                #      InstallLocation=<game folder>
                #      DisplayName="The Elder Scrolls V: Skyrim Special Edition"

                # Get the uninstall name
                uninstall_display_name = method["uninstall_display_name"]
                self._log(f"INFO: Searching for uninstall_display_name to find folder: {uninstall_display_name}")
                install_location = None
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Microsoft\Windows\\CurrentVersion\\Uninstall") as key:
                        for i in range(0, winreg.QueryInfoKey(key)[0]):
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                try:
                                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                    if display_name == uninstall_display_name:
                                        self._log(f"INFO: Found uninstall_display_name: {uninstall_display_name}")
                                        values = winreg.QueryValueEx(subkey, "InstallLocation")
                                        if len(values) > 0:                                            
                                            install_location = values[0]
                                            break
                                except FileNotFoundError:
                                    pass
                except FileNotFoundError:
                    pass

                if install_location is not None:
                    self._log(f"INFO: Found install_location using uninstall registry: {install_location}")
                    result_folder = install_location
                    break
                
            elif 'ask' in method:
                # Create a Tkinter dialog to ask the user for the folder
                while True:
                    root = tk.Tk()
                    root.withdraw()  # Hide the Tkinter root window
                    chosen_folder = filedialog.askdirectory(title=method['ask'])
                    root.destroy()
                    if chosen_folder:
                        self._log(f"INFO: User selected folder: {chosen_folder}")
                        # Verify the file exsists in the folder
                        if "file_that_must_exist_in_folder" in action:
                            file_that_must_exist_in_folder = action["file_that_must_exist_in_folder"]
                            if os.path.exists(os.path.join(chosen_folder, file_that_must_exist_in_folder)):
                                self._log(f"INFO: File {file_that_must_exist_in_folder} exists in the chosen folder {chosen_folder}.")
                                result_folder = chosen_folder
                                break
                            else:
                                self._log(f"WARNING: File {file_that_must_exist_in_folder} does not exist in folder {chosen_folder}.")
                                self._message(f"File {file_that_must_exist_in_folder} does not exist in folder {chosen_folder}.")
                    else:
                        # User cancelled the dialog
                        self._log(f"INFO: User cancelled the dialog.")

        # Validate the folder has file_that_must_exist_in_folder
        if "file_that_must_exist_in_folder" in action and result_folder is not None:
            file_that_must_exist_in_folder = action["file_that_must_exist_in_folder"]
            if not os.path.exists(os.path.join(result_folder, file_that_must_exist_in_folder)):
                self._log(f"ERROR: File {file_that_must_exist_in_folder} does not exist in folder {result_folder}.")
                result_folder = None
        
        # Check if the folder was found
        if result_folder is None:
            # Run the error_actions
            self._log(f"ERROR: Folder not found.")
            raise Exception("Folder not found.")
        
        # Success, save the folder path to the variable
        self._log(f"INFO: Folder successfully found: {result_folder}")
        self._set_variable(action['save_path_to_variable'], result_folder)
        
        self._log(f"INFO: Finished find_folder action.")

    def _action_check_executable(self, action):
        # Implement executable checking logic here
        # Placeholder: assume the executable is correct
        pass
    
    def _action_delete_folder(self, action):
        # Delete a folder, but ask for confirmation first
        #   - action: delete_folder
        #       folder: "%LOCALAPPDATA%\\ModOrganizer\\Skyrim Special Edition"
        #       confirm_if_not_partial_match: "ModOrganizer"
        if "folder" not in action:
            self._log(f"ERROR: Missing folder in delete_folder action {action}")
            raise Exception(f"Missing folder in delete_folder action {action}")
        folder = self._replace_variables(action["folder"])

        # Check if the folder exists
        if not os.path.exists(folder):
            self._log(f"INFO: Folder to delete does not exist: {folder}")
            return
        else:
            # Check if confirmation is required
            confirm = False
            if "confirm" in action:
                confirm = action["confirm"]
            
            if "confirm_if_not_partial_match" in action:
                # Check if the filepath has a specific fragment
                partial_pattern = action["confirm_if_not_partial_match"]
                if partial_pattern.lower() not in folder.lower():
                    self._log(f"INFO: Folder to delete does not contain the required fragment: {folder}")
                    
            if confirm:
                # Ask for confirmation
                self._log(f"INFO: Asking for confirmation to delete folder: {folder}")
                if not messagebox.askokcancel("Confirmation", f"Folder '{folder}' exists, but does not contain '{partial_pattern}'. Continue with deleting this whole folder?"):
                    self._log(f"ERROR: User cancelled the folder delete.")
                    raise Exception(f"User cancelled the folder delete.")
                      
            # Delete the folder recursively
            self._log(f"INFO: Deleting folder: {folder}")
            shutil.rmtree(folder)

    def _download_with_selenium(self, url):
        # Implement download logic with selenium here
        # Placeholder: print url
        print("Downloading from:", url)

    def _action_mod_install(self, action):
        pass

    def _set_variable(self, key, value):
        # Set a variable to a value
        self._log(f"INFO: Setting variable {key} to {value}")
        self.variables[key] = value
    
    def _append_variable(self, key, value):
        # Append a value to a variable
        self._log(f"INFO: Appending variable {key} with {value}")
        if key not in self.variables:
            self._set_variable(key, [])
        
        self.variables[key].append(value)

    def _action_abort(self, action):
        # Abort the whole script
        self._log(f"INFO: Aborting the script.")
        sys.exit(0)  # Abort
    
    def _action_set_variable(self, action):
        # Set a variable to a value
        if "name" not in action:
            self._log(f"ERROR: Missing name in set_variable action {action}")
            raise Exception(f"Missing name in set_variable action {action}")
        if "value" not in action:
            self._log(f"ERROR: Missing value in set_variable action {action}")
            raise Exception(f"Missing value in set_variable action {action}")
        self._set_variable(action['name'], action['value'])
    
    def _action_append_variable(self, action):
        # Append a value to a variable
        if "name" not in action:
            self._log(f"ERROR: Missing name in append_variable action {action}")
            raise Exception(f"Missing name in append_variable action {action}")
        if "value" not in action:
            self._log(f"ERROR: Missing value in append_variable action {action}")
            raise Exception(f"Missing value in append_variable action {action}")
        self._append_variable(action['name'], action['value'])
    
    def _run_actions(self, actions):
        self._log(f"INFO: Starting group of {len(actions)} actions.")
        
        # Iterate over each action in the list
        for action in actions:
            if "action" not in action:
                self._log(f"ERROR: Missing action key in action: {action}")
                raise Exception(f"Missing action key in action: {action}")

            action_type = action['action']
            dispatch_table = {
                'ask_continue': self._action_ask_continue,
                'find_folder': self._action_find_folder,
                'check_executable': self._action_check_executable,
                'mod_install': self._action_mod_install,
                'message': self._action_message,
                'abort': self._action_abort,
                'set_variable': self._action_set_variable,
                'append_variable': self._action_append_variable,
                'label': lambda action: None,  # Do nothing
                'delete_folder': self._action_delete_folder,
            }
            if action_type not in dispatch_table:
                self._log(f"ERROR: Unknown action_type: {action_type}")
                raise Exception(f"Unknown action_type: {action_type}")
            
            # Dispatch the action to the corresponding function
            self._log(f"Executing action of type {action_type}: {action}")
            try:
                dispatch_table[action_type](action)

                # Run the success_actions if specified
                if "success_actions" in action:
                    self._log(f"INFO: Running success_actions.")
                    self._run_actions(action['success_actions'])
            except:
                self._log(f"ERROR: Failed to execute action of type {action_type}: {action}")
                # Run the error_actions if specified
                if "error_actions" in action:
                    self._log(f"INFO: Running error_actions.")
                    self._run_actions(action['error_actions'])
                else:
                    self._log(f"WARNING: No error_actions specified for action.")
            
            # Print action completed for demonstration
            self._log(f"Completed action: {action_type}")
        
        self._log(f"INFO: Completed group of {len(actions)} actions.")
    
    def _prerun_actions(self, actions):
        # Run pre-run actions to register some pre-run variables
        for action in actions:
            if "action" not in action:
                self._log(f"ERROR: Missing key action in action: {action}")
                raise Exception(f"Missing key action in action: {action}")
            
            action_type = action['action']
            if action_type == "registered_choice":
                # Register this choice as a variable for a later choice menu
                if "choice_id" not in action:
                    self._log(f"ERROR: Missing choice_id in registered_choice action: {action}")
                    raise Exception(f"Missing choice_id in registered_choice action: {action}")
                if "name" not in action:
                    self._log(f"ERROR: Missing name in registered_choice action: {action}")
                    raise Exception(f"Missing name in registered_choice action: {action}")

                data = {}
                data["name"] = action["name"]
                if "columns" in action:
                    for column in action["columns"]:
                        for key, value in column.items():
                            data[key] = self._replace_variables(value)
                
                self._append_variable(action["choice_id"], data)

            # Process sub-actions
            if "actions" in action:
                self._prerun_actions(action["actions"])
            if "success_actions" in action:
                self._prerun_actions(action["success_actions"])
            if "error_actions" in action:
                self._prerun_actions(action["error_actions"])   
    
    def run(self):
        # Run the main actions
        self._log(f"INFO: Starting main actions.")
        self._run_actions(self.config["actions"])
        self._log(f"INFO: Completed main actions.")
    
    def prerun(self):
        # Run the pre-run actions
        self._log(f"INFO: Starting pre-run actions.")
        self._prerun_actions(self.config["actions"])
        self._log(f"INFO: Completed pre-run actions.")
        self._log(f"INFO: Variables after pre-run: {self.variables}", verbose_only_message=True)

def main():
    # Global variables
    variables = {
        'GAME_PATH': None,
        'DOWNLOAD_CACHE_PATH': None,
        'MO2_EXE_PATH': None,
        'MO2_APPDATA_PATH': None,
    }

    # Load the configuration from YAML
    with open('config.yaml', 'r') as file:
        config = yaml.safe_load(file)

    # Initialize the installer
    installer = SimpleInstaller(config, variables)

    # Execute the installation steps
    installer.prerun()
    installer.run()

if __name__ == "__main__":
    # Initialize Tkinter root for messageboxes
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    # Run the main function
    main()