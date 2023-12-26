import glob
import json
import os
import time
import tkinter as tk
import tkinter.font as tkFont
import winreg
from ttkwidgets import Table
import tkinter as tk
from tkinter import ttk
import ttkwidgets as tw
from tkinter import font
#from ttkwidgets import CheckboxTreeview
import win32api as w
import yaml
from PIL import Image, ImageTk
import webbrowser

from mod import Mod
from mod_group import ModGroup
from PIL import ImageDraw

class CheckboxTreeview(tw.CheckboxTreeview):
    def __init__(self, parent=None, master=None, **kw):
        tw.CheckboxTreeview.__init__(self, master, **kw)
        self.parent_gui = parent

        # Create a font for the hyperlink-like text
        self.hyperlink_font = font.Font(self, family="Helvetica", size=10, underline=True)

        # Hyperlink tag
        self.tag_configure("hyperlink", font=self.hyperlink_font, foreground="blue")

        # Bind events for hyperlink-like behavior
        self.bind("<Motion>", self.on_mouse_motion)
        self.bind("<Button-1>", self.on_treeview_click)

        # Disabled tag to mark disabled items
        self.tag_configure("required_by_parent", foreground='grey')

        # Add selected tag style, background color
        self.tag_configure("selected", background="#000000", foreground="#ffffff")

        # Add highlighted tag style, YELLOW background
        self.tag_configure("highlighted", background="#ffff00")

        # Bind the click event
        self.bind("<ButtonRelease-1>", self._on_mod_selected)

        # Draw a checked checkbox image for when it can't be enabled/disabled
        self.transparent_image = Image.new('RGBA', (12, 12), (255, 255, 255, 0))
        draw = ImageDraw.Draw(self.transparent_image)
        draw.rectangle((0, 0, 12, 12), fill=(0, 0, 0, 0))
        draw.line((3, 6, 5, 8), fill=(120, 120, 120, 255), width=2)
        draw.line((5, 8, 10, 2), fill=(120, 120, 120, 255), width=2)
        self.transparent_photo_checked = ImageTk.PhotoImage(self.transparent_image)

        # Draw a unchecked checkbox image for when it can't be enabled/disabled
        # Draw a small grey x
        self.transparent_image = Image.new('RGBA', (12, 12), (255, 255, 255, 0))
        draw = ImageDraw.Draw(self.transparent_image)
        draw.rectangle((0, 0, 12, 12), fill=(0, 0, 0, 0))
        draw.line((3, 3, 9, 9), fill=(120, 120, 120, 255), width=2)
        draw.line((3, 9, 9, 3), fill=(120, 120, 120, 255), width=2)
        self.transparent_photo_unchecked = ImageTk.PhotoImage(self.transparent_image)

    def insert(self, parent, index, iid=None, **kw):
        if 'tags' in kw and 'required_by_parent' in kw['tags']:
            kw['image'] = self.transparent_photo_checked
        return super().insert(parent, index, iid, **kw)

    def on_mouse_motion(self, event):
        # Change cursor to a hand when over the hyperlink column if it has a\
        # valid "official_website" backing the mod
        region = self.identify("region", event.x, event.y)
        if region == "cell":
            column = self.identify_column(event.x)
            if column == "#1":
                row_id = self.identify_row(event.y)
                name = self.item(row_id).get("values")[0]
                if name in self.parent_gui.mods:
                    mod = self.parent_gui.mods[name]
                    if "official_website" in mod.config:
                        self.config(cursor="hand2")
                    else:
                        self.config(cursor="")
                else:
                    self.config(cursor="")
            else:
                self.config(cursor="")
        else:
            self.config(cursor="")

    def on_treeview_click(self, event):
        # Open a browser when a hyperlink item is clicked
        region = self.identify("region", event.x, event.y)
        if region == "cell":
            column = self.identify_column(event.x)
            if column == "#1":
                row_id = self.identify_row(event.y)
                name = self.item(row_id).get("values")[0]
                if name in self.parent_gui.mods:
                    mod = self.parent_gui.mods[name]
                    url = None
                    if "official_website" in mod.config:
                        self.parent_gui._log(f"INFO: Opening website: {mod.config['official_website']}")
                        url = mod.config["official_website"]
                        if url.startswith("http"):
                            webbrowser.open(url)

        # Call the default behavior
        self._box_click(event)

    # Update the checkbox image when the state changes
    def change_state(self, iid, new_state):
        print(f"change_state: {iid} {new_state}")
        # call super
        super().change_state(iid, new_state)
        
        # If "required_by_parent" tag is present, override images
        if self.tag_has("required_by_parent", iid):
            if new_state == "checked":
                self.item(iid, image=self.transparent_photo_checked)
            elif new_state == "unchecked":
                self.item(iid, image=self.transparent_photo_unchecked)
            else:
                self.item(iid, image=self.transparent_photo_checked)
        else:
            # Handle "only_one_allowed" tag, where only one item can be checked
            # in this group.
            if new_state == "checked" and self.tag_has("only_one_allowed", iid):
                # Uncheck all other items in the group, with preference to whichever
                # item has "checked"
                parent = self.parent(iid)

                # Uncheck all other
                for child in self.get_children(parent):
                    if child != iid:
                        self.change_state(child, "unchecked")
                
                # If there was no preferred item, then use the first item
                #if not preferred_item:
                #    preferred_item = self.get_children(parent)[0]

                # Check the preferred item
                #self.change_state(preferred_item, "checked")

            # Override partially checked state to be checked
            if new_state == "tristate":
                new_state = "checked"

    def _box_click(self, event):
        """Check or uncheck box when clicked."""
        x, y, widget = event.x, event.y, event.widget
        elem = widget.identify("element", x, y)
        if "image" in elem:
            # a box was clicked
            item = self.identify_row(y)
            if self.tag_has("required_by_parent", item):
                return  # do nothing when disabled
            if self.tag_has("unchecked", item) or self.tag_has("tristate", item):
                self._check_ancestor(item)
                self._check_descendant(item)
            elif self.tag_has("checked"):
                self._uncheck_descendant(item)
                self._uncheck_ancestor(item)
    
    def check_item(self, item):
        self.change_state(item, "checked")
        self._check_descendant(item)
        self._check_ancestor(item)
    
    def _on_mod_selected(self, event):
        # Apply selected style to clicked on row
        item = self.identify_row(event.y)
        if item:
            # Remove selected style from all other rows
            def remove_tag(items):
                for item in items:
                    self.tag_del(item, "selected")
                    remove_tag(self.get_children(item))
            
            remove_tag(self.get_children())

            # Add selected style to clicked on row                    
            self.selection_set(int(item))
            self.tag_add(item, "selected")

class App:
    def __init__(self, root):
        self.log_file = open("log.txt", "w", encoding="utf8")

        #### Setup TkIter GUI ####
        root.title("Skyrim EasyInstall")
        width=1200
        height=577
        screenwidth = root.winfo_screenwidth()
        screenheight = root.winfo_screenheight()
        alignstr = '%dx%d+%d+%d' % (width, height, (screenwidth - width) / 2, (screenheight - height) / 2)
        root.geometry(alignstr)
        root.resizable(width=False, height=False)
        self.original_data = {}

        label_info=tk.Label(root)
        label_info["text"] = "Your setup:"
        label_info.place(x=-80,y=0,width=236,height=30)

        text_info=tk.Text(root)
        text_info["borderwidth"] = "1px"
        ft = tkFont.Font(family='Times',size=10)
        text_info["font"] = ft
        text_info["fg"] = "#333333"
        text_info.place(x=10,y=30,width=250,height=500)
        self.text_info = text_info

        label_tree_mods=tk.Label(root)
        ft = tkFont.Font(family='Times',size=10)
        label_tree_mods["font"] = ft
        label_tree_mods["fg"] = "#333333"
        label_tree_mods["justify"] = "left"
        label_tree_mods["text"] = "Choose which EasyInstall initial setup components you'd like to use to create your MO2 profile:"
        label_tree_mods.place(x=270,y=0,width=600,height=30)

        # Initialize the CheckboxTreeview
        columns = ["Name", "Description"]
        tree_mods = CheckboxTreeview(self, root, columns=columns, height=6)
        tree_mods.place(x=270, y=30, width=925, height=500)

        # Configure the tree column to be narrow
        tree_mods.heading('#0', text='')  # Heading for the tree column (checkboxes)
        tree_mods.column('#0', width=95, stretch=tk.NO)
        tree_mods.heading('Name', text='Name')
        tree_mods.column('Name', width=150, stretch=tk.NO)
        tree_mods.heading('Description', text='Description') # fill this column
        tree_mods.column('Description', width=200, stretch=tk.YES)
        # Change the style of the name columns to look like a blue hyperlink
        tree_mods.tag_configure("Name", foreground="#0000EE")

        self.tree_mods = tree_mods

        button_build_mo2_profile=tk.Button(root)
        button_build_mo2_profile["justify"] = "center"
        button_build_mo2_profile["text"] = "[RUN] Create MO2 profile with selected mods"
        button_build_mo2_profile.place(x=750,y=540,width=291,height=30)
        button_build_mo2_profile["command"] = self.onclick_build_mo2_profile

        button_cleanup_mo2=tk.Button(root)
        button_cleanup_mo2["justify"] = "center"
        button_cleanup_mo2["text"] = "Clean EasySetup MO2 profile\n(deletes all mods from profile)"
        button_cleanup_mo2.place(x=450,y=540,width=293,height=30)
        button_cleanup_mo2["command"] = self.onclick_cleanup_mo2

        button_cleanup_skyrim=tk.Button(root)
        button_cleanup_skyrim["justify"] = "center"
        button_cleanup_skyrim["text"] = "Clean Skyrim game folder\n(deletes all non-official files)"
        button_cleanup_skyrim.place(x=180,y=540,width=269,height=30)
        button_cleanup_skyrim["command"] = self.onclick_cleanup_skyrim

        #### End TkIter GUI setup ####
        header_prefix = "✦✧✦ "  # Decorative stars
        header_suffix = " ✦✧✦"
        header_prefix = ""
        header_suffix = ""
        decorative_line = "────────────────────────"  # Using em dash for a line

        # Load saved variables from "save.json"
        self.folder_skyrim = None
        self.folder_mo2 = None
        if os.path.exists("save.json"):
            with open("save.json", "r", encoding="utf8") as f:
                self._log(f"INFO: Loading save.json")
                data = json.load(f)
                for key, value in data.items():
                    if key == "folder_skyrim":
                        self.folder_skyrim = value
                    elif key == "folder_mo2":
                        self.folder_mo2 = value

        # Load the game folder
        self.load_game_folder()
        self.text_info.insert(tk.END, f"{decorative_line}\n")
        self.text_info.insert(tk.END, f"{header_prefix}✦✧✦ Skyrim ✦✧✦{header_suffix}\n")
        self.text_info.insert(tk.END, f"{header_prefix}Version:{header_suffix}\n")
        self.text_info.insert(tk.END, f"{self.version_skyrim}\n\n")
        self.text_info.insert(tk.END, f"{header_prefix}Folder:{header_suffix}\n")
        self.text_info.insert(tk.END, f"{self.folder_skyrim}\n")
        self.text_info.insert(tk.END, f"{decorative_line}\n")

        # Load the MO2 folder
        self.load_mo2_folder()
        self.text_info.insert(tk.END, f"{header_prefix}✦✧✦ Mod Organizer 2 ✦✧✦{header_suffix}\n")
        self.text_info.insert(tk.END, f"{header_prefix}Folder:{header_suffix}\n")
        self.text_info.insert(tk.END, f"{self.folder_mo2}\n\n")
        
        # Set the MO2 profile instance
        self.text_info.insert(tk.END, f"{header_prefix}EasyInstall instance:{header_suffix}\n")
        self.text_info.insert(tk.END, f"{self.folder_mo2_appdata}\n")
        self.text_info.insert(tk.END, f"{decorative_line}\n")

        # Load the download cache folder as a %temp% folder
        self.folder_download_cache = os.path.join(os.getenv("TEMP"), "Skyrim EasyInstall")
        # Make the folder if it doesn't exist
        if not os.path.exists(self.folder_download_cache):
            os.makedirs(self.folder_download_cache)
        self.text_info.insert(tk.END, f"{header_prefix}✦✧✦ Download cache ✦✧✦{header_suffix}\n")
        self.text_info.insert(tk.END, f"{header_prefix}Number of mods:{header_suffix}\n")
        self.text_info.insert(tk.END, f"{len(os.listdir(self.folder_download_cache))}\n\n")
        self.text_info.insert(tk.END, f"{header_prefix}Size:{header_suffix}\n")
        self.text_info.insert(tk.END, f"{os.path.getsize(self.folder_download_cache) / 1024 / 1024 / 1024:.2f} GB\n\n")
        self.text_info.insert(tk.END, f"{header_prefix}Folder:{header_suffix}\n")
        self.text_info.insert(tk.END, f"{self.folder_download_cache}\n")
        self.text_info.insert(tk.END, f"{decorative_line}\n")

        # Save specific variables to "save.json"
        with open("save.json", "w", encoding="utf8") as f:
            self._log(f"INFO: Saving save.json")
            json.dump({"folder_skyrim": self.folder_skyrim,
                       "folder_mo2": self.folder_mo2}, f, indent=4)

        self.load_mods()
        self.load_mod_groups()

        # Populate the top-level mod-groups into the tree.
        # Use mod_group.gui_order_in_table to order them.
        self.iid_to_name = {}
        self.iid_to_table_data = {}
        ordered_mod_groups = sorted(self.mod_groups.values(), key=lambda mod_group: mod_group.gui_order_in_table)
        for mod_group in ordered_mod_groups:
            if mod_group.gui_show_in_table:
                table_data = mod_group.get_tree_data(None, False, self.mods, self.mod_groups, self.iid_to_name)

                for data in table_data:
                    print(data)
                    # Add some tags
                    tags_to_add = []
                    tags = data["tags"] if "tags" in data else []

                    if "required_by_parent" in tags:
                        tags_to_add.append("disabled")
                    
                    if "highlighted" in tags:
                        tags_to_add.append("highlighted")
                    
                    self.tree_mods.insert(data["parent"] or "", 'end', iid=data["iid"], text='', values=data["values"], tags=tags[:])
                    self.iid_to_table_data[data["iid"]] = data
                
                # Check the first item in the mod group
                if len(table_data) > 0 and mod_group.gui_checked_by_default == True:
                    self.tree_mods.check_item(table_data[0]["iid"])
        
        # Expand all the items in the tree view recursively
        def expand_all(items):
            for item in items:
                self.tree_mods.item(item, open=True)
                expand_all(self.tree_mods.get_children(item))
        
        expand_all(self.tree_mods.get_children())
    

    def _check_changed_state(self, iid, state):
        # If it was checked, then apply the check, then
        # apply the default "checked" state according to the
        # children's config
        if state == "checked":
            self.tree_mods.change_state(iid, "checked")

            # Now loop through the children and check them according to their config
            for child in self.tree_mods.get_children(iid):
                mod_table_data = self.iid_to_table_data[int(child)]
                if "unchecked" in mod_table_data["tags"]:
                    self.tree_mods.change_state(child, "unchecked")
                    self._check_changed_state(child, "unchecked")
                else:
                    self.tree_mods.change_state(child, "checked")
                    self._check_changed_state(child, "checked")

    def _log(self, message, verbose_only_message=False):
        # Log with timestamp
        if not verbose_only_message or "about" in self.config and "verbose" in self.config["about"] and self.config["about"]["verbose"]:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
        
        if self.log_file:
            self.log_file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
            self.log_file.flush()

    def load_mods(self):
        # Load all the mods from ./templates/mods/*.yaml
        self.mods = {} # Key: mod name, Value: Mod object
        glob_pattern = os.path.join("templates", "mods", "*.yaml")
        self._log(f"INFO: Loading mods from {glob_pattern}")
        for filename in glob.glob(glob_pattern):
            self._log(f"INFO: Loading mod from {filename}")
            configs = None
            try:
                with open(filename, "r", encoding="utf8") as f:
                    configs = yaml.safe_load(f)
            except Exception as e:
                self._log(f"ERROR: Failed to load YAML mod from {filename}: {e}")
                continue
            if not configs:
                self._log(f"ERROR: Failed to load mod from {filename}")
                continue
            
            for config in configs:
                mod = Mod(config, self._log, self.folder_download_cache)
                self.mods[mod.name] = mod
        
        self._log(f"INFO: Loaded {len(self.mods)} mods")
    
    def load_mod_groups(self):
        # Load all the mod groups from ./templates/mod_groups/*.yaml
        self.mod_groups = {} # Key: mod group name, Value: ModGroup object
        glob_pattern = os.path.join("templates", "mod_groups", "*.yaml")
        self._log(f"INFO: Loading mod groups from {glob_pattern}")
        for filename in glob.glob(glob_pattern):
            self._log(f"INFO: Loading mod group from {filename}")
            configs = None
            try:
                with open(filename, "r", encoding="utf8") as f:
                    configs = yaml.safe_load(f)
            except Exception as e:
                self._log(f"ERROR: Failed to load YAML mod group from {filename}: {e}")
                continue

            if not configs:
                self._log(f"ERROR: Failed to load mod group from {filename}")
                continue
            
            for config in configs:
                mod_group = ModGroup(config, self._log)
                self.mod_groups[mod_group.name] = mod_group
        
        self._log(f"INFO: Loaded {len(self.mod_groups)} mod groups")
            



    def load_mo2_folder(self):
        # Use predefined locations to find the MO2 folder
        # If that fails, ask the user to select the folder.
        # If the user cancels, exit the program.
        validation_filename = "ModOrganizer.exe"
        self.folder_mo2 = None

        if self.folder_mo2 and os.path.exists(os.path.join(self.folder_mo2, validation_filename)):
            self._log(f"INFO: Using saved MO2 folder: {self.folder_mo2}")
        else:
            # Try some pre-defined locations
            self._log(f"INFO: Searching for MO2 folder")
            for location in ["C:\\Modding\MO2",
                            "D:\\Modding\MO2",
                            "E:\\Modding\MO2",
                            "F:\\Modding\MO2",
                            "G:\\Modding\MO2",
                            "H:\\Modding\MO2",]:
                if os.path.exists(location) and os.path.exists(os.path.join(location, validation_filename)):
                    self._log(f"INFO: Found MO2 folder: {location}")
                    self.folder_mo2 = location
                    break
            
            while not self.folder_mo2 or not os.path.exists(os.path.join(self.folder_mo2, validation_filename)):
                self._log(f"INFO: Pre-defined locations failed, asking user to select MO2 folder")
                self.folder_mo2 = tk.filedialog.askdirectory(title="Select the ModOrganizer 2 (MO2) folder (where ModOrganizer.exe is located). If you have not installed it yet, install the latest version using the Nexus Mods link athttps://www.modorganizer.org/.")
                if not self.folder_mo2:
                    self._log(f"INFO: User cancelled MO2 folder selection")
                    exit(0)
        
        self._log(f"INFO: Found MO2 folder: {self.folder_mo2}")

        # Load the appdata folder
        self.folder_mo2_appdata = os.path.join(os.getenv("APPDATA"), "ModOrganizer", "Skyrim EasyInstall")
        # Make the folder if it doesn't exist
        if not os.path.exists(self.folder_mo2_appdata):
            os.makedirs(self.folder_mo2_appdata)
        self._log(f"INFO: Set appdata MO2 folder: {self.folder_mo2_appdata}")
        
    def load_game_folder(self):
        # Load the game folder from the uninstall registry first
        # If that fails, check some pre-defined locations,
        # then ask the user to select the folder.
        # If the user cancels, exit the program.
        # Get the uninstall name
        validation_filename = "SkyrimSE.exe"
        def is_valid_install_location(install_location):
            return os.path.exists(os.path.join(install_location, validation_filename))
        uninstall_display_name = "The Elder Scrolls V: Skyrim Special Edition"

        if self.folder_skyrim and is_valid_install_location(self.folder_skyrim):
            self._log(f"INFO: Using saved game folder: {self.folder_skyrim}")
            install_location = self.folder_skyrim
        else:
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

        # Validate the install location
        if install_location and not is_valid_install_location(install_location):
            install_location = None
            self._log(f"INFO: Found uninstall_display_name, but install_location is invalid: {install_location}")
            
        if not install_location:
            self._log(f"INFO: Registry search failed, trying pre-defined locations")

            # Try some pre-defined locations
            self._log(f"INFO: Searching for validation_filename to find folder: {validation_filename}")
            for location in ["C:\\Program Files (x86)\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "C:\\Program Files\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "D:\\Program Files (x86)\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "D:\\Program Files\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "E:\\Program Files (x86)\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "E:\\Program Files\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "F:\\Program Files (x86)\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "F:\\Program Files\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "G:\\Program Files (x86)\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "G:\\Program Files\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "H:\\Program Files (x86)\\Steam\\steamapps\\common\\Skyrim Special Edition",
                             "H:\\Program Files\\Steam\\steamapps\\common\\Skyrim Special Edition",]:
                if os.path.exists(location) and os.path.exists(os.path.join(location, validation_filename)):
                    self._log(f"INFO: Found validation_filename: {validation_filename}")
                    install_location = location
                    break
        
        # Ask the user to select the folder until they cancel or select the right folder
        while not install_location or not is_valid_install_location(install_location):
            self._log(f"INFO: Asking user to select game folder")
            install_location = tk.filedialog.askdirectory(title="Select the Skyrim Special Edition game folder (where SkyrimSE.exe is located)")
            if not install_location:
                self._log(f"INFO: User cancelled game folder selection")
                exit(0)
        
        self._log(f"INFO: Found game folder: {install_location}")
        self.folder_skyrim = install_location

        # Now check the game version
        self._log(f"INFO: Checking game version")
        version_file = os.path.join(self.folder_skyrim, "SkyrimSE.exe")
        version = w.GetFileVersionInfo(version_file, "\\")
        version_ms = version["FileVersionMS"]
        version_ls = version["FileVersionLS"]
        version = (version_ms >> 16, version_ms & 0xFFFF, version_ls >> 16, version_ls & 0xFFFF)
        version = ".".join(map(str, version))
        self._log(f"INFO: Game version: {version}")
        self.version_skyrim = version

    def onclick_build_mo2_profile(self):
        print("command")

    def onclick_cleanup_mo2(self):
        print("command")

    def onclick_cleanup_skyrim(self):
        print("command")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
