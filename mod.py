import asyncio
import atexit
import json
import re
from subprocess import SW_HIDE
import time
import requests
import os
import win32com
import yaml
import threading
from selenium_profiles.webdriver import Chrome # pip install selenium-profiles
from selenium_profiles.profiles import profiles
from selenium_driverless.webdriver import ChromeOptions # pip install selenium-driverless>=1.3.4
from selenium_driverless.types.by import By
import win32gui

class Mod:
    # Class-wide lock for shared resources
    class_lock = threading.Lock()
    nexus_api_key = None
    driver = None
    driver_lock = threading.Lock()
    driver_handle = None

    @classmethod
    def cleanup_driver(cls):
        with cls.driver_lock:
            if cls.driver is not None:
                # Unhide the browser
                if cls.driver_handle is not None:
                    win32gui.ShowWindow(cls.driver_handle, 5) # SW_SHOW = 5

                # Quit
                cls.driver.quit()
                # Reset the driver
                cls.driver = None
                # Sleep 5 seconds
                time.sleep(5)

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
        self.filesize = None

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

    def _handle_download(self, url, response, filename):
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
            self.file = os.path.join(self.cache_folder, filename_final)
            self.filesize = filesize
            return True
        
        return False

    def _google_drive_download(self, url):
        # Download the file to the cache folder
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
            
            return self._handle_download(url, response, filename)
        except Exception as e:
            self.logger("Failed to download {} from {}".format(self.name, url))
            self.logger(e)
            self.download_failed = True
            return False

    def _nexus_download(self, url):
        # Automate a nexus download through Selenium
        with Mod.driver_lock:
            if Mod.driver is None:
                self.logger("INFO: Logged in Nexus browser session required to start Nexus downloads, launching browser.")

                # Create a chrome driver with GUI, and get the user to login to Nexus Mods
                profile = profiles.Windows()  # or .Android
                options = ChromeOptions()

                
                prefs = {
                    "download_restrictions": 3, # Disable browser downloads
                    "credentials_enable_service": False, # Disable password manager popup
                    "profile.password_manager_enabled": False, # Disable password manager popup
                }
                options.add_experimental_option(
                    "prefs", prefs
                )

                # options.add_argument("--headless=new")
                Mod.driver = Chrome(profile, options=options, driverless_options=True)
                
                # Register cleanup at exit
                atexit.register(Mod.cleanup_driver)
                
                # Login to Nexus Mods
                Mod.driver.get("https://users.nexusmods.com/auth/sign_in")

                # Wait for the user to login, show a TKinter window with spinning wheel until the user logs in

                # Create the TKinter window
                import tkinter as tk
                from tkinter import ttk
                window = tk.Tk()
                window.title("Please login to Nexus Mods")
                window.geometry("300x140")
                window.resizable(False, False)
                # Center the window on the screen
                window.eval('tk::PlaceWindow . center')
                # Create the spinner
                spinner = ttk.Progressbar(window, orient=tk.HORIZONTAL, length=100, mode='indeterminate')
                spinner.pack(pady=10)
                # Add a text box below it
                text = tk.Label(window, text="Please login to Nexus Mods with the browser.\nThis is needed so that mods can be downloaded.\n\n(During downloads you may see a\n'Blocked by your organization' popup, just ignore it.")
                text.pack(pady=10)
                # Make it float above all other windows
                window.attributes("-topmost", True)
                # Start the spinner
                spinner.start()

                # Callback for when login completes
                def login_complete():
                    # Stop the spinner
                    spinner.stop()
                    # Close the window
                    window.destroy()
                
                # Check if the user is logged in every 0.5 seconds
                def check_login():
                    # Check if the user is logged in
                    if Mod.driver.current_url in ["https://www.nexusmods.com/", "https://users.nexusmods.com/account/profile"]:
                        # User is logged in
                        self.logger("INFO: Nexus login success.")
                        login_complete()
                    else:
                        # User is not logged in
                        window.after(500, check_login)

                # Check if the user is logged in every 0.5 seconds
                window.after(500, check_login)

                # Start the TKinter window
                window.mainloop()

                # Now hide the window of the driver to run in the background
                handle = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(handle)
                self.logger(f"INFO: Hiding window with title {title}")
                if "Nexus" in title and "Google Chrome" in title:
                    Mod.driver_handle = handle
                    pass
                    #win32gui.ShowWindow(handle, SW_HIDE)
        
            # Download the file to the cache folder
            self.logger("INFO: Starting nexus download for {}".format(self.name))

            # Load the download page to get a download link
            Mod.driver.get(url)
            Mod.driver.sleep(0.5)

            # Wait until either the download button appears, or "Log in here" appears
            download_url = None
            start_time = time.time()
            retry_count = 0
            while True:
                # If it's been more than 120 seconds, retry up to 3 times
                if time.time() - start_time > 120.0:
                    if retry_count > 3:
                        self.logger(f"ERROR: Nexus download failed for mod {self.name} for url {url} after {retry_count} retries.")
                        return False
                    else:
                        retry_count += 1
                        self.logger(f"INFO: Nexus download timed out, retrying {retry_count} of 3.")
                        # Reload the page
                        Mod.driver.get(url)
                        Mod.driver.sleep(1)
                        start_time = time.time()

                # Find "Log in here" by finding link <a> of class "replaced-login-link"
                try:
                    #elem = Mod.driver.find_element(By.XPATH, '/html/body/div[2]/div/main/p[2]/a', timeout=10)
                    elem = Mod.driver.find_element(By.XPATH, "//a[@class='replaced-login-link']", timeout=0.1)
                    self.logger(f"INFO: Found login link {elem.text}")
                    #elem.click()
                    # Better way to click
                    Mod.driver.execute_script("arguments[0].click();", elem)
                    Mod.driver.find_element(By.XPATH, "//a[text()='Continue']", timeout=2)
                except:
                    pass

                try:
                    # Click "Continue" <a> link
                    elem = Mod.driver.find_element(By.XPATH, "//a[text()='Continue']", timeout=0.1)
                    self.logger(f"INFO: Found continue link {elem.text}")
                    #elem.click()
                    Mod.driver.execute_script("arguments[0].click();", elem)
                    Mod.driver.sleep(1)

                    # Navigate back to the download page
                    Mod.driver.get(url)
                    Mod.driver.find_element(By.ID, "slowDownloadButton", timeout=1)
                except:
                    pass

                # Find the "Slow download" button id and click it
                try:
                    # id="slowDownloadButton" and contains a span with text "Slow download"
                    # Find by the id
                    elem = Mod.driver.find_element(By.ID, "slowDownloadButton", timeout=0.1)
                    #elem = Mod.driver.find_element(By.XPATH, "//span[text()='Slow download']/..", timeout=0.1)
                    self.logger(f"INFO: Found slow download button {elem.text}")
                    Mod.driver.sleep(0.3) # Extra delay to populate the download button
                    #elem = Mod.driver.find_element(By.XPATH, "//span[text()='Slow download']/..", timeout=0.1)
                    elem = Mod.driver.find_element(By.ID, "slowDownloadButton", timeout=0.1)
                    # Click the button
                    #elem.click()
                    Mod.driver.execute_script("arguments[0].click();", elem)
                    Mod.driver.sleep(0.1)

                    # Wait for download link
                    elem = Mod.driver.find_element(By.XPATH, "//a[text()='click here' and contains(@href, 'nexus')]", timeout=30)
                except:
                    pass
                
                # Find the actual download link
                try:
                    # Wait for the actual download link url to appear
                    # <a> link with text "click here" going to *nexusmods.com*
                    elem = Mod.driver.find_element(By.XPATH, "//a[text()='click here' and contains(@href, 'nexus')]", timeout=0.1)
                    self.logger(f"INFO: Found download link {elem.text}")
                    download_url = elem.get_attribute("href")

                    # Navigate back to the mod page, so that the auto-download doesn't start
                    Mod.driver.get(url)                    
                    break
                except:
                    pass

            self.logger(f"INFO: Downloading {self.name} from {download_url}")

            # Download the file
            response = requests.get(download_url, stream=True)
            if response.status_code != 200:
                self.logger(f"ERROR: Nexus download failed for mod {self.name} for url {url}.")
                return False
            
            if "Content-Type" not in response.headers or "application" not in response.headers["Content-Type"]:
                self.logger(f"ERROR: Unexpected content-type for url {url}.")
                self.logger(response.headers)
                return False
            
            # Load the filename from the url
            # url like: https://cf-files.nexusmods.com/cdn/1704/11669/MfgFix-11669-1-6-1-1664520342.7z?md5=_5zdEu9e-iODWIrMDWBaGw&expires=1703716874&user_id=9747136&rip=24.146.109.9
            # or: https://supporter-files.nexus-cdn.com/1704/21423/A.%20Noble%20Skyrim%20-%20FULL%20PACK_2K-21423-5-5-0-1543032385.7z?md5=YANNssVLLuhip4F88akxHg&expires=1703722261&user_id=9747136&rip=24.146.109.9
            filename = download_url.split("/")[-1].split("?")[0]
            # unescape
            filename = requests.utils.unquote(filename)

            return self._handle_download(url, response, filename)

    def _download_urls(self, urls):
        # Download the file
        with self.lock:
            self.download_in_progress = True
            self.download_complete = False
            self.download_failed = False
            self.download_progress = 0.0
        
        # Attempt to load it from the cache for any of the urls
        for url in urls:
            # Check if the file is already downloaded and registered in the cache registry
            registry = {}
            with self.class_lock:
                if os.path.exists(os.path.join(self.cache_folder, "cache_registry.json")):
                    registry = json.load(open(os.path.join(self.cache_folder, "cache_registry.json"), "rb"))
            if url in registry:
                # Check if the file exists
                filename = registry[url]["filename"]
                if os.path.exists(os.path.join(self.cache_folder, filename)):
                    self.logger("INFO: File {} already downloaded, using cached value.".format(filename))
                    self.file = os.path.join(self.cache_folder, filename)
                    self.filesize = registry[url]["filesize"]
                    with self.lock:
                        # Successfully downloaded
                        self.download_in_progress = False
                        self.download_failed = False
                        self.download_complete = True
                        return True
                else:
                    self.logger("INFO: File in cache registry, but file it points to of {} not found".format(filename))
                    del registry[url]
                    with self.class_lock:
                        json.dump(registry, open(os.path.join(self.cache_folder, "cache_registry.json"), "w"), indent=4)

        # Now try to download the file since it's not in the cache
        download_success = False
        for url in urls:
            self.logger("INFO: Attempting to download {} from {}".format(self.name, url))

            # Download the file
            if url.startswith("https://drive.google.com"):
                if self._google_drive_download(url):
                    download_success = True
                    break
            elif url.startswith("https://www.nexusmods.com"):
                # Nexus
                if self._nexus_download(url):
                    download_success = True
                    break
            else:
                raise Exception(f"Unknown download url type {url} for mod {self.name}. Must be a google drive or nexus url.")
            
            self.logger("INFO: Failed to download {} from {}".format(self.name, url))
        
        with self.lock:
            if download_success:
                # Successfully downloaded
                self.download_in_progress = False
                self.download_failed = False
                self.download_complete = True
            else:
                # Failed to download
                self.download_in_progress = False
                self.download_failed = True
                self.download_complete = False
                return False
        
        # Register the file in "cache_registry.json"
        self.logger("INFO: Registering {} in cache_registry.json".format(self.name))
        registry = {}
        with self.class_lock:
            if os.path.exists(os.path.join(self.cache_folder, "cache_registry.json")):
                registry = json.load(open(os.path.join(self.cache_folder, "cache_registry.json"), "rb"))
        registry[url] = {
            "name": self.name,
            "filename": self.file,
            "filesize": self.filesize,
        }
        with self.class_lock:
            json.dump(registry, open(os.path.join(self.cache_folder, "cache_registry.json"), "w"), indent=4)
        self.logger("Registered {} in cache_registry.json".format(self.name))

        return True

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


if __name__ == "__main__":
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
    files = [".\\templates\\mods\\mfg_fix.yaml", ".\\templates\\mods\\qui.yaml", ".\\templates\\mods\\Noble Skyrim Mod HD-2K.yaml"]
    mods = []
    for file in files:
        data = yaml.load(open(file, "rb"), Loader=yaml.FullLoader)[0]
        mod = Mod(data, print, "C:\\temp")
        mod.start_download_async("1.6.629.0")
        mods.append(mod)

    for mod in mods:
        mod.wait_for_download()
        print(mod.file)