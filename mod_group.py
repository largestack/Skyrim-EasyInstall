import random


class ModGroup:
    '''
    Mod-group schema is like:
      - name: "Skyrim Core Dependencies"
        description: "A collection of mods that are required by many other mods."
        mods:
        - name: "Skyrim Script Extender (SKSE64)"
            required: true
        - name: "Address Library for SKSE Plugins"
            required: true
        - section: "Body Replacer"
            mods:
            only_one_allowed: true
            - name: "Caliente's Beautiful Bodies Enhancer -CBBE-"
            checked: true
            - name: "BHUNP Body Replacer (UNP Next Generation)"
            checked: false
        - name: "UIExtensions"
            required: true
    Note that you are using a UNP BHUNP body replacer.
    '''
    def __init__(self, config, logger):
        # config is a dict
        # mods is a dict of mods {name: Mod}
        if "name" not in config:
            raise Exception("ModGroup config must have a name.")
        if "description" not in config:
            raise Exception("ModGroup config must have a description.")
        if "mods" not in config:
            raise Exception("ModGroup config must have a mods section.")

        self.description = config["description"]
        
        self.gui_show_in_table = False
        if "gui_show_in_table" in config:
            self.gui_show_in_table = config["gui_show_in_table"] == True
        
        self.gui_order_in_table = 1000.0
        if "gui_order_in_table" in config:
            self.gui_order_in_table = config["gui_order_in_table"]
        
        self.gui_checked_by_default = False
        if "gui_checked_by_default" in config:
            self.gui_checked_by_default = config["gui_checked_by_default"] == True
        
        self.name = config['name']
        self.config = config
        self.logger = logger

    def get_tree_data(self, parent_iid, parent_checked, mods, mod_groups, iid_to_name, mod_list_to_process = None):
        '''
        Returns an array of dicts that can be used to populate a tree widget. Keys:
        - parent: the parent item id
        - iid: the item id
        - values: a tuple of (name, description)
        '''
        if "mods" not in self.config:
            return []
        
        results = []
        if mod_list_to_process == None:
            # Add an entry for ourself
            iid = random.randint(0, 1000000000)
            iid_to_name[iid] = self.name
            result = {
                "parent": parent_iid,
                "iid": iid,
                "values": (self.name, self.description),
                "tags": ["TEST"],
            }
            results.append(result)
            parent_iid = iid
        
        # Process the mod list
        mod_list_to_process = mod_list_to_process or self.config["mods"]
        for mod_list_entry in mod_list_to_process:
            additional_results = []
            additional_results_modgroup = None
            iid = None

            tags = []
            if "tags" in mod_list_entry:
                tags = mod_list_entry["tags"]
            
            if 'section' in mod_list_entry:
                # This is a section
                section = mod_list_entry
                iid = random.randint(0, 1000000000)
                iid_to_name[iid] = mod_list_entry["section"]
                result = {
                    "parent": parent_iid,
                    "iid": iid,
                    "values": ("--- " + section["section"] + " ---", section["description"] or ""),
                    "tags": tags,
                }
                additional_results.append(result)
                # Process the mods in this section
                additional_results += self.get_tree_data(iid, parent_checked, mods, mod_groups, iid_to_name, section["mods"])

            elif mod_list_entry["name"] in mods:
                # This is a mod, add it to the list
                mod = mods[mod_list_entry['name']]
                iid = random.randint(0, 1000000000)
                iid_to_name[iid] = mod.name
                result = {
                    "parent": parent_iid,
                    "iid": iid,
                    "values": (mod.name, mod.description),
                    "tags": tags,
                }
                additional_results.append(result)
            
            elif mod_list_entry["name"] in mod_groups:
                # This is a mod group
                mod_group = mod_groups[mod_list_entry['name']]
                additional_results_modgroup = mod_group
            
            # Add to the results
            results += additional_results

            # Now process the children if needed
            checked = parent_checked
            if "unchecked" in tags:
                checked = False
            if "checked" in tags:
                checked = True
            if additional_results_modgroup:
                results += additional_results_modgroup.get_tree_data(parent_iid, checked, mods, mod_groups, iid_to_name)
            
        return results