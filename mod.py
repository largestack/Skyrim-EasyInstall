import json
import re
import time
import requests
import os
import yaml
import threading


class Mod:
    # Class-wide lock for shared resources
    class_lock = threading.Lock()
    nexus_api_key = None

    '''
    Mod schema is like:
    - name: "BHUNP Body Replacer (UNP Next Generation)"
    description: "Body model for female characters. Needed by lots of mods."
    official_website: https://www.nexusmods.com/skyrimspecialedition/mods/31126
    tag: body-replacer
    only_one_with_tag: body-replacer
    mod_order:
    - after: "RaceMenu"
    install:
    - game_version: *.*.*.*
        urls:
        - https://drive.google.com/file/d/1yEww94rWXUcqYelLuJmDqxeRmdeGmXh9/view?usp=drive_link
        - https://www.nexusmods.com/skyrimspecialedition/mods/31126?tab=files&file_id=453529
    instructions-helpful: |
    Note that you are using a UNP BHUNP body replacer.
    '''
    def __init__(self, config, logger, cache_folder):
        self.config = config
        self.name = None
        self.cache_folder = cache_folder
        self.logger = logger

        self.download_failed = False
        self.download_complete = False
        self.download_progress = 0.0
        self.download_in_progress = False
        self.file = None

        self.lock = threading.Lock()
        
        if 'name' not in config:
            logger("Mod does not have a name")
            raise Exception("Mod does not have a name")
        self.name = config["name"]

        if 'description' not in config:
            logger("Mod {} does not have a description".format(self.name))
            raise Exception("Mod {} does not have a description".format(self.name))
        if 'install' not in config:
            logger("Mod {} does not have a install".format(self.name))
            raise Exception("Mod {} does not have a install".format(self.name))
        
        self.description = config["description"]
    
    def _is_version_check_satisfied(self, version_pattern, version):
        # game_version can be formated like:
        #   1.6.629.0
        #   1.6.629.0+
        #   1.6.*.*
        #   1.6.629.0-1.6.650.0
        def version_to_tuple(v):
            return tuple(map(int, (v.split("+")[0].split("-")[0].split("*")[0].split("."))))

        version_tuple = version_to_tuple(version)
        
        if "+" in version_pattern:
            base_version = version_to_tuple(version_pattern)
            return version_tuple >= base_version
        elif "-" in version_pattern:
            start_version, end_version = map(version_to_tuple, version_pattern.split("-"))
            return start_version <= version_tuple <= end_version
        elif "*" in version_pattern:
            pattern = version_pattern.replace('*', '\d+')
            return re.match(pattern, version) is not None
        else:
            return version_tuple == version_to_tuple(version_pattern)

    def is_compatable(self, game_version):
        for install in self.config['install']:
            if self._is_version_check_satisfied(install['game_version'], game_version):
                return True
        return False

    def _google_drive_download(self, url):
        # Download the file to the cache folder
        self.logger("Downloading {} from {}".format(self.name, url))

        # Check if the file is already downloaded and registered in cache
        registry = {}
        with self.class_lock:
            if os.path.exists(os.path.join(self.cache_folder, "cache_registry.json")):
                registry = json.load(open(os.path.join(self.cache_folder, "cache_registry.json"), "rb"))
        if url in registry:
            # Check if the file exists
            filename = registry[url]["filename"]
            if os.path.exists(os.path.join(self.cache_folder, filename)):
                self.logger("File {} already downloaded, using cached value.".format(filename))
                self.file = os.path.join(self.cache_folder, filename)
                return True
            else:
                self.logger("File in cache registry, but file it points to of {} not found".format(filename))
                del registry[url]
                with self.class_lock:
                    json.dump(registry, open(os.path.join(self.cache_folder, "cache_registry.json"), "w"), indent=4)

        try:
            file_id = url.split("/")[5]
            response = requests.get("https://drive.google.com/uc?export=download&id={}".format(file_id), stream=True)
            if response.status_code != 200:
                self.logger(f"Google drive download failed for mod {self.name} for url {url}.")
                return False
            if "Content-Disposition" in response.headers and "attachment" in response.headers["Content-Disposition"]:
                # Successfully started download!
                pass
            elif response.headers['Content-Type'] == "text/html; charset=utf-8":
                # UX page warning that the file is too large. Need another step to proceed to the download.
                # https://drive.usercontent.google.com/download?id={}&export=download&authuser=0&confirm=t&at=APZUnTUmBxP8DVcYX77oD3S2xiaX%3A1703459418376
                # Need to extract the at token from HTML, eg:
                #       <input type="hidden" name="at" value="APZUnTVXYq1G3fxwMpBboNW9UrP4:1703459695692"></form>
                token = response.text.split("<form>")[-1].split("</form>")[0].split("name=\"at\"")[-1].split("value=")[-1].split('"')[1]
                if token is None:
                    self.logger(f"Google drive download large file download failed for mod {self.name} for url {url}.")
                    return False
                
                response = requests.get("https://drive.google.com/uc?export=download&id={}&authuser=0&confirm=t&at={}".format(file_id, token), stream=True)

                if response.status_code != 200:
                    self.logger(f"Google drive download large file failed for mod {self.name} for url {url}.")
                    return False
                if "Content-Disposition" not in response.headers or "attachment" not in response.headers["Content-Disposition"]:
                    self.logger(f"Unexpected content disposition for url {url}.")
                    return False
            else:
                self.logger(f"Unexpected content type {response.headers['Content-Type']} for url {url}.")
                self.logger(response.headers)
                return False
            
            # Load the filename
            #   'Content-Disposition': 'attachment; filename="MfgFix-11669-1-6-1-1664520342.7z"; filename*=UTF-8\'\'MfgFix-11669-1-6-1-1664520342.7z'
            filename = None
            for key, value in response.headers.items():
                if key == 'Content-Disposition':
                    filename = value.split("filename=")[1].split("\"")[1]
            
            # Load the filesize
            #   'Content-Length': '123456789'
            filesize = None
            for key, value in response.headers.items():
                if key == 'Content-Length':
                    filesize = int(value)
            
            if response.status_code == 200:
                # Once per second, update the download progress variable
                self.download_progress = 0.0
                self.logger("Downloading {} {:.2f}%".format(filename, self.download_progress * 100.0))

                # Download the file
                last_log_time = time.time()
                progress = 0
                with open(os.path.join(self.cache_folder, filename + ".partial"), 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                        # Update progress
                        self.download_progress = float(f.tell()) / filesize
                        # Log the download progress every 5 seconds
                        if time.time() - last_log_time > 5.0:
                            self.logger("Downloading {} {:.2f}%".format(filename, self.download_progress * 100.0))
                            last_log_time = time.time()
                self.logger("Downloading {} {:.2f}%".format(filename, 100.0))
                
                # Use the hash of the url in the cache registry so that multiple game versions can be supported
                url_hash = hex(hash(url))[2:]

                # Rename the file
                extension = filename.split(".")[-1]
                filename_without_extension = ".".join(filename.split(".")[:-1])
                filename_final = f"{filename_without_extension}_{url_hash}.{extension}"
                self.logger(f"Renaming {filename} to {filename_final}")
                
                os.rename(os.path.join(self.cache_folder, filename + ".partial"), os.path.join(self.cache_folder, filename_final))

                # Register the file in "cache_registry.json"
                registry = {}
                with self.class_lock:
                    if os.path.exists(os.path.join(self.cache_folder, "cache_registry.json")):
                        registry = json.load(open(os.path.join(self.cache_folder, "cache_registry.json"), "rb"))
                registry[url] = {
                    "name": self.name,
                    "filename": filename_final,
                    "filesize": filesize,
                }
                with self.class_lock:
                    json.dump(registry, open(os.path.join(self.cache_folder, "cache_registry.json"), "w"), indent=4)
                self.logger("Registered {} in cache_registry.json".format(self.name))
                self.file = os.path.join(self.cache_folder, filename_final)
                return True
            else:
                self.logger(f"Google drive download failed for mod {self.name} for url {url}.")
                return False
        except Exception as e:
            self.logger("Failed to download {} from {}".format(self.name, url))
            self.logger(e)
            self.download_failed = True
            return False

    def _nexus_download(self, url):
        if Mod.nexus_api_key is None:
            # We need to use the browser to get the api key
            """
            https://github.com/Nexus-Mods/sso-integration-demo

            Connect to the SSO service, via a websocket client:

            window.socket = new WebSocket("wss://sso.nexusmods.com");
            Once connected, retrieve the request ID and connection_token used on the previous connection.

            // retrieve previous uuid and token
            uuid = sessionStorage.getItem("uuid");
            token = sessionStorage.getItem("connection_token");
            Or, if this is the first connection, just generate a random uuid, a token is not needed for first connection

            uuid = uuidv4();
            token = null;
            sessionStorage.setItem('uuid', uuid);
            var data = {
                id: uuid,
                token: token,
                protocol: 2
            };

            // Send the request
            socket.send(JSON.stringify(data));
            This has informed the SSO server that we are ready to received the user's approval. Once the request is sent, the SSO will send a message back with the connection_token mentioned above - this is only used on subsequent connections (usually due to disconnects and network errors). The response from the SSO will look something like this:

            {"success":true,"data":{"connection_token":"X5SjO3P4i8tiBgMdYVTCh3z57ZnWVK5z"},"error":null}

            The response will always contain a success attribute, along with error, to be used for error reporting.

            The browser can now be opened and the authorise page can be shown.

            // Open the browser window, using the uuid and your application's reference
            window.open("https://www.nexusmods.com/sso?id="+uuid+"&application="+application_slug);
            Note: an application reference can only be generated by Nexus Mods staff. Please, contact the Community Team for further instructions.

            The user will be shown an 'authorise' page, or the login page if they are not logged in. Once they have authorised the token, the API key will be sent through the websocket in the following format

            {"success":true,"data":{"api_key":"VX2PMnc4T5Q3dUFmjE45WyRyZ3VkKzIvYVJiMUdick5XQU9QWHdUbFo4..."},"error":null}

            This API key can be stored by the client and sent as a header for every HTTP request for the API.
            """
            


        pass

    def _download_urls(self, urls):
        # Download the file
        with self.lock:
            self.download_in_progress = True
            self.download_complete = False
            self.download_failed = False
            self.download_progress = 0.0
        for url in urls:
            if url.startswith("https://drive.google.com"):
                if self._google_drive_download(url):
                    with self.lock:
                        self.download_complete = True
                        self.download_failed = False
                        self.download_in_progress = False
                    return True
            elif url.startswith("https://www.nexusmods.com"):
                # Nexus
                raise Exception(f"Nexus download not implemented for mod {self.name} for url {url}.")
            else:
                raise Exception(f"Unknown download url type {url} for mod {self.name}. Must be a google drive or nexus url.")
        
        with self.lock:
            self.download_in_progress = False
            self.download_failed = True
            self.download_complete = False
        return False

    def start_download_async(self, game_version):
        # Find the download for this game version
        download_urls = None
        for install in self.config['install']:
            if self._is_version_check_satisfied(install['game_version'], game_version):
                download_urls = install['urls']
                break
        
        if download_urls is None:
            self.logger("No download url found for mod {} for game version {}.".format(self.name, game_version))
            raise Exception("No download url found for mod {} for game version {}.".format(self.name, game_version))
        
        #self._download_urls(download_urls)
        # Call _download_urls using a thread
        thread = threading.Thread(target=self._download_urls, args=(download_urls,))
        thread.start()
    
    def wait_for_download(self):
        while True:
            with self.lock:
                if self.download_in_progress is False:
                    return self.download_complete
            time.sleep(0.05)

"""
# test google download
# Small file test
files = [".\\templates\\mods\\mfg_fix.yaml", ".\\templates\\mods\\BHUNP_body_replacer.yaml"]
mods = []
for file in files:
    data = yaml.load(open(file, "rb"), Loader=yaml.FullLoader)[0]
    mod = Mod(data, print, "C:\\temp")
    mod.start_download_async("1.6.629.0")
    mods.append(mod)

for mod in mods:
    mod.wait_for_download()
    print(mod.file)
"""

# test Nexus download
# Small file test
'''
files = [".\\templates\\mods\\mfg_fix.yaml"]
mods = []
for file in files:
    data = yaml.load(open(file, "rb"), Loader=yaml.FullLoader)[0]
    mod = Mod(data, print, "C:\\temp")
    mod.start_download_async("1.6.629.0")
    mods.append(mod)

for mod in mods:
    mod.wait_for_download()
    print(mod.file)
'''