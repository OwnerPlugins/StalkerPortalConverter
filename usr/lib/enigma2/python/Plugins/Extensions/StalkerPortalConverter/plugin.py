# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function
from . import (
    _, __version__, b64decoder, check_version,
    fetch_system_timezone, get_mounted_devices,
    has_enough_free_space, installer_url, Request,
    requests, urlopen, cleanName,
)
from Tools.Directories import defaultRecordingLocation
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.Console import Console
from Screens.ChoiceBox import ChoiceBox
from Plugins.Plugin import PluginDescriptor
from Components.config import config, configfile, ConfigSelection, ConfigSubsection, ConfigText, ConfigYesNo
from Components.MenuList import MenuList
from Components.Label import Label
from Components.ActionMap import ActionMap

import threading
import time
import random
import unicodedata
import concurrent.futures
from enigma import eDVBDB, eTimer
from hashlib import md5
from json import JSONDecodeError, dumps, loads
from os import (
    chmod, listdir, makedirs, remove, replace, urandom, access, W_OK
)
from os.path import (
    basename, dirname, exists, getsize, isdir, isfile, join,
)
from re import IGNORECASE, compile, search, sub
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread
from urllib.parse import urlencode, urlparse
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from requests.exceptions import RequestException, SSLError
from twisted.web import server, resource
from twisted.internet import reactor
import ssl
import socket
import urllib3

# Disabilita warning SSL per portali con certificati non validi
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


"""
#########################################################
#                                                       #
#  Stalker Portal Converter Plugin                      #
#  Version: 1.4                                         #
#  Created by Lululla (https://github.com/Belfagor2005) #
#  License: CC BY-NC-SA 4.0                             #
#  https://creativecommons.org/licenses/by-nc-sa/4.0    #
#  Last Modified: "21:50 - 20250606"                    #
#                                                       #
#  Credits:                                             #
#  - Original concept by Lululla                        #
#  Usage of this code without proper attribution        #
#  is strictly prohibited.                              #
#  For modifications and redistribution,                #
#  please maintain this credit header.                  #
#########################################################
"""
__author__ = "Lululla"


"""Use mode:
# playlist.txt with case sensitive
# Examples of supported formats:
# Standard format:

# Panel: http://example.com:80/c/
# MAC: 00:1A:79:XX:XX:XX
# Compact format:

# http://example.com/c/ # My Portal
# 00:1A:79:XX:XX:XX
# Multiple MACs per portal:

# Portal: http://server.com:8080/c
# MAC1: 00:1A:79:AA:AA:AA
# MAC2: 00:1A:79:BB:BB:BB
# Unlabeled MAC:

# Panel http://example.com/c
# 00:1A:79:XX:XX:XX
# Portal without explicit MAC:

# http://server1.com/c/
# http://server2.com/c/ # Uses same MAC as server1
# 00:1A:79:XX:XX:XX
"""


def defaultMoviePath():
    result = config.usage.default_path.value
    if not result.endswith("/"):
        result += "/"
    if not isdir(result):
        return defaultRecordingLocation(config.usage.default_path.value)
    return result


def update_mounts():
    mounts = get_mounted_devices()
    if not mounts:
        default_path = defaultMoviePath()
        mounts = [(default_path, default_path)]
    config.plugins.stalkerportal.output_dir.setChoices(
        mounts, default=mounts[0][0])
    config.plugins.stalkerportal.output_dir.save()


# Configuration setup
config.plugins.stalkerportal = ConfigSubsection()
default_dir = config.movielist.last_videodir.value if isdir(
    config.movielist.last_videodir.value) else defaultMoviePath()
config.plugins.stalkerportal.output_dir = ConfigSelection(
    default=default_dir, choices=[])
config.plugins.stalkerportal.input_filelist = ConfigText(
    default="/etc/enigma2")
config.plugins.stalkerportal.type_convert = ConfigSelection(
    default="0",
    choices=[("0", "MAC to M3U"), ("1", "MAC to .tv")]
)
config.plugins.stalkerportal.include_vod = ConfigYesNo(default=True)
config.plugins.stalkerportal.bouquet_position = ConfigSelection(
    default="bottom",
    choices=[("top", _("Top")), ("bottom", _("Bottom"))]
)
config.plugins.stalkerportal.portal_url = ConfigText(
    default="http://my.server.xyz:8080/c/", fixed_size=False)
config.plugins.stalkerportal.mac_address = ConfigText(
    default="00:1A:79:00:00:00", fixed_size=False)
config.plugins.stalkerportal.web_access_code = ConfigText(
    default="", fixed_size=False)

AgentRequest = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.3'

update_mounts()


def reload_services():
    eDVBDB.getInstance().reloadServicelist()
    eDVBDB.getInstance().reloadBouquets()


for path in [
    "/tmp/account_debug.log",
    "/tmp/stalker_convert_info.log",
        "/tmp/stalker_convert.log"]:
    if exists(path):
        try:
            remove(path)
        except Exception as e:
            print("[DEBUG] Failed to remove {}: {}".format(path, e))


class StalkerPortalConverter(Screen):
    skin = """
        <screen name="StalkerPortalConverter" position="center,center" size="1280,720" title="Stalker Portal Converter" backgroundColor="#16000000">
            <widget name="title" position="10,5" size="1260,40" font="Regular;30" halign="center" foregroundColor="#00ffff" />
            <widget name="portal_label" position="10,50" size="300,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="portal_input" position="315,50" size="950,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="mac_label" position="10,80" size="300,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="mac_input" position="315,80" size="950,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="file_label" position="10,140" size="300,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="file_input" position="315,140" size="950,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="file_path_label" position="10,110" size="300,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="file_path_input" position="315,110" size="950,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="user_label" position="10,505" size="200,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="user_value" position="215,505" size="300,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="pass_label" position="535,505" size="200,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="pass_value" position="740,505" size="240,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="expiry_label" position="10,535" size="200,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="expiry_value" position="215,535" size="300,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="status_label" position="535,535" size="200,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="status_value" position="740,535" size="240,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="active_label" position="10,565" size="200,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="active_value" position="215,565" size="300,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="max_label" position="535,565" size="200,30" font="Regular;24" foregroundColor="#ffffff" zPosition="2" />
            <widget name="max_value" position="740,565" size="240,30" font="Regular;24" backgroundColor="#252525" zPosition="2" />
            <widget name="status" position="9,602" size="985,59" font="Regular;24" foregroundColor="#00ff00" halign="center" zPosition="2" />
            <widget name="account_info" position="6,173" size="1260,45" font="Regular;22" foregroundColor="#00ff00" halign="center" zPosition="2" cornerRadius="10" />
            <widget name="portal_list_label" position="8,221" size="1260,30" font="Regular;24" foregroundColor="#ffff00" zPosition="2" />
            <widget name="file_list" position="10,253" size="1260,239" scrollbarMode="showOnDemand" itemHeight="40" font="Regular;28" backgroundColor="#252525" />
            <ePixmap position="10,670" pixmap="skin_default/buttons/red.png" size="30,30" alphatest="blend" zPosition="2" />
            <widget name="key_red" font="Regular;28" position="40,670" size="200,30" halign="left" backgroundColor="black" zPosition="1" transparent="1" cornerRadius="10" />
            <ePixmap position="245,670" pixmap="skin_default/buttons/green.png" size="30,30" alphatest="blend" zPosition="2" />
            <widget name="key_green" font="Regular;28" position="280,670" size="200,30" halign="left" backgroundColor="black" zPosition="2" transparent="1" cornerRadius="10" />
            <ePixmap position="490,670" pixmap="skin_default/buttons/yellow.png" size="30,30" alphatest="blend" zPosition="2" />
            <widget name="key_yellow" font="Regular;28" position="525,670" size="200,30" halign="left" backgroundColor="black" zPosition="2" transparent="1" cornerRadius="10" />
            <ePixmap position="730,670" pixmap="skin_default/buttons/blue.png" size="30,30" alphatest="blend" zPosition="2" />
            <widget name="key_blue" font="Regular;28" position="765,670" size="200,30" halign="left" backgroundColor="black" zPosition="2" transparent="1" cornerRadius="10" />
            <eLabel name="" position="995,664" size="52,40" backgroundColor="#00ffff" foregroundColor="#000000" halign="center" valign="center" transparent="0" cornerRadius="10" font="Regular; 17" zPosition="1" text="OK" />
            <eLabel name="" position="1065,664" size="52,40" backgroundColor="#00ffff" foregroundColor="#000000" halign="center" valign="center" transparent="0" cornerRadius="10" font="Regular; 17" zPosition="1" text="INFO" />
            <eLabel name="" position="1135,664" size="52,40" backgroundColor="#00ffff" foregroundColor="#000000" halign="center" valign="center" transparent="0" cornerRadius="10" font="Regular; 17" zPosition="1" text="EXIT" />
            <widget name="key_web" position="995,620" size="265,44" font="Regular;22" halign="center" backgroundColor="#b3b3b3" foregroundColor="#000000" cornerRadius="10" />
            <eLabel name="" position="1200,664" size="60,40" backgroundColor="#ffff00" foregroundColor="#000000" halign="center" valign="center" transparent="0" cornerRadius="10" font="Regular; 17" zPosition="1" text="TXT WEB" />
            <widget name="access_code_label" position="995,580" size="265,40" font="Regular;22" halign="center" backgroundColor="#ff8080" foregroundColor="#000000" zPosition="2" cornerRadius="10" />
            <widget name="regen_code_btn" position="1047,540" size="213,40" font="Regular;24" halign="center" valign="center" backgroundColor="#00ffff" foregroundColor="#000000" cornerRadius="10" />
            <widget name="show_code_btn" position="1047,500" size="213,40" font="Regular;24" halign="center" valign="center" backgroundColor="#00ffff" foregroundColor="#000000" cornerRadius="10" />
            <eLabel name="" position="995,540" size="52,40" backgroundColor="#00ffff" foregroundColor="#000000" halign="center" valign="center" transparent="0" cornerRadius="10" font="Regular; 24" zPosition="1" text="0" />
            <eLabel name="" position="995,500" size="52,40" backgroundColor="#00ffff" foregroundColor="#000000" halign="center" valign="center" transparent="0" cornerRadius="10" font="Regular; 24" zPosition="1" text="1" />
        </screen>
        """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.portal_list = []
        self.playlist_file = ""
        self.channels = []
        self.account_info_timer = None
        self.account_info_timeout = 15
        self.conversion_stopped = False
        self.conversion_running = False
        self.conversion_timeout = 0
        self.conversion_result = None
        self.closed = False
        self.channel_cache = {}
        self.cache_expiration = 0

        if not config.plugins.stalkerportal.web_access_code.value:
            self.generate_access_code()

        self.stop_timer = eTimer()
        self.stop_timer.timeout.get().append(self.reset_conversion_state)
        self.result_timer = eTimer()
        self.result_timer.timeout.get().append(self.handle_conversion_result)

        self.access_code_timer = eTimer()
        self.access_code_timer.callback.append(self.hide_access_code)
        self.access_code_visible = False

        self.update_timer = eTimer()
        self.update_timer.callback.append(self.check_for_updates)
        self.update_timer.start(2000)

        self.get_output_filename = self._get_output_filename
        self.update_flag_file = "/tmp/stalker_update_flag"

        self["title"] = Label(
            _("Stalker Portal to M3U Converter v.%s") %
            __version__)
        self["portal_label"] = Label(_("Portal URL:"))
        self["portal_input"] = Label(
            config.plugins.stalkerportal.portal_url.value)
        self["mac_label"] = Label(_("MAC Address:"))
        self["mac_input"] = Label(
            config.plugins.stalkerportal.mac_address.value)
        self["file_label"] = Label(_("Output File:"))
        self["file_input"] = Label("")
        self["file_path_label"] = Label(_("Playlist File:"))
        self["file_path_input"] = Label("")
        self["portal_list_label"] = Label(
            _("Valid Portals from Selected File:"))
        self["account_info"] = Label("")
        self["user_label"] = Label(_("User:"))
        self["user_value"] = Label("")
        self["pass_label"] = Label(_("Password:"))
        self["pass_value"] = Label("")
        self["expiry_label"] = Label(_("Expiry:"))
        self["expiry_value"] = Label("")
        self["status_label"] = Label(_("Status:"))
        self["status_value"] = Label("")
        self["active_label"] = Label(_("Active:"))
        self["active_value"] = Label("")
        self["max_label"] = Label(_("Max: "))
        self["max_value"] = Label("")

        self["file_list"] = MenuList([])
        self["status"] = Label(_("Ready - Select a file or enter URL/MAC"))
        self["key_red"] = Label(_("Clear"))
        self["key_green"] = Label(self.get_convert_label())
        self["key_yellow"] = Label(_("Select Playlist"))
        self["key_blue"] = Label(_("Edit"))
        self["key_web"] = Label(_("Web Portal Server Off"))
        self["hint_label"] = Label(
            _("Press 0: Show Access Code | Press 1: New Code"))
        self["access_code_label"] = Label(
            _("Access Code: ") + self.get_masked_access_code())
        self["regen_code_btn"] = Label(_("New Code"))
        self["show_code_btn"] = Label(_("Show Code"))

        self["actions"] = ActionMap(
            ["StalkerPortalConverter"],
            {
                "cancel": self.close,
                "exit": self.close,
                "info": self.show_info,
                "red": self.clear_fields,
                "green": self.convert,
                "yellow": self.select_playlist_file,
                "blue": self.edit_settings,
                "up": self.keyUp,
                "down": self.keyDown,
                "left": self.keyLeft,
                "right": self.keyRight,
                "ok": self.select_portal,
                "web": self.start_web_server,
                "regenCode": self.regenerate_access_code,
                "showCode": self.toggle_access_code_visibility,
            }, -1
        )

        try:
            portal = config.plugins.stalkerportal.portal_url.value
            mac = config.plugins.stalkerportal.mac_address.value
            entry = self.validate_and_add_entry(portal, mac)
            if entry:
                self.portal_list.append(entry)
            display_list = [entry[0] for entry in self.portal_list]
            self["file_list"].setList(display_list)
        except Exception as e:
            print(e)

        self.web_server = None
        self.listening_port = None
        self.onLayoutFinish.append(self.initialize_ui)

    def initialize_ui(self):
        if "file_input" not in self:
            self["file_input"] = Label("")
        self.get_output_filename = self._get_output_filename
        vod_status = _(
            "Enabled") if config.plugins.stalkerportal.include_vod.value else _("Disabled")
        self["status"].setText(_("VOD inclusion: {}").format(vod_status))
        self.update_all_widgets()

    def update_all_widgets(self):
        try:
            configfile.load()
            self["portal_input"].setText(
                config.plugins.stalkerportal.portal_url.value)
            self["mac_input"].setText(
                config.plugins.stalkerportal.mac_address.value)

            output_dir = config.plugins.stalkerportal.output_dir.value
            if not output_dir or not isdir(output_dir):
                output_dir = defaultMoviePath()
                config.plugins.stalkerportal.output_dir.value = output_dir
                configfile.save()

            output_file = self._get_output_filename()
            self["file_input"].setText(output_file)

            playlist_file = self.get_playlist_file_path()
            if hasattr(self, 'playlist_file') and self.playlist_file:
                playlist_file = self.playlist_file
            self["file_path_input"].setText(playlist_file)
            self["key_green"].setText(self.get_convert_label())

            for widget in [
                "portal_input",
                "mac_input",
                "file_input",
                "file_path_input",
                    "key_green"]:
                if widget in self:
                    self[widget].instance.invalidate()

            self.extract_account_info_async()
        except Exception as e:
            print(f"Error updating widgets: {str(e)}")
            self["status"].setText(_("Initialization error"))

    def select_portal(self):
        if self.conversion_running:
            self.conversion_stopped = True
            self["status"].setText(
                _("Stopping current process to switch portal..."))
            start_time = time.time()
            while self.conversion_running and (time.time() - start_time) < 2.0:
                time.sleep(0.1)

        self.conversion_running = False
        self.conversion_stopped = False

        selection = self["file_list"].getCurrent()
        if selection and self.portal_list:
            idx = self["file_list"].getSelectedIndex()
            if idx < len(self.portal_list):
                _display, portal, mac = self.portal_list[idx]
                config.plugins.stalkerportal.portal_url.value = portal
                config.plugins.stalkerportal.mac_address.value = mac
                configfile.save()
                configfile.load()
                self["status"].setText(
                    _("Selected: ") +
                    basename(
                        self.playlist_file))
                self["account_info"].setText("")
                self["user_value"].setText("")
                self["pass_value"].setText("")
                self["expiry_value"].setText("")
                self["status_value"].setText("")
                self["active_value"].setText("")
                self["max_value"].setText("")
                self["status"].setText(
                    _("Loading account info in background..."))
                self.extract_account_info_async()
                self.update_all_widgets()

    def extract_account_info_async(self):
        def worker():
            self.update_account_fields("", "", "", "", "", "")
            info = self.extract_account_info()
            if info:
                self.update_account_fields(
                    info.get("user", "N/A"), info.get("password", "N/A"),
                    info.get("expiry", "N/A"), info.get("status", "N/A"),
                    info.get("active", "N/A"), info.get("max", "N/A")
                )
                self.update_status(_("Account info loaded"))
            else:
                self.update_status(_("Failed to load account info"))
        threading.Thread(target=worker, daemon=True).start()

    def extract_account_info(self):
        try:
            portal = config.plugins.stalkerportal.portal_url.value.strip()
            mac = config.plugins.stalkerportal.mac_address.value.strip()
        except Exception as e:
            self.update_status(
                _("Error accessing configuration values: ") + str(e))
            return None

        if not portal or not mac:
            self.update_status(_("Error: Portal and MAC are required"))
            return None

        if not portal.endswith("/c/"):
            portal = portal.rstrip("/") + "/c/"

        timestamp = int(time.time())
        md5_hash = md5(mac.encode()).hexdigest()
        session = requests.Session()
        retry_strategy = Retry(total=3, backoff_factor=0.5,
                               status_forcelist=[429, 500, 502, 503, 504],
                               allowed_methods=["GET"])
        adapter = HTTPAdapter(max_retries=retry_strategy,
                              pool_connections=10, pool_maxsize=10)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.verify = False

        host = urlparse(portal).netloc
        timezone = fetch_system_timezone()
        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": host,
            "Referer": portal,
            "Cookie": f"mac={mac}; stb_lang=en; timezone={timezone};",
            "X-User-Agent": "Model: MAG254; Link: Ethernet",
        }

        idents = {"mac": mac, "sn": md5_hash, "type": "STB",
                  "model": "MAG250", "uid": "", "random": "null"}

        legacy_params = {
            'action': 'get_profile',
            'mac': mac,
            'type': 'stb',
            'hd': '1',
            'sn': md5_hash,
            'stb_type': "MAG250",
            'client_type': 'STB',
            'image_version': '218',
            'device_id': "",
            'hw_version': '1.7-BD-00',
            'hw_version_2': '1.7-BD-00',
            'auth_second_step': '1',
            'video_out': 'hdmi',
            'num_banks': '2',
            'ver': "ImageDescription: 0.2.18-r14-pub-250;ImageDate: Fri Jan 15 15:20:44 EET 2016;PORTAL version: 5.6.1;API Version: JS API version: 328;STB API version: 134;Player Engine version: 0x566",
            'not_valid_token': '0',
            'metrics': dumps(idents),
            'timestamp': str(timestamp),
            'api_signature': '262'}

        url_templates = {
            "handshake": [
                f"http://{host}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml",
                f"http://{host}/server/load.php?type=stb&action=handshake&JsHttpRequest=1-xml",
                f"http://{host}/stalker_portal/server/load.php?type=stb&action=handshake&JsHttpRequest=1-xml"
            ],
            "profile": [
                f"http://{host}/portal.php?type=stb&action=get_profile&JsHttpRequest=1-xml",
                f"http://{host}/server/load.php?type=stb&action=get_profile&JsHttpRequest=1-xml",
                f"http://{host}/stalker_portal/server/load.php?type=stb&action=get_profile&JsHttpRequest=1-xml"
            ],
            "account": [
                f"http://{host}/portal.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml",
                f"http://{host}/server/load.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml",
                f"http://{host}/stalker_portal/server/load.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml"
            ],
            "tariff": [
                f"http://{host}/portal.php?type=account_info&action=get_tariff_plan&JsHttpRequest=1-xml",
                f"http://{host}/server/load.php?type=account_info&action=get_tariff_plan&JsHttpRequest=1-xml",
                f"http://{host}/stalker_portal/server/load.php?type=account_info&action=get_tariff_plan&JsHttpRequest=1-xml"
            ]
        }

        info = {
            "user": "",
            "password": "",
            "expiry": "",
            "status": "",
            "active": "",
            "max": ""}

        try:
            self.update_status(_("Step 1/3: Handshake..."))
            token = None
            with open("/tmp/stalker_account_info.log", "w") as f_debug:
                f_debug.write("=== Handshake phase ===\n")
                for url in url_templates["handshake"]:
                    try:
                        response = session.get(
                            url, headers=headers, timeout=8, verify=False)
                        f_debug.write("URL: " + url + "\n")
                        f_debug.write("Response status: " +
                                      str(response.status_code) + "\n")
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                token = data.get("js", {}).get("token")
                                if token:
                                    f_debug.write(
                                        "Token found: " + token + "\n\n")
                                    break
                            except JSONDecodeError:
                                match = search(
                                    r'"token"\s*:\s*"([^"]+)"', response.text)
                                if match:
                                    token = match.group(1)
                                    f_debug.write(
                                        "Token extracted manually: " + token + "\n\n")
                                    break
                    except (requests.exceptions.RequestException, ConnectionError) as e:
                        f_debug.write("Request exception: " + str(e) + "\n")
                        continue

            if not token:
                self.update_status(_("Handshake failed: No token received"))
                self.update_account_info(
                    _("Possible causes:\n- Server not responding\n- Incorrect portal URL\n- Network issues"))
                return None

            headers_auth = headers.copy()
            headers_auth["Authorization"] = "Bearer " + token
            session.get(f"http://{host}/portal.php",
                        params={"type": "stb", "action": "do_auth", "mac": mac,
                                "token": token, "JsHttpRequest": "1-xml"},
                        headers=headers_auth, timeout=8, verify=False)

            profile_data = {}
            for url in url_templates["profile"]:
                try:
                    response = session.get(
                        url, headers=headers_auth, timeout=8, verify=False)
                    if response.status_code == 200:
                        try:
                            profile_data = response.json().get("js", {})
                            break
                        except JSONDecodeError:
                            continue
                except (requests.exceptions.RequestException, ConnectionError):
                    continue

            account_info = {}
            for url in url_templates["account"]:
                try:
                    response = session.get(
                        url,
                        headers=headers_auth,
                        params=legacy_params,
                        timeout=8,
                        verify=False)
                    if response.status_code == 200:
                        try:
                            account_info = response.json().get("js", {})
                            info["expiry"] = account_info.get("exp_date", "")
                            break
                        except JSONDecodeError:
                            continue
                except (requests.exceptions.RequestException, ConnectionError):
                    continue

            tariff_info = {}
            for url in url_templates["tariff"]:
                try:
                    response = session.get(
                        url, headers=headers_auth, timeout=8, verify=False)
                    if response.status_code == 200:
                        try:
                            tariff_info = response.json().get("js", {})
                            info["status"] = tariff_info.get("status", "")
                            info["active"] = tariff_info.get("active", "")
                            info["max"] = tariff_info.get(
                                "max_connections", "")
                            break
                        except JSONDecodeError:
                            continue
                except (requests.exceptions.RequestException, ConnectionError):
                    continue

            info = {
                "user": account_info.get("name", "N/A"),
                "password": profile_data.get("password", "N/A"),
                "expiry": account_info.get("expire_billing_date", "N/A"),
                "status": tariff_info.get("status", "N/A"),
                "active": tariff_info.get("active", "N/A"),
                "max": tariff_info.get("max_connections", "N/A")
            }
            print("[DEBUG] Account Info: {}".format(info))
            return info
        except Exception as e:
            self.update_status(_("Error extracting account information"))
            self.update_account_info(_("Error details: {}").format(str(e)))
            with open("/tmp/stalker_account_info.log", "a") as f_debug:
                f_debug.write("Error: " + str(e) + "\n")
            return None

    def update_account_fields(
            self,
            user,
            password,
            expiry,
            status,
            active,
            max_conn):
        status_map = {"0": "Active", "1": "Disabled", "": "Unknown"}
        status_str = status_map.get(status, status)
        expiry_str = "Never" if expiry == "0000-00-00 00:00:00" else expiry

        def update():
            self["user_value"].setText(user)
            self["pass_value"].setText(password)
            self["expiry_value"].setText(expiry_str)
            self["status_value"].setText(status_str)
            self["active_value"].setText(active)
            self["max_value"].setText(max_conn)
        reactor.callFromThread(update)

    def clear_account_info(self):
        self.update_account_fields("", "", "", "", "", "")

    def get_playlist_file_path(self):
        input_filelist = config.plugins.stalkerportal.input_filelist.value
        if not input_filelist:
            input_filelist = '/etc/enigma2'
        if not exists(input_filelist):
            makedirs(input_filelist)
        return join(input_filelist, "stalker_playlist.txt")

    def validate_and_add_entry(self, portal, mac):
        if portal and mac:
            portal_valid, portal = self.validate_portal_url(portal)
            mac_valid = self.validate_mac_address(mac)
            if portal_valid and mac_valid:
                display = f"{portal} - {mac}"
                return display, portal, mac
            elif not portal_valid:
                self["status"].setText(_("Invalid URL: ") + portal)
            elif not mac_valid:
                self["status"].setText(_("Invalid MAC: ") + mac)
        return None

    def validate_mac_address(self, mac):
        pattern = compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
        return bool(pattern.match(mac))

    def validate_portal_url(self, url):
        url = url.rstrip("/")
        if url.endswith("/c"):
            url += "/"
        elif not url.endswith("/c/"):
            url += "/c/"
        url = url.replace("/c/c/", "/c/")
        pattern = compile(r"^https?://[^\s/$.?#].[^\s]*$")
        return bool(pattern.match(url)), url

    def edit_settings(self):
        translations = {
            "Set Type Conversion": _("Set Type Conversion"),
            "Edit Portal URL": _("Edit Portal URL"),
            "Edit MAC Address": _("Edit MAC Address"),
            "Select Playlist File": _("Select Playlist File"),
            "Delete Playlist File": _("Delete Playlist File"),
            "Change Output Directory": _("Change Output Directory"),
            "Set Bouquet Position": _("Set Bouquet Position"),
            "Include VOD in Playlist": _("Include VOD in Playlist"),
            "Upgrade Stalker Converter": _("Upgrade Stalker Converter"),
            "Information": _("Information"),
        }

        menu_items = [
            ("Set Type Conversion", self.select_type_convert),
            ("Edit Portal URL", self.edit_portal),
            ("Edit MAC Address", self.edit_mac),
            ("Select Playlist File", self.select_playlist_file),
            ("Delete Playlist File", self.delete_playlist),
            ("Change Output Directory", self.select_output_dir),
            ("Include VOD in Playlist", self.toggle_include_vod),
            ("Upgrade Stalker Converter", self.check_vers),
            ("Information", self.show_info)
        ]

        if config.plugins.stalkerportal.type_convert.value == "1":
            menu_items.insert(
                5, ("Set Bouquet Position", self.select_bouquet_position))

        menu = [(translations.get(text, text), function)
                for text, function in menu_items]
        self.session.openWithCallback(self.menu_callback, MenuDialog, menu)

    def toggle_include_vod(self):
        current_value = config.plugins.stalkerportal.include_vod.value
        config.plugins.stalkerportal.include_vod.value = not current_value
        config.plugins.stalkerportal.include_vod.save()
        configfile.save()
        status = _("Enabled") if config.plugins.stalkerportal.include_vod.value else _(
            "Disabled")
        self["status"].setText(_("VOD inclusion: {}").format(status))
        self.update_all_widgets()

    def edit_portal(self):
        def portal_callback(portal):
            if portal:
                config.plugins.stalkerportal.portal_url.value = portal
                config.plugins.stalkerportal.portal_url.save()
                configfile.save()
                configfile.load()
                self.update_all_widgets()
        self.session.openWithCallback(
            portal_callback, VirtualKeyBoard,
            title=_("Enter Portal URL (e.g. http://example.com/c/ or http://example.com:8088/c/)"),
            text=config.plugins.stalkerportal.portal_url.value)

    def edit_mac(self):
        def mac_callback(mac):
            if mac:
                config.plugins.stalkerportal.mac_address.value = mac
                configfile.save()
                configfile.load()
                self.update_all_widgets()
        self.session.openWithCallback(
            mac_callback, VirtualKeyBoard,
            title=_("Enter MAC Address (e.g., 00:1A:79:XX:XX:XX)"),
            text=config.plugins.stalkerportal.mac_address.value)

    def menu_callback(self, result):
        if result:
            result[1]()

    def select_type_convert(self):
        options = [("MAC to M3U", "0"), ("MAC to .tv", "1")]

        def type_callback(choice):
            if choice:
                config.plugins.stalkerportal.type_convert.value = choice[1]
                configfile.save()
                configfile.load()
                self.update_all_widgets()
        self.session.openWithCallback(
            type_callback,
            ChoiceBox,
            title=_("Select Type of Conversion"),
            list=options)

    def select_bouquet_position(self):
        options = [("top", _("Top")), ("bottom", _("Bottom"))]

        def bouquet_pos_callback(choice):
            if choice is not None:
                config.plugins.stalkerportal.bouquet_position.value = choice
                configfile.save()
                configfile.load()
                self.update_status(
                    _("Bouquet position set to: {}").format(choice))
                self.update_all_widgets()
        self.session.openWithCallback(bouquet_pos_callback, ChoiceBox,
                                      title=_("Select Bouquet Position"),
                                      list=[(key, _(val)) for key, val in options])

    def load_playlist(self, file_path=None):
        if not file_path:
            file_path = self.get_playlist_file_path()
        self.playlist_file = file_path
        self.portal_list = []
        valid_count = 0
        try:
            if not exists(file_path):
                with open(file_path, 'w') as f:
                    f.write("")
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f.readlines()]

            current_portal = None
            for line in lines:
                if not line:
                    continue
                if any(
                    keyword in line.lower() for keyword in [
                        'panel',
                        'portal']) or line.startswith('http'):
                    url_match = search(r'(https?://[^\s]+)', line)
                    if url_match:
                        portal = url_match.group(0)
                        if not portal.startswith('http'):
                            portal = 'http://' + portal
                        if not portal.endswith('/c/'):
                            portal = portal.rstrip('/') + '/c/'
                        current_portal = portal
                elif any(keyword in line.lower() for keyword in ['mac', 'mac_address']) or ':' in line:
                    mac_match = search(
                        r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line, IGNORECASE)
                    if mac_match and current_portal:
                        mac = mac_match.group(0)
                        display = f"{current_portal} - {mac}"
                        self.portal_list.append((display, current_portal, mac))
                        valid_count += 1

            display_list = [entry[0] for entry in self.portal_list]
            self["file_list"].setList(display_list)
            if valid_count > 0:
                self["status"].setText(
                    _("Loaded {} valid entries from {}").format(
                        valid_count, basename(file_path)))
            else:
                self["status"].setText(_("No valid entries found in file"))
        except Exception as e:
            self["status"].setText(_("Error: ") + str(e))

    def reset_conversion_state(self):
        self.conversion_running = False
        self.conversion_stopped = False
        self.channels = []
        self["status"].setText(_("Conversion stopped by user"))
        self.stop_timer.stop()

    def finish_conversion(self, success, message):
        if self.closed:
            return
        try:
            self.conversion_running = False
            self.conversion_stopped = False
            self.conversion_result = (success, message)
            reactor.callFromThread(lambda: self.result_timer.start(10, True))
        except Exception:
            pass

    def handle_conversion_result(self):
        if self.closed or not hasattr(self, 'conversion_result'):
            return
        try:
            success, message = self.conversion_result
            self["key_green"].setText(self.get_convert_label())
            self["status"].setText(
                (_("Success! ") if success else _("Error! ")) + message)
        finally:
            if hasattr(self, 'conversion_result'):
                del self.conversion_result
            self.result_timer.stop()

    def convert(self):
        self.conversion_timeout = time.time() + 900
        with open("/tmp/stalker_convert_info.log", "a") as f_debug:
            f_debug.write("=== convert phase ===\n")
            if self.conversion_running:
                self.conversion_stopped = True
                self["status"].setText(_("Stopping conversion..."))
                self["key_green"].setText(self.get_convert_label())
                self.stop_timer.start(500, True)
                return

            output_path = config.plugins.stalkerportal.output_dir.value
            if not has_enough_free_space(
                    output_path, min_bytes_required=100 * 1024 * 1024):
                self["status"].setText(
                    _("Not enough space on {}!").format(output_path))
                return

            try:
                portal = config.plugins.stalkerportal.portal_url.value.strip()
                mac = config.plugins.stalkerportal.mac_address.value.strip()
                output_file = self._get_output_filename()
                f_debug.write("Output file: {}\n".format(output_file))
            except Exception as e:
                self["status"].setText(
                    _("Error accessing configuration values"))
                self.session.open(
                    MessageBox,
                    _("Failed to read portal or MAC configuration:\n") +
                    str(e),
                    MessageBox.TYPE_ERROR)
                return

            if not portal or not mac:
                self["status"].setText(_("Error: Portal and MAC are required"))
                return

            portal_valid, portal = self.validate_portal_url(portal)
            if not portal_valid:
                self["status"].setText(_("Error: Invalid portal URL"))
                return
            if not self.validate_mac_address(mac):
                self["status"].setText(_("Error: Invalid MAC address"))
                return

            output_dir = dirname(output_file)
            if not exists(output_dir):
                try:
                    makedirs(output_dir)
                except Exception as e:
                    self["status"].setText(
                        _("Cannot create directory: ") + str(e))
                    return

            self.conversion_stopped = False
            self.conversion_running = True
            self["key_green"].setText(_("Stop"))
            self["status"].setText(_("Starting conversion process..."))
            f_debug.write("Starting conversion process...\n")

            self.worker_thread = Thread(
                target=self.convert_thread, args=(
                    portal, mac, output_file))
            self.worker_thread.start()

    def convert_thread(self, portal, mac, output_file):
        output_dir = dirname(output_file)
        if not exists(output_dir):
            try:
                makedirs(output_dir, exist_ok=True)
            except Exception as e:
                self.finish_conversion(
                    False, _("Cannot create directory: ") + str(e))
                return
        try:
            if self.closed or self.conversion_stopped:
                return

            self.conversion_timeout = time.time() + 900
            if not output_file:
                output_file = f"/tmp/stalker_{mac}.m3u"

            with open("/tmp/stalker_convert_info.log", "a") as f_debug:
                f_debug.write("=== convert_thread phase ===\n")
                self.update_status(_("Step 1/3: Connecting to portal..."))
                success, token = self.get_channel_list(portal, mac)
                if time.time() > self.conversion_timeout:
                    self.finish_conversion(
                        False, _("Conversion timeout exceeded"))
                    return
                if self.conversion_stopped:
                    self.finish_conversion(
                        False, _("Conversion stopped during channel retrieval"))
                    return
                if not success or not self.channels:
                    self.finish_conversion(
                        False, _("Failed to retrieve channel list"))
                    return

                self.update_status(_("Step 2/3: Creating playlist file..."))
                convert_type = config.plugins.stalkerportal.type_convert.value

                try:
                    if convert_type == "0":
                        self.update_status(_("Step 3/3: Create M3U file..."))
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write("#EXTM3U\n")
                            f.write("# Portal: {}\n".format(portal))
                            f.write("# MAC: {}\n".format(mac))
                            f.write("# Channels: {}\n\n".format(
                                len(self.channels)))
                            for channel in self.channels:
                                if self.conversion_stopped:
                                    self.finish_conversion(
                                        False, _("Conversion stopped during M3U creation"))
                                    return
                                cleaned_name = cleanName(channel["name"])
                                cleaned_group = cleanName(channel["group"])
                                f.write(
                                    "#EXTINF:-1 tvg-id=\"{}\" tvg-name=\"{}\" ".format(channel["id"], cleaned_name))
                                f.write(
                                    "tvg-logo=\"{}\" group-title=\"{}\",{}\n".format(
                                        channel["logo"], cleaned_group, cleaned_name))
                                f.write("{}\n\n".format(channel["url"]))

                        if config.plugins.stalkerportal.include_vod.value:
                            self.update_status(
                                _("Step 4/4: Getting VOD content..."))
                            vod_categories = self.get_vod_list(
                                portal, mac, token)
                            if vod_categories:
                                with open(output_file, "a", encoding="utf-8") as f:
                                    f.write("\n\n#EXTM3U VOD SECTION\n\n")
                                    for category in vod_categories:
                                        f.write(
                                            f"#EXTINF:-1 group-title=\"VOD - {category['name']}\",{category['name']}\n")
                                        f.write(
                                            "#EXTVLCOPT:network-caching=1000\n\n")
                                        for movie in category['movies']:
                                            cleaned_name = cleanName(
                                                movie["name"])
                                            f.write(
                                                f"#EXTINF:-1 tvg-id=\"{movie['id']}\" ")
                                            f.write(
                                                f"tvg-name=\"{cleaned_name}\" ")
                                            if movie.get('year'):
                                                f.write(
                                                    f"tvg-year=\"{movie['year']}\" ")
                                            if movie.get('poster'):
                                                f.write(
                                                    f"tvg-logo=\"{movie['poster']}\" ")
                                            if movie.get('description'):
                                                desc = movie['description'].replace(
                                                    '"', "'")
                                                f.write(
                                                    f"tvg-description=\"{desc}\" ")
                                            f.write(
                                                f"group-title=\"VOD - {category['name']}\",")
                                            f.write(f"{cleaned_name} ({movie['year']})\n" if movie.get(
                                                'year') else f"{cleaned_name}\n")
                                            if movie.get('poster'):
                                                f.write(
                                                    f"#EXTIMG:{movie['poster']}\n")
                                            f.write(
                                                "#EXTVLCOPT:network-caching=1000\n")
                                            f.write(
                                                f"{movie['stream_url']}\n\n")
                                    total_vod = sum(
                                        len(cat['movies']) for cat in vod_categories)
                                    self.update_status(
                                        _("Added {} VOD items").format(total_vod))

                        self.update_status(_("M3U created with {} channels").replace(
                            "%s", str(len(self.channels))).replace("{}", str(len(self.channels))))
                        self.finish_conversion(
                            True, _("M3U created successfully"))

                    elif convert_type == "1":
                        self.update_status(
                            _("Step 3/3: Create Bouquet file..."))
                        groups = {}
                        for idx, channel in enumerate(self.channels):
                            if idx % 50 == 0 and self.conversion_stopped:
                                self.finish_conversion(
                                    False, _("Conversion stopped during grouping"))
                                return
                            group = channel.get("group", "Default")
                            groups.setdefault(group, []).append(channel)
                        if self.conversion_stopped:
                            self.finish_conversion(
                                False, _("Conversion stopped before bouquet creation"))
                            return
                        for group, ch_list in groups.items():
                            if self.conversion_stopped:
                                self.finish_conversion(
                                    False, _("Conversion stopped during bouquet creation"))
                                return
                            self.write_group_bouquet(group, ch_list)

                        if config.plugins.stalkerportal.include_vod.value:
                            self.update_status(
                                _("Step 4/4: Getting VOD content..."))
                            vod_categories = self.get_vod_list(
                                portal, mac, token)
                            if vod_categories:
                                vod_group_names = []
                                for category in vod_categories:
                                    group_name = "VOD: " + category['name']
                                    self.write_group_bouquet(
                                        group_name, category['movies'], is_vod=True)
                                    vod_group_names.append(group_name)
                                for group_name in vod_group_names:
                                    groups[group_name] = []
                                total_vod = sum(len(cat['movies'])
                                                for cat in vod_categories)
                                self.update_status(
                                    _("Added {} VOD items").format(total_vod))

                        self.update_main_bouquet(groups.keys())
                        self.finish_conversion(
                            True, _("Bouquets created: {} groups with {} channels").format(
                                len(groups), len(
                                    self.channels)))
                except Exception as e:
                    self.finish_conversion(
                        False, _("Error creating playlist: ") + str(e))
        except Exception as e:
            self.finish_conversion(False, _("Conversion error: ") + str(e))
        finally:
            self.conversion_running = False
            reactor.callFromThread(
                lambda: self["key_green"].setText(
                    self.get_convert_label()))

    def write_group_bouquet(self, group, items, is_vod=False):
        try:
            safe_name = self.get_safe_filename(group)
            filename = "/etc/enigma2/userbouquet." + safe_name + ".tv"
            temp_file = filename + ".tmp"
            with open(temp_file, "w", encoding="utf-8", errors="replace") as f:
                cleaned_group = cleanName(group) if group else safe_name
                f.write("#NAME {}\n".format(cleaned_group))
                if is_vod:
                    f.write("#SERVICE 1:64:0:0:0:0:0:0:0:0:--- | VOD | ---\n")
                    f.write("#DESCRIPTION --- | VOD | ---\n")
                else:
                    f.write(
                        "#SERVICE 1:64:0:0:0:0:0:0:0:0:--- | Stalker2Bouquet | ---\n")
                    f.write("#DESCRIPTION --- | Stalker2Bouquet | ---\n")
                for item in items:
                    url = item["stream_url"] if is_vod else item["url"]
                    name = item["name"]
                    if not url.startswith("http"):
                        url = "http://" + url
                    encoded_url = url.replace(":", "%3a")
                    f.write("#SERVICE 4097:0:1:0:0:0:0:0:0:0:")
                    f.write(encoded_url)
                    f.write("\n#DESCRIPTION " + name + "\n")
            replace(temp_file, filename)
            chmod(filename, 0o644)
        except Exception as e:
            print(f"[ERROR] write_group_bouquet exception: {e}")
            if exists(temp_file):
                try:
                    remove(temp_file)
                except BaseException:
                    pass
            raise

    def update_main_bouquet(self, groups):
        main_file = "/etc/enigma2/bouquets.tv"
        existing = []
        if exists(main_file):
            with open(main_file, "r", encoding="utf-8") as f:
                existing = f.readlines()
        new_lines = []
        for group in groups:
            safe_name = self.get_safe_filename(group)
            bouquet_path = "userbouquet." + safe_name + ".tv"
            line_to_add = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "' + \
                bouquet_path + '" ORDER BY bouquet\n'
            if line_to_add not in existing and line_to_add not in new_lines:
                new_lines.append(line_to_add)
        new_content = (
            new_lines +
            existing) if config.plugins.stalkerportal.bouquet_position.value == "top" else (
            existing +
            new_lines)
        with open(main_file, "w", encoding="utf-8") as f:
            f.writelines(new_content)
        reactor.callFromThread(reload_services)

    def get_safe_filename(self, group):
        if not group or not group.strip():
            mac = config.plugins.stalkerportal.mac_address.value.replace(
                ":", "_")
            return f"stalker_{mac}"
        safe_name = unicodedata.normalize("NFKD", group)
        safe_name = safe_name.encode("ascii", "ignore").decode("ascii")
        safe_name = sub(r"[^a-z0-9_\- ]", "_", safe_name.lower())
        safe_name = sub(r"\s+", "_", safe_name)
        safe_name = sub(r"_+", "_", safe_name).strip("_")
        if not safe_name:
            mac = config.plugins.stalkerportal.mac_address.value.replace(
                ":", "_")
            return f"stalker_{mac}"
        if len(safe_name) > 40:
            safe_name = safe_name[-40:]
        return safe_name + "_stalker"

    def update_account_info(self, text):
        reactor.callFromThread(self._update_account_info_safe, text)

    def _update_account_info_safe(self, text):
        self["account_info"].setText(text)
        self["account_info"].instance.invalidate()

    def update_status(self, text):
        reactor.callFromThread(self._update_status_safe, text)

    def _update_status_safe(self, text):
        if self.closed or "status" not in self:
            return
        try:
            self["status"].setText(text)
        except Exception:
            pass

    def get_channel_list(self, portal, mac):
        if self.closed or self.conversion_stopped:
            return False, None
        cache_key = f"{portal}_{mac}"
        if cache_key in self.channel_cache and time.time() < self.cache_expiration:
            self.channels = self.channel_cache[cache_key]["channels"]
            return True, self.channel_cache[cache_key]["token"]
        if time.time() > self.conversion_timeout:
            self.update_status(_("Conversion timeout exceeded"))
            return False, None

        self.channels = []
        token = None
        try:
            session = requests.Session()
            retry_strategy = Retry(total=2, backoff_factor=0.3,
                                   status_forcelist=[429, 500, 502, 503, 504],
                                   allowed_methods=["GET"])
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=50,
                pool_maxsize=100)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            session.verify = False

            portal = portal.rstrip("/")
            link_api = portal + "/portal.php"
            host = urlparse(portal).netloc
            timezone = fetch_system_timezone()
            headers = {
                "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/537.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/537.3",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Host": host,
                "Referer": portal,
                "Cookie": f"mac={mac}; stb_lang=en; timezone={timezone};",
                "X-User-Agent": "Model: MAG254; Link: Ethernet"}

            self.update_status(_("Step 1/3: Handshake..."))
            try:
                response = session.get(
                    link_api,
                    params={
                        "type": "stb",
                        "action": "handshake",
                        "token": "",
                        "JsHttpRequest": "1-xml"},
                    headers=headers,
                    timeout=(
                        3.0,
                        10.0))
                if response.status_code != 200:
                    self.update_status(
                        _("Handshake failed: HTTP {}").format(
                            response.status_code))
                    return False, None
            except RequestException as e:
                self.update_status(_("Connection error: ") + str(e))
                return False, None

            token_match = search(r'"token"\s*:\s*"([^"]+)"', response.text)
            if not token_match:
                self.update_status(_("Failed to obtain token!"))
                return False, None
            token = token_match.group(1)

            self.update_status(_("Step 2/3: Authentication..."))
            headers["Authorization"] = f"Bearer {token}"
            try:
                session.get(
                    link_api,
                    params={
                        "type": "stb",
                        "action": "do_auth",
                        "mac": mac,
                        "token": token,
                        "JsHttpRequest": "1-xml"},
                    headers=headers,
                    timeout=(
                        3.0,
                        10.0))
            except RequestException as e:
                self.update_status(_("Authentication failed: ") + str(e))
                return False, None

            self.update_status(_("Step 3/3: Getting channels..."))
            try:
                response = session.get(
                    link_api,
                    params={
                        "type": "itv",
                        "action": "get_all_channels",
                        "JsHttpRequest": "1-xml"},
                    headers=headers,
                    timeout=(
                        3.0,
                        15.0))
                if response.status_code != 200:
                    self.update_status(
                        _("Channel list failed: HTTP {}").format(
                            response.status_code))
                    return False, None
                json_data = response.json()
            except JSONDecodeError:
                self.update_status(_("Invalid JSON response for channel list"))
                return False, None
            except RequestException as e:
                self.update_status(_("Channel list error: ") + str(e))
                return False, None

            channels_data = json_data.get("js", {}).get("data", [])
            total_channels = len(channels_data)
            if not channels_data:
                self.update_status(_("No channels found in response"))
                return False, None

            self.update_status(
                _("Preparing {} channels...").format(total_channels))
            start_time = time.time()
            last_update = start_time
            # Conta TUTTI i processati (successi e fallimenti)
            completed_count = 0
            success_count = 0   # Conta solo i canali validi
            results = []
            max_workers = 50

            def update_detailed_status():
                elapsed = time.time() - start_time
                speed = completed_count / elapsed if elapsed > 0 else 0
                percent = (
                    completed_count /
                    total_channels *
                    100) if total_channels > 0 else 0
                eta = (total_channels - completed_count) / \
                    speed if speed > 0 else 0
                status_text = (
                    "Processed {}/{} ({:.1f}%)\n"
                    "Success: {} | Speed: {:.1f}/s | ETA: {:.1f}s"
                ).format(completed_count, total_channels, percent, success_count, speed, eta)
                self.update_status(status_text)

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self.process_channel,
                        session,
                        portal,
                        headers,
                        channel,
                        mac,
                        token): channel for channel in channels_data}

                for future in concurrent.futures.as_completed(futures):
                    if self.conversion_stopped:
                        self.update_status(
                            _("Conversion stopped during processing"))
                        return False, None
                    try:
                        channel_data = future.result(timeout=15.0)
                        completed_count += 1
                        if channel_data:
                            results.append(channel_data)
                            success_count += 1

                        current_time = time.time()
                        if completed_count % 10 == 0 or current_time - last_update > 2:
                            update_detailed_status()
                            last_update = current_time
                    except Exception as e:
                        completed_count += 1
                        print(f"Error processing channel: {str(e)}")

            update_detailed_status()
            self.channels = results
            self.cache_expiration = time.time() + 1800
            self.channel_cache[cache_key] = {
                "channels": self.channels.copy(), "token": token}
            return True, token
        except Exception as e:
            print(f"Critical error in get_channel_list: {str(e)}")
            import traceback
            traceback.print_exc()
            self.update_status(_("Critical channel processing error"))
            return False, None

    def get_vod_list(self, portal, mac, token):
        vod_categories = []
        try:
            categories_url = f"{portal}?type=vod&action=get_categories&JsHttpRequest=1-xml"
            with requests.Session() as session:
                session.verify = False
                categories_response = session.get(categories_url, timeout=8)
            categories_data = categories_response.json().get("js", {}).get("data", [])
            if not categories_data:
                return []
            with ThreadPoolExecutor(max_workers=min(10, len(categories_data))) as executor:
                futures = [
                    executor.submit(
                        self.process_vod_category,
                        category,
                        portal,
                        mac,
                        token) for category in categories_data]
                for future in as_completed(futures):
                    try:
                        category_data = future.result()
                        if category_data and category_data['movies']:
                            vod_categories.append(category_data)
                    except Exception as e:
                        print(f"Error processing VOD category: {str(e)}")
            return vod_categories
        except Exception as e:
            print(f'Error getting VOD list: {str(e)}')
            return []

    def process_vod_category(self, category, portal, mac, token):
        category_id = category.get("id")
        category_name = category.get("title", "Unknown")
        parsed_portal = urlparse(portal)
        host = parsed_portal.netloc
        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/537.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/537.3",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": host,
            "Referer": portal,
            "Cookie": f"mac={mac}; stb_lang=en; timezone={
                fetch_system_timezone()};",
            "X-User-Agent": "Model: MAG254; Link: Ethernet",
            "Authorization": f"Bearer {token}"}
        movies_url = f"{portal}?type=vod&action=get_ordered_list&genre={category_id}&JsHttpRequest=1-xml"
        try:
            response = requests.get(
                movies_url,
                headers=headers,
                timeout=15,
                verify=False)
            movies_data = response.json().get("js", {}).get("data", [])
            vod_entries = []
            for movie in movies_data:
                movie_data = self.process_vod_movie(
                    movie, portal, mac, token, category_name)
                if movie_data:
                    vod_entries.append(movie_data)
            return {
                "id": category_id,
                "name": category_name,
                "movies": vod_entries}
        except Exception as e:
            print(f"Error processing VOD category {category_name}: {e}")
            return None

    def get_vod_stream_url(self, portal, cmd, mac, token):
        try:
            parsed_portal = urlparse(portal)
            host = parsed_portal.netloc
            base_url = f"{parsed_portal.scheme}://{host}"
            headers = {
                "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/537.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/537.3",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Host": host,
                "Referer": portal,
                "Cookie": f"mac={mac}; stb_lang=en; timezone={
                    fetch_system_timezone()};",
                "X-User-Agent": "Model: MAG254; Link: Ethernet",
                "Authorization": f"Bearer {token}"}
            params = {
                "type": "vod",
                "action": "create_link",
                "cmd": cmd,
                "forced_storage": "none",
                "disable_ad": "0",
                "download": "0",
                "JsHttpRequest": "1-xml"}
            for endpoint in [
                    f"{base_url}/portal.php",
                    f"{base_url}/server/load.php",
                    f"{base_url}/stalker_portal/server/load.php"]:
                try:
                    response = requests.get(
                        endpoint,
                        params=params,
                        headers=headers,
                        timeout=10,
                        verify=False)
                    if response.status_code == 200:
                        try:
                            json_data = response.json()
                            if json_data.get("js", {}).get("cmd"):
                                return json_data["js"]["cmd"]
                        except JSONDecodeError:
                            if response.text.startswith("http"):
                                return response.text.strip()
                except Exception:
                    continue
            return ""
        except Exception as e:
            print(f'Error getting VOD stream URL: {str(e)}')
            return ""

    def process_vod_movie(self, movie, portal, mac, token, category_name):
        try:
            cmd = movie.get("cmd")
            if not cmd:
                return None
            stream_url = ""
            retries = 3
            while retries > 0 and not stream_url:
                stream_url = self.get_vod_stream_url(portal, cmd, mac, token)
                retries -= 1
                if not stream_url and retries > 0:
                    time.sleep(1)
            if not stream_url:
                return None
            if stream_url.startswith('ffmpeg '):
                stream_url = stream_url[7:]
            year = movie.get("year", "")
            if year and len(year) > 4:
                year = year[:4]
            return {
                "id": str(movie.get("id")),
                "name": cleanName(movie.get("name", "Unknown Movie")),
                "year": year, "poster": movie.get("poster", ""),
                "stream_url": stream_url, "category": category_name,
                "description": movie.get("description", ""),
                "duration": movie.get("duration", ""),
                "rating": movie.get("rating", ""),
                "director": movie.get("director", ""),
                "actors": movie.get("actors", ""),
                "genres": movie.get("genres", "")
            }
        except Exception as e:
            print(f"Error processing VOD movie: {str(e)}")
            return None

    def process_channel(self, session, portal, headers, channel, mac, token):
        """Process individual channel with enhanced reliability and Xtream compatibility"""
        try:
            cmd = channel.get("cmd", "").strip()
            channel_id = channel.get("id", "")
            channel_name = channel.get("name", "Unknown")

            # OTTIMIZZAZIONE 1: Se il comando è già un URL valido, risparmiamo
            # la richiesta HTTP!
            if cmd.startswith("http://") or cmd.startswith("https://"):
                return {
                    "id": str(channel_id),
                    "name": cleanName(channel_name),
                    "number": int(
                        channel.get(
                            "number",
                            0)),
                    "group": channel.get("category_name") or channel.get("group_name") or "",
                    "logo": str(
                        channel.get(
                            "logo",
                            "")),
                    "url": cmd,
                    "username": "",
                    "password": ""}

            max_retries = 2
            retry_delay = 0.5

            channel_params = {
                "type": "itv",
                "action": "create_link",
                "cmd": cmd,
                "mac": mac,
                "token": token,
                "JsHttpRequest": "1-xml"
            }
            api_url = portal.rstrip('/') + "/portal.php?" + \
                urlencode(channel_params)
            domain = urlparse(portal).netloc

            for attempt in range(max_retries + 1):
                if self.conversion_stopped or time.time() > self.conversion_timeout:
                    return None
                try:
                    # OTTIMIZZAZIONE 2: Usiamo la sessione passata (con pool di connessioni)
                    # invece di crearne una nuova per ogni canale
                    current_headers = headers.copy()
                    user_agents = [
                        "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/537.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/537.3",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"]
                    current_headers["User-Agent"] = random.choice(user_agents)

                    response = session.get(
                        api_url,
                        headers=current_headers,
                        timeout=(2.0, 3.0),
                        allow_redirects=True
                    )

                    if response.status_code >= 500:
                        if attempt < max_retries:
                            time.sleep(retry_delay)
                            continue
                        else:
                            response.raise_for_status()

                    if not response.content:
                        return None

                    try:
                        json_data = response.json()
                    except JSONDecodeError:
                        json_match = search(r'\{.*\}', response.text)
                        if json_match:
                            try:
                                json_data = loads(json_match.group())
                            except BaseException:
                                json_data = {"js": {"cmd": api_url}}
                        else:
                            if response.text.startswith("http"):
                                return {
                                    "id": str(channel_id),
                                    "name": cleanName(channel_name),
                                    "number": int(
                                        channel.get(
                                            "number",
                                            0)),
                                    "group": channel.get("category_name") or channel.get("group_name") or "",
                                    "logo": str(
                                        channel.get(
                                            "logo",
                                            "")),
                                    "url": response.text.strip()}
                            else:
                                return None

                    stream_url = None
                    if json_data.get("js", {}).get("cmd"):
                        stream_url = json_data["js"]["cmd"]
                    elif "url" in json_data:
                        stream_url = json_data["url"]
                    elif isinstance(json_data, str) and json_data.startswith("http"):
                        stream_url = json_data

                    if not stream_url:
                        stream_url = api_url

                    if stream_url.startswith('ffmpeg '):
                        stream_url = stream_url[7:]

                    if "localhost" in stream_url:
                        stream_url = stream_url.replace("localhost", domain)

                    group_title = channel.get(
                        "group_name", "") or channel.get(
                        "category_name", "")
                    display_name = channel_name.split(
                        ",", 1)[1].strip() if "," in channel_name else channel_name

                    return {
                        "id": str(channel_id),
                        "name": cleanName(display_name),
                        "number": int(channel.get("number", 0)),
                        "group": group_title,
                        "logo": str(channel.get("logo", "")),
                        "url": stream_url,
                        "username": "",
                        "password": ""
                    }

                except Exception:
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                        continue
                    return None
            return None
        except Exception as e:
            print(f"Error processing channel: {str(e)}")
            return None

    def process_fallback_response(
            self,
            response,
            channel_id,
            channel_name,
            channel,
            api_url,
            domain):
        try:
            try:
                json_data = response.json()
                stream_url = json_data.get("js", {}).get("cmd", api_url)
            except BaseException:
                if response.text.startswith("http"):
                    stream_url = response.text.strip()
                else:
                    stream_url = api_url
            if stream_url.startswith('ffmpeg '):
                stream_url = stream_url[7:]
            if "localhost" in stream_url:
                stream_url = stream_url.replace("localhost", domain)
            return {
                "id": str(channel_id),
                "name": cleanName(channel_name),
                "number": int(
                    channel.get(
                        "number",
                        0)),
                "group": channel.get("category_name") or channel.get("group_name") or "",
                "logo": str(
                    channel.get(
                        "logo",
                        "")),
                "url": stream_url}
        except BaseException:
            return None

    def select_output_dir(self):
        self.browse_directory(
            config.plugins.stalkerportal.output_dir.value,
            mode="directory")

    def browse_directory(self, path=None, mode="playlist"):
        if path is None:
            path = config.plugins.stalkerportal.output_dir.value
        is_mount_point = any(
            ['/barryhallen' in path, '/hdd' in path, '/usb' in path, '/net' in path])
        if not exists(path):
            try:
                makedirs(path, exist_ok=True)
            except BaseException:
                path = "/tmp"

        entries = []
        parent_dir = dirname(path)
        if parent_dir and parent_dir != path and exists(parent_dir):
            entries.append(("[DIR] ..", parent_dir, "dir"))
        if is_mount_point:
            entries.append(
                ("[MOUNT ROOT] " +
                 _("Select Mount Root"),
                    path,
                    "mount_root"))
        if mode == "directory":
            entries.append(
                ("[SELECT] " + _("Select this directory"), path, "select"))

        try:
            for item in sorted(listdir(path)):
                full_path = join(path, item)
                if isdir(full_path):
                    entries.append((f"[DIR] {item}", full_path, "dir"))
                elif mode == "playlist" and item.lower().endswith(('.txt', '.list', '.m3u')):
                    try:
                        human_size = self.format_size(getsize(full_path))
                        entries.append(
                            (f"{item} ({human_size})", full_path, "file"))
                    except BaseException:
                        entries.append((item, full_path, "file"))
        except Exception as e:
            self["status"].setText(_("Error accessing directory: ") + str(e))
            return

        if entries:
            entries.insert(0, (_("<< Cancel"), None, "cancel"))
            self.session.openWithCallback(
                lambda choice: self.handle_directory_selection(
                    choice, mode), ChoiceBox, title=_(
                    "Select directory" if mode == "directory" else _("Select playlist file")), list=[
                    (desc, (path, type)) for desc, path, type in entries])
        else:
            self["status"].setText(_("No files found in: ") + path)

    def _get_output_filename(self):
        convert_type = config.plugins.stalkerportal.type_convert.value
        mac = config.plugins.stalkerportal.mac_address.value.replace(":", "_")
        if convert_type == "1":
            return f"/etc/enigma2/userbouquet.{mac}.tv"
        output_dir = config.plugins.stalkerportal.output_dir.value
        if not output_dir or not isdir(output_dir):
            output_dir = defaultMoviePath()
            config.plugins.stalkerportal.output_dir.value = output_dir
            config.plugins.stalkerportal.output_dir.save()
            configfile.save()
        if not output_dir.endswith('/'):
            output_dir += '/'
        return f"{output_dir}stalker_{mac}.m3u"

    def handle_directory_selection(self, choice, mode):
        if not choice or not choice[1]:
            return
        selected_path, entry_type = choice[1]
        if entry_type == "cancel":
            return
        if entry_type == "dir":
            self.browse_directory(selected_path, mode)
            return
        if mode == "directory" and entry_type == "select":
            selected_path = selected_path.rstrip('/') + '/'
            if not isdir(selected_path):
                try:
                    makedirs(selected_path, exist_ok=True)
                except Exception as e:
                    self["status"].setText(
                        _("Cannot create directory: ") + str(e))
                    return
            if not access(selected_path, W_OK):
                self["status"].setText(
                    _("Directory not writable: ") + selected_path)
                return
            config.plugins.stalkerportal.output_dir.value = selected_path
            config.plugins.stalkerportal.output_dir.save()
            configfile.save()
            self.update_all_widgets()
            self["status"].setText(_("Selected directory: ") + selected_path)
        elif mode == "playlist" and entry_type == "file":
            self.playlist_file = selected_path
            self.load_playlist(selected_path)
            config.plugins.stalkerportal.input_filelist.value = dirname(
                selected_path)
            config.plugins.stalkerportal.input_filelist.save()
            configfile.save()
            self["status"].setText(
                _("Loaded playlist: %s") %
                basename(selected_path))
            self.update_all_widgets()

    def confirm_low_space(self, result, path):
        if result:
            config.plugins.stalkerportal.output_dir.value = path
            config.plugins.stalkerportal.output_dir.save()
            configfile.save()
            self.update_all_widgets()
            self["status"].setText(_("Selected directory: ") + path)

    def select_playlist_file(self):
        self.browse_directory(
            config.plugins.stalkerportal.input_filelist.value,
            mode="playlist")

    def delete_playlist(self, path=None):
        if path is None:
            path = config.plugins.stalkerportal.input_filelist.value
            if not exists(path):
                path = defaultMoviePath()
        files = []
        path = path.rstrip('/') or '/'
        parent_dir = dirname(path)
        if parent_dir and parent_dir != path:
            files.append(("[DIR] ..", parent_dir))
        try:
            dir_contents = sorted(listdir(path))
            dirs = [f for f in dir_contents if isdir(join(path, f))]
            file_list = [
                f for f in dir_contents if isfile(
                    join(
                        path, f)) and f.lower().endswith(
                    ('.m3u', '.txt', '.list'))]
            for d in sorted(dirs):
                files.append(("[DIR] " + d, join(path, d)))
            for f in sorted(file_list):
                full_path = join(path, f)
                try:
                    size = self.format_size(getsize(full_path))
                    files.append((f"{f} ({size})", full_path))
                except Exception:
                    files.append((f, full_path))
        except Exception as e:
            self["status"].setText(_("Error accessing directory: ") + str(e))
            return
        if not files:
            self["status"].setText(
                _("No files or directories found in: ") + path)
            return
        files.insert(0, (_("<< Back to main menu"), None))
        self.session.openWithCallback(
            self.playlist_selected_for_deletion,
            ChoiceBox,
            title=_("Select file to delete in: {}").format(path),
            list=files)

    def playlist_selected_for_deletion(self, choice):
        if not choice or choice[1] is None:
            return
        if choice[0].startswith("[DIR]"):
            self.delete_playlist(choice[1])
            return
        file_path = choice[1]
        filename = basename(file_path)
        self.session.openWithCallback(
            lambda result: self.confirm_delete(result, file_path),
            MessageBox,
            _("Are you sure you want to delete:\n{}?").format(filename),
            MessageBox.TYPE_YESNO)

    def confirm_delete(self, result, file_path):
        if result:
            try:
                current_dir = dirname(file_path)
                remove(file_path)
                self["status"].setText(_("Deleted: ") + basename(file_path))
                if hasattr(
                        self,
                        'playlist_file') and self.playlist_file == file_path:
                    self.playlist_file = None
                    self["file_input"].setText("")
                self.delete_playlist(current_dir)
            except Exception as e:
                self["status"].setText(_("Delete failed: ") + str(e))
                self.delete_playlist(dirname(file_path))

    def format_size(self, size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} GB"

    def update_path(self):
        try:
            base_path = config.plugins.stalkerportal.output_dir.value
            if not base_path or not isdir(base_path):
                fallbacks = ["/media/hdd", "/media/usb", "/tmp"]
                base_path = next((p for p in fallbacks if isdir(p)), "/tmp")
            if base_path == "/tmp":
                self.full_path = base_path
            else:
                self.full_path = join(base_path, "movie")
                if not isdir(self.full_path):
                    makedirs(self.full_path, exist_ok=True)
                    chmod(self.full_path, 0o755)
            if not isdir(self.full_path):
                self.full_path = "/tmp"
        except Exception as e:
            self.full_path = "/tmp"
            print(f"update_path error: {str(e)}")

    def get_convert_label(self):
        convert_type = config.plugins.stalkerportal.type_convert.value
        if convert_type == "0":
            return _("Convert to M3U")
        elif convert_type == "1":
            return _("Convert to TV")
        return _("")

    def keyUp(self):
        self["file_list"].up()

    def keyDown(self):
        self["file_list"].down()

    def keyLeft(self):
        self["file_list"].pageUp()

    def keyRight(self):
        self["file_list"].pageDown()

    def show_info(self):
        text = _(
            "Plugin: StalkerPortalConvert to M3U/TV\n"
            "Author: Lululla\n"
            "Version: %s\n"
            "Date: June 2025\n"
            "Description: Convert Stalker Portal playlists to M3U or Enigma2 bouquet format.\n"
            "Support: linuxsat-support.com - corvoboys.org\n\n"
        ) % __version__
        text += _("HELP:\n")
        text += _("- Open a file with server URLs or press the BLUE button to edit the host and MAC address\n")
        text += _("- Choose the desired output format: M3U or TV bouquet\n")
        text += _("- Press CONVERT to generate the playlist")
        self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=10)

    def clear_fields(self):
        config.plugins.stalkerportal.portal_url.value = "http://my.server.xyz:8080/c/"
        config.plugins.stalkerportal.mac_address.value = "00:1A:79:00:00:00"
        self["status"].setText(_("Fields cleared"))
        configfile.save()
        configfile.load()
        self.update_all_widgets()

    def check_vers(self):
        remote_version = "0.0"
        remote_changelog = ""
        try:
            req = Request(
                b64decoder(installer_url), headers={
                    "User-Agent": AgentRequest})
            page = urlopen(req).read().decode("utf-8")
        except Exception as e:
            print("[ERROR] Unable to fetch version info:", str(e))
            self.defer_message(
                _("Unable to fetch version info:\n{}").format(
                    str(e)), MessageBox.TYPE_ERROR)
            return
        for line in page.split("\n"):
            line = line.strip()
            if line.startswith("version"):
                remote_version = line.split(
                    "=")[-1].strip().strip("'").strip('"')
            elif line.startswith("changelog"):
                remote_changelog = line.split(
                    "=")[-1].strip().strip("'").strip('"')
                break
        self.new_version = str(remote_version)
        self.new_changelog = str(remote_changelog)
        if __version__ < self.new_version:
            self.Update = True
            self.select_update()
        else:
            self.defer_message(
                _("You are already running the latest version: {}").format(__version__),
                MessageBox.TYPE_INFO)

    def select_update(self):
        self.Update = False
        self.new_version, self.new_changelog, update_available = check_version(
            __version__, installer_url, AgentRequest)
        if update_available:
            self.Update = True

            def ask_update():
                self.session.openWithCallback(
                    self.install_update,
                    MessageBox,
                    _("New version %s available\n\nChangelog: %s\n\nDo you want to install it now?") %
                    (self.new_version,
                        self.new_changelog),
                    MessageBox.TYPE_YESNO)
            self._defer_timer = eTimer()
            self._defer_timer.callback.append(ask_update)
            self._defer_timer.start(100, True)
        else:
            self.defer_message(
                _("You are already running the latest version: %s") %
                __version__, MessageBox.TYPE_INFO)

    def install_update(self, answer=False):
        if answer:
            self.session.open(
                Console,
                "Upgrading...",
                cmdlist=[
                    "wget -q --no-check-certificate " +
                    b64decoder(installer_url) +
                    " -O - | /bin/sh"],
                finishedCallback=self.myCallback,
                closeOnSuccess=False)
        else:
            self.session.open(
                MessageBox,
                _("Update Aborted!"),
                MessageBox.TYPE_INFO,
                timeout=3)

    def myCallback(self, result=None):
        print("result:", result)

    def defer_message(self, text, mtype=MessageBox.TYPE_INFO):
        self._defer_timer = eTimer()
        self._defer_timer.callback.append(
            lambda: self.session.open(
                MessageBox, text, type=mtype))
        self._defer_timer.start(100, True)

    def start_web_server(self):
        if hasattr(self, 'web_server') and self.web_server:
            self.stop_web_server()
            self["key_web"].setText(_("Web Portal Server Off"))
            return
        try:
            port = 8080
            self.web_server = WebControlResource(self)
            self.site = server.Site(self.web_server)
            self.listening_port = reactor.listenTCP(
                port, self.site, interface="")
            ip_address = self.get_ip_address()
            self["key_web"].setText(_("Web Portal Server On"))
            self["status"].setText(
                _("Web server: http://%s:%d") %
                (ip_address, port))
        except Exception as e:
            self["status"].setText(_("Web server error: ") + str(e))

    def stop_web_server(self):
        if self.listening_port:
            self.listening_port.stopListening()
            self.listening_port = None
        self.web_server = None
        self["key_web"].setText(_("Web Portal Server Off"))
        self["status"].setText(_("Web server stopped"))

    def get_ip_address(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except BaseException:
            return "localhost"

    def update_config(self, portal, mac):
        config.plugins.stalkerportal.portal_url.value = portal
        config.plugins.stalkerportal.mac_address.value = mac
        configfile.save()
        configfile.load()
        self.update_all_widgets()
        self.extract_account_info_async()

    def close(self):
        self.closed = True
        self.conversion_stopped = True
        self.conversion_running = False
        self.stop_timer.stop()
        self.result_timer.stop()
        self.access_code_timer.stop()
        self.update_timer.stop()
        self.stop_web_server()
        if hasattr(self, 'worker_thread') and self.worker_thread.is_alive():
            self.worker_thread.join(2.0)
        super().close()

    def check_for_updates(self):
        """Check for updates from the web interface"""
        if exists(self.update_flag_file):
            try:
                # Read the type of update
                with open(self.update_flag_file, "r") as f:
                    update_type = f.read().strip()

                # Remove the flag file
                remove(self.update_flag_file)

                # Perform the appropriate update
                if update_type in ("full_reload", "config_update"):
                    # Ricarica la lista dal file di testo
                    self.load_playlist(self.get_playlist_file_path())
                    # Aggiorna i campi di testo
                    self.update_all_widgets()
                    self.extract_account_info_async()
                    print("[UPDATE] Sincronizzazione dal Web completata.")

            except Exception as e:
                print(f"Error processing update: {str(e)}")

    def generate_access_code(self):
        import random
        access_code = ''.join(str(random.randint(0, 9)) for _ in range(6))
        config.plugins.stalkerportal.web_access_code.value = access_code
        config.plugins.stalkerportal.web_access_code.save()
        configfile.save()
        return access_code

    def get_access_code(self):
        if config.plugins.stalkerportal.web_access_code.value:
            return config.plugins.stalkerportal.web_access_code.value
        return self.generate_access_code()

    def get_masked_access_code(self):
        code = self.get_access_code()
        if len(code) > 4:
            return code[:2] + "••" + code[-2:]
        return code

    def toggle_access_code_visibility(self):
        if self.web_server:
            if self.access_code_visible:
                self.hide_access_code()
            else:
                self.show_access_code()
        else:
            self.session.open(
                MessageBox,
                _("You need to start the Web Server first!"),
                MessageBox.TYPE_INFO)

    def show_access_code(self):
        self.access_code_visible = True
        self["access_code_label"].setText(
            _("Access Code: ") + self.get_access_code())
        self["show_code_btn"].setText(_("Hide Code"))
        self.access_code_timer.start(10000, True)

    def hide_access_code(self):
        self.access_code_visible = False
        self["access_code_label"].setText(
            _("Access Code: ") + self.get_masked_access_code())
        self["show_code_btn"].setText(_("Show Code"))
        self.access_code_timer.stop()

    def regenerate_access_code(self):
        if self.web_server:
            new_code = self.generate_access_code()
            self.hide_access_code()
            self.access_code_visible = True
            self["access_code_label"].setText(
                _("New Access Code: ") + new_code)
            self.access_code_timer.start(15000, True)
            self.session.open(
                MessageBox,
                _("New access code generated!"),
                MessageBox.TYPE_INFO)
        else:
            self.session.open(
                MessageBox,
                _("You need to start the Web Server first!"),
                MessageBox.TYPE_INFO)

    def reset_access_code(self):
        new_code = self.generate_access_code()
        self["access_code_label"].setText(
            _("Access Code: ") + self.get_masked_access_code())
        return new_code

    def get_current_portal(self):
        return config.plugins.stalkerportal.portal_url.value

    def get_current_mac(self):
        return config.plugins.stalkerportal.mac_address.value

    def get_all_macs(self):
        macs = set()
        try:
            with open(self.get_playlist_file_path(), "r", encoding="utf-8") as f:
                for line in f.readlines():
                    line = line.strip()
                    if self.validate_mac_address(line):
                        macs.add(line.upper())
        except FileNotFoundError:
            pass
        return macs

    def add_to_playlist(self, portal, macs):
        mac_list = [m.strip() for m in macs.split(",") if m.strip()]
        if not portal or not mac_list:
            return "error", None
        existing_macs = self.get_all_macs()
        for mac in mac_list:
            if mac.upper() in existing_macs:
                return "duplicate", mac
        try:
            with open(self.get_playlist_file_path(), "a", encoding="utf-8") as f:
                f.write("\n" + portal + "\n")
                for mac in mac_list:
                    if self.validate_mac_address(mac):
                        f.write(mac + "\n")
            config.plugins.stalkerportal.portal_url.value = portal
            config.plugins.stalkerportal.mac_address.value = mac_list[0]
            configfile.save()
            return "ok", None
        except Exception as e:
            print("Error adding to playlist:", str(e))
            return "error", None

    def get_full_playlist(self):
        playlist = []
        if not hasattr(self, 'playlist_file') or not self.playlist_file:
            return playlist
        try:
            with open(self.playlist_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            current_portal = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("http"):
                    if current_portal:
                        playlist.append(current_portal)
                    current_portal = {'portal': line, 'macs': []}
                elif self.validate_mac_address(line):
                    if current_portal:
                        current_portal['macs'].append(line)
            if current_portal:
                playlist.append(current_portal)
        except Exception as e:
            print(f"Error reading playlist: {str(e)}")
        return playlist

    def save_full_playlist(self, playlist):
        try:
            with open(self.get_playlist_file_path(), 'w') as f:
                for entry in playlist:
                    f.write(entry['portal'] + "\n")
                    for mac in entry['macs']:
                        f.write(mac + "\n")
                    f.write("\n")
            self.playlist_file = self.get_playlist_file_path()
            self.load_playlist(self.playlist_file)
            return True
        except Exception as e:
            print(f"Error saving playlist: {str(e)}")
            return False

    def remove_entry(self, portal_index, mac_index=None):
        playlist = self.get_full_playlist()
        if portal_index < 0 or portal_index >= len(playlist):
            return False
        if mac_index is not None:
            if 0 <= mac_index < len(playlist[portal_index]['macs']):
                del playlist[portal_index]['macs'][mac_index]
                if not playlist[portal_index]['macs']:
                    del playlist[portal_index]
        else:
            del playlist[portal_index]
        return self.save_playlist(playlist)

    def notify_plugin(self, update_type="full_reload"):
        try:
            with open(self.update_flag_file, "w") as f:
                f.write(update_type)
        except Exception as e:
            print(f"Error notifying plugin: {str(e)}")

    def update_entry(self, portal_index, new_portal, new_macs):
        playlist = self.get_full_playlist()
        if portal_index < 0 or portal_index >= len(playlist):
            return False
        playlist[portal_index]['portal'] = new_portal
        playlist[portal_index]['macs'] = [m.strip() for m in new_macs.split(
            ',') if m.strip() and self.validate_mac_address(m.strip())]
        return self.save_playlist(playlist)

    def save_playlist(self, playlist):
        try:
            with open(self.playlist_file, 'w', encoding='utf-8') as f:
                for entry in playlist:
                    f.write(f"{entry['portal']}\n")
                    for mac in entry['macs']:
                        f.write(f"{mac}\n")
                    f.write("\n")
            self.load_playlist(self.playlist_file)
            return True
        except Exception as e:
            print(f"Error saving playlist: {str(e)}")
            return False


class WebControlResource(resource.Resource):
    """
    ---
    **Web Interface Access and Management Help**

    This plugin includes a built-in web server that allows access to a full management interface.

    ### How It Works

    * When the plugin starts, a **masked access code** is displayed (e.g., **"Access Code: 12••34"**).
    * Open the displayed web address in your browser (e.g., `http://192.168.1.100:8080`).
    * Enter the **full access code** shown in the plugin (e.g., `123456`).
    * If the entered code is correct, you gain access to the management interface.

    ---

    ### Authentication System Features

    * **Automatic code generation**:
      A random 6-digit code is generated on plugin start (if not already present).
      The code is stored in the plugin configuration.

    ---

    ### On-Screen Controls

    In the main screen:

    * You see **"Access Code: 12••34"** (yellow text).
    * Green button: **"Show Code"**
    * Red button: **"New Code"**
    * Below the buttons, you see hints: **"0-SHOW"**, **"1-NEW"**

    #### To reveal the full code:

    * Press **"0"** on the remote control.
    * The full code is shown (e.g., **"Access Code: 123456"**).
    * After 10 seconds, it returns to the masked view (e.g., **"12••34"**).

    #### To generate a new code:

    * Press **"1"** on the remote control.
    * A new 6-digit code is generated (e.g., `987654`).
    * You see **"New Access Code: 987654"** for 15 seconds.
    * Then it returns to masked view (e.g., **"98••54"**).

    ---

    ### Advanced Security

    * Access is **temporarily blocked after 3 failed attempts**.
    * **No hints** about the correct code are shown in error messages.
    * Code check is **case-insensitive**.

    ---

    ### Playlist Management Interface

    * View all saved portals and associated MAC addresses.
    * Displayed in a structured, tabular format with logical grouping.

    #### Available Actions:

    * ✏️ **Edit** a portal (URL and MAC list)
    * 🗑️ **Delete** an entire portal
    * 🗑️ **Delete** a single MAC address

    #### Confirmation & Feedback:

    * Confirmation popup for all delete operations
    * Visual feedback after each action

    ---

    ### Workflow

    * Full management access from the main menu
    * Inline editing with dedicated forms
    * Automatic return to main view after operations

    ---

    ### Real-Time Updates

    * Changes are saved directly to the playlist file
    * Plugin reloads automatically
    * Interface always reflects the current state

    ---

    ### How to Use

    #### Access Advanced Management:

    * From the homepage, click **"Full Management"**
    * Or go directly to `/manage` in the browser

    #### Edit an Entry:

    * Click the ✏️ icon next to a portal
    * Edit the URL and/or MAC list (comma-separated)
    * Click **"Save Changes"**

    #### Delete Items:

    * 🗑️ Next to a portal: deletes the entire portal
    * 🗑️ Next to a MAC: deletes only that MAC address

    #### Add New Entries:

    * Return to the homepage using the dedicated button
    * Use the main form to add new entries

    ---

    ### Security Notes

    * All operations require authentication
    * Input validation before saving:

      * Correct URL format
      * MAC address validation
    * Confirmation required for destructive actions
    * Clear error messages for invalid operations

    ---
    """
    isLeaf = True
    attempts = {}

    def __init__(self, plugin):
        resource.Resource.__init__(self)
        self.plugin = plugin
        self.playlist_path = self.plugin.get_playlist_file_path()
        self.sessions = {}

        self.attempts = {}

    def check_authentication(self, request):
        token = request.getCookie(b'session_token')
        if token:
            token = token.decode('utf-8')
            if token in self.sessions and self.sessions[token]['expires'] > time.time(
            ):
                return True
        return False

    def create_session(self, request):
        token = urandom(16).hex()
        expires = time.time() + 3600
        self.sessions[token] = {
            'ip': request.getClientIP(),
            'expires': expires}
        request.setHeader(
            b'Set-Cookie',
            f"session_token={token}; Path=/; Max-Age=3600".encode('utf-8'))
        return token

    def is_ip_blocked(self, ip):
        if ip in self.attempts:
            entry = self.attempts[ip]
            if 'blocked_until' in entry:
                if time.time() < entry['blocked_until']:
                    return True
                else:
                    del self.attempts[ip]
                    return False
            return False
        return False

    def block_ip(self, ip):
        self.attempts[ip] = {
            'blocked_until': time.time() + 300,
            'type': 'block'}

    def render(self, request):
        try:
            self.cleanup_sessions()
            path = request.path.decode("utf-8")
            client_ip = request.getClientIP()
            if self.is_ip_blocked(client_ip):
                return self.get_blocked_page()
            if path == "/auth":
                return self.get_auth_page(request)
            if path == "/":
                return self.get_index(request)
            if not self.check_authentication(request):
                request.redirect(b"/auth")
                return b""
            if request.method == b"POST" and path == "/submit":
                return self.render_POST(request)
            try:
                if path == "/":
                    return self.get_index(request)
                elif path == "/manage":
                    return self.get_manage_page()
                elif path.startswith("/edit/"):
                    parts = path.split("/")
                    return self.get_edit_page(int(parts[2]))
                elif path.startswith("/delete/"):
                    parts = path.split("/")
                    mac_index = int(parts[3]) if len(parts) > 3 else None
                    return self.delete_entry(int(parts[2]), mac_index, request)
                elif path == "/upload":
                    return self.get_upload_page()
                elif path == "/upload_file":
                    return self.handle_file_upload(request)
                elif path.startswith("/save_edit/"):
                    parts = path.split("/")
                    return self.save_edit(int(parts[2]), request)
                elif path == "/force_sync":
                    self.plugin.notify_plugin("full_reload")
                    request.redirect(b"/?saved=1")
                    return b""

                return self.get_404_page()
            except Exception as e:
                return self.get_error_page(str(e))
        except Exception as e:
            return self.get_error_page(f"Internal server error: {str(e)}")

    def get_auth_page(self, request):
        message = ""
        client_ip = request.getClientIP()
        if self.is_ip_blocked(client_ip):
            return self.get_blocked_page()
        if request.method == b'POST':
            submitted_code = request.args.get(b'access_code', [b''])[
                0].decode('utf-8').strip()
            correct_code = self.plugin.get_access_code().strip()
            if submitted_code == correct_code:
                self.create_session(request)
                return b'<html><head><meta http-equiv="refresh" content="0; url=/" /></head><body><p>Redirecting...</p></body></html>'
            else:
                if client_ip not in self.attempts:
                    self.attempts[client_ip] = {'count': 1}
                else:
                    self.attempts[client_ip]['count'] += 1
                    if self.attempts[client_ip]['count'] >= 3:
                        self.block_ip(client_ip)
                        return self.get_blocked_page()
                message = "<div class='error-message'>Invalid access code! Attempts left: {}</div>".format(
                    3 - self.attempts[client_ip]['count'])
        html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Authentication Required</title>{
            self.get_css()}</head><body><div class="container"><header><h1>Authentication Required</h1></header><div class="card">{message}<form method="POST"><div class="form-group"><label>Access Code:</label><input type="password" name="access_code" required autofocus></div><button type="submit">Authenticate</button></form></div></div>{
            self.get_footer()}</body></html>"""
        return html.encode('utf-8')

    def get_blocked_page(self):
        html = """<!DOCTYPE html><html><head><title>Blocked</title>""" + self.get_css() + \
            """</head><body><div class="container"><header><h1>Access Temporarily Blocked</h1></header><div class="card"><div class="error-message">⚠️ Too many failed authentication attempts</div><p>Your IP has been temporarily blocked. Try again in 5 minutes.</p></div></div>""" + self.get_footer() + """</body></html>"""
        return html.encode('utf-8')

    def get_css(self):
        return """<style>:root{--primary:#00a8ff;--secondary:#2c3e50;--success:#27ae60;--danger:#e74c3c;--warning:#f39c12;--dark:#1a1d21;--darker:#15181c;--text:#e0e0e0;}*{box-sizing:border-box;margin:0;padding:0;}body{font-family:'Segoe UI',sans-serif;line-height:1.6;color:var(--text);background:linear-gradient(135deg,var(--darker)0%,var(--dark)100%);padding:20px;min-height:100vh;}.container{max-width:900px;margin:0 auto;background:rgba(30,33,38,0.85);padding:25px;border-radius:12px;box-shadow:0 5px 25px rgba(0,0,0,0.5);}header{text-align:center;margin-bottom:25px;padding-bottom:20px;border-bottom:1px solid rgba(80,85,90,0.3);}h1{color:var(--primary);margin-bottom:10px;}.card{background:rgba(40,44,50,0.8);border-radius:10px;padding:25px;margin-bottom:25px;border:1px solid rgba(70,75,80,0.3);}input[type="text"],input[type="password"],textarea{width:100%;padding:12px 15px;background:rgba(30,33,38,0.8);border:1px solid #444;border-radius:6px;font-size:16px;color:var(--text);}button,.btn{display:inline-block;padding:12px 25px;background:var(--primary);color:white;border:none;border-radius:6px;cursor:pointer;font-size:16px;font-weight:600;text-decoration:none;}button:hover,.btn:hover{background:#0090e0;}.error-message{background:rgba(231,76,60,0.2);border:1px solid var(--danger);color:#ffd4d4;padding:15px;border-radius:6px;margin:15px 0;}.success-message{background:rgba(39,174,96,0.2);border:1px solid var(--success);color:#d4ffd4;padding:15px;border-radius:6px;margin:15px 0;}table{width:100%;border-collapse:collapse;margin:25px 0;}th,td{padding:15px;text-align:left;border-bottom:1px solid rgba(70,75,80,0.3);}th{background-color:var(--secondary);color:white;}.actions{display:flex;gap:15px;margin-top:20px;}.actions a{flex:1;text-align:center;}.form-group{margin-bottom:20px;}label{display:block;margin-bottom:8px;color:#ccc;}</style>"""

    def get_index(self, request):
        current_portal = self.plugin.get_current_portal()
        current_mac = self.plugin.get_current_mac()
        saved = ""
        if b"saved" in request.args:
            saved = "<div class='success-message'>✓ Playlist entry saved successfully</div>"
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Stalker Portal Converter</title>{
            self.get_css()}</head><body><div class="container"><header><h1>Stalker Portal Converter</h1><p>by Lululla</p></header>{saved}<div class="card"><h2>Current Configuration</h2><p><strong>Portal URL:</strong> {current_portal}</p><p><strong>MAC Address:</strong> {current_mac}</p><form method="POST" action="/submit"><div class="form-group"><label>Portal URL:</label><input type="text" name="portal" value="{current_portal}" required></div><div class="form-group"><label>MAC Addresses (comma separated):</label><textarea name="mac" rows="3" required>{current_mac}</textarea></div><button type="submit">Save Configuration</button></form><div class="actions"><a href="/manage" class="btn">Full Management</a><a href="/upload" class="btn">Upload Playlist</a></div></div></div>{
            self.get_footer()}</body></html>"""
        return html.encode("utf-8")

    def get_manage_page(self):
        playlist = self.plugin.get_full_playlist()
        if not playlist:
            try:
                self.plugin.load_playlist(self.playlist_path)
                playlist = self.plugin.get_full_playlist()
            except Exception:
                pass
        rows = ""
        for idx, entry in enumerate(playlist):
            for mac_idx, mac in enumerate(entry.get('macs', [])):
                rows += f"""<tr><td><a href="/edit/{idx}/
    {mac_idx}" class="btn">Edit</a> <a href="/delete/{idx}/
    {mac_idx}" class="btn" onclick="return confirm('Delete?')">Delete</a></td><td>{
                    entry['portal']}</td><td>{mac}</td></tr>"""
                html = f"""
        <!DOCTYPE html><html><head><meta charset="UTF-8"><title>Playlist Management</title>{self.get_css()}</head>
        <body><div class="container"><header><h1>Playlist Management</h1></header>
        <div style="display:flex; gap:10px; margin-bottom:20px;">
            <a href="/" class="btn">← Torna alla Home</a>
            <a href="/force_sync" class="btn" style="background-color:#f39c12;">🔄 Forza Aggiornamento Decoder</a>
        </div>
        <div class="card"><table><thead><tr><th>Actions</th><th>Portal</th><th>MAC</th></tr></thead>
        <tbody>{rows if playlist else "<tr><td colspan='3'>Nessuna voce trovata</td></tr>"}</tbody></table></div></div>
        {self.get_footer()}</body></html>
        """
        return html.encode('utf-8')

    def get_edit_page(self, portal_index):
        playlist = self.plugin.get_full_playlist()
        if portal_index < 0 or portal_index >= len(playlist):
            return self.get_404_page("Invalid portal index")
        entry = playlist[portal_index]
        macs = ", ".join(entry['macs'])
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Edit Portal</title>{
            self.get_css()}</head><body><div class="container"><header><h1>Edit Portal</h1></header><a href="/manage" class="btn">← Back</a><div class="card"><form method="POST" action="/save_edit/{portal_index}"><div class="form-group"><label>Portal URL:</label><input type="text" name="portal" value="{
            entry['portal']}" required></div><div class="form-group"><label>MAC Addresses (comma separated):</label><textarea name="mac" rows="5" required>{macs}</textarea></div><button type="submit">Save Changes</button></form></div></div>{
            self.get_footer()}</body></html>"""
        return html.encode('utf-8')

    def delete_entry(self, portal_index, mac_index, request):
        if self.plugin.remove_entry(portal_index, mac_index):
            self.plugin.notify_plugin("full_reload")
            request.redirect(b"/manage")
            return b""
        return self.get_error_page("Failed to delete entry")

    def save_edit(self, portal_index, request):
        portal = request.args.get(b'portal', [b''])[0].decode('utf-8')
        macs = request.args.get(b'mac', [b''])[0].decode('utf-8')
        if self.plugin.update_entry(portal_index, portal, macs):
            self.plugin.notify_plugin("full_reload")
            request.redirect(b"/manage")
            return b""
        return self.get_error_page("Failed to save changes")

    def get_upload_page(self):
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Upload Playlist</title>{
            self.get_css()}</head><body><div class="container"><header><h1>Upload Playlist</h1></header><a href="/" class="btn">← Back</a><div class="card"><form method="POST" action="/upload_file" enctype="multipart/form-data"><div class="form-group"><label>Select playlist file (TXT):</label><input type="file" name="playlist_file" accept=".txt" required></div><button type="submit">Upload</button></form></div></div>{
            self.get_footer()}</body></html>"""
        return html.encode('utf-8')

    def handle_file_upload(self, request):
        """Handle multipart file upload using manual parsing (compatible with Python 3.13+)"""
        try:
            content_type = request.getHeader(b'content-type') or b''
            if b'multipart/form-data' not in content_type:
                return self.get_error_page("Invalid content type for upload")
            boundary = None
            for part in content_type.split(b';'):
                part = part.strip()
                if part.startswith(b'boundary='):
                    boundary = part[len(b'boundary='):].strip(b'"')
                    break
            if not boundary:
                return self.get_error_page("Missing boundary in upload")
            body = request.content.read()
            boundary_marker = b'--' + boundary
            parts = body.split(boundary_marker)
            file_content = None
            for part in parts:
                if b'name="playlist_file"' in part and b'filename=' in part:
                    # Header separator is \r\n\r\n
                    header_end = part.find(b'\r\n\r\n')
                    if header_end != -1:
                        file_content = part[header_end + 4:]
                        # Remove trailing \r\n before boundary
                        if file_content.endswith(b'\r\n'):
                            file_content = file_content[:-2]
                        break
            if file_content is None:
                return self.get_error_page("No file received")
            try:
                text = file_content.decode('utf-8', errors='ignore')
            except Exception:
                text = file_content.decode('latin-1', errors='ignore')

            with open(self.playlist_path, 'w', encoding='utf-8') as f:
                f.write(text)

            self.plugin.load_playlist(self.playlist_path)
            self.plugin.notify_plugin("full_reload")

            html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Upload Successful</title>{
                self.get_css()}</head><body><div class="container"><header><h1>Playlist Uploaded</h1></header><a href="/" class="btn">← Back</a><div class="card"><div class="success-message">✓ Playlist file uploaded successfully</div><div class="actions"><a href="/" class="btn">Go to Main</a><a href="/manage" class="btn">View Playlist</a></div></div></div>{
                self.get_footer()}</body></html>"""
            return html.encode('utf-8')
        except Exception as e:
            return self.get_error_page(f"Error uploading file: {str(e)}")

    def get_404_page(self, message="Page not found"):
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Not Found</title>{
            self.get_css()}</head><body><div class="container"><header><h1>Page Not Found</h1></header><div class="card"><div class="error-message">{message}</div><div class="actions"><a href="/" class="btn">Return to Main</a></div></div></div>{
            self.get_footer()}</body></html>"""
        return html.encode('utf-8')

    def get_error_page(self, error):
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Error</title>{
            self.get_css()}</head><body><div class="container"><header><h1>An Error Occurred</h1></header><div class="card"><div class="error-message">{error}</div><div class="actions"><a href="/" class="btn">Return to Main</a><a href="/manage" class="btn">Back to Management</a></div></div></div>{
            self.get_footer()}</body></html>"""
        return html.encode('utf-8')

    def cleanup_sessions(self):
        now = time.time()
        expired = [
            token for token,
            data in self.sessions.items() if data['expires'] < now]
        for token in expired:
            del self.sessions[token]

    def render_GET(self, request):
        path = request.path.decode("utf-8")
        parts = path.strip("/").split("/")
        try:
            if path == "/":
                return self.get_index(request)
            elif path == "/manage":
                return self.get_manage_page()
            elif path == "/force_sync":
                self.plugin.notify_plugin("full_reload")
                request.redirect(b"/?saved=1")
                return b""
            elif parts[0] == "edit" and len(parts) == 2:
                return self.get_edit_page(int(parts[1]))
            elif parts[0] == "delete" and len(parts) >= 3:
                return self.delete_entry(int(parts[1]), int(parts[2]), request)
            elif path == "/upload":
                return self.get_upload_page()
            elif path == "/upload_file":
                return self.handle_file_upload(request)
            elif parts[0] == "save_edit" and len(parts) == 2:
                return self.save_edit(int(parts[1]), request)
            else:
                return self.get_404_page()
        except Exception as e:
            return self.get_error_page(str(e))

    def render_POST(self, request):
        path = request.path.decode("utf-8")
        if path == "/submit":
            portal = request.args.get(b"portal", [b""])[
                0].decode("utf-8").strip()
            macs = request.args.get(b"mac", [b""])[0].decode("utf-8").strip()

            if not portal or not macs:
                return self.get_error_page(
                    "Portal URL and MAC addresses are required.")

            status, extra = self.plugin.add_to_playlist(portal, macs)

            if status == "duplicate":
                return self.get_error_page(f"MAC già presente: {extra}")
            if status != "ok":
                return self.get_error_page(
                    "Errore nel salvataggio della playlist.")

            self.plugin.notify_plugin("full_reload")
            request.redirect(b"/?saved=1")
            return b""
        elif path == "/save_playlist_entry":
            content = request.content.read().decode("utf-8")
            try:
                data = loads(content)
                portal = data.get("portal", "").strip()
                macs = data.get("macs", "").strip()
                confirm = data.get("confirm", False)
            except Exception:
                request.setResponseCode(400)
                return b"Invalid JSON data"
            if not confirm:
                request.setHeader("Content-Type", "application/json")
                return dumps({"message": "Confirm saving?",
                             "portal": portal, "macs": macs}).encode("utf-8")
            status, _ = self.plugin.add_to_playlist(portal, macs)
            if status == "ok":
                self.plugin.load_playlist(self.playlist_path)
                self.plugin.notify_plugin("config_update")
                request.setHeader("Content-Type", "text/plain")
                return b"Playlist saved successfully"
            request.setResponseCode(500)
            return b"Failed to save playlist entry"
        else:
            request.setResponseCode(404)
            return b"Not found"

    def get_footer(self):
        return """<footer style="text-align:center;margin:20px 0;color:#888;font-size:0.9em;">powered by Lululla</footer>"""


class MenuDialog(Screen):
    skin = """
    <screen name="MenuDialog" position="center,center" size="600,400" title="Edit Settings">
        <widget name="menu" position="10,10" size="580,380" itemHeight="40" font="Regular;28" scrollbarMode="showOnDemand" />
    </screen>
    """

    def __init__(self, session, menu):
        Screen.__init__(self, session)
        self["menu"] = MenuList(menu)
        self["actions"] = ActionMap(
            ["OkCancelActions"], {
                "ok": self.ok, "cancel": self.cancel}, -1)

    def ok(self):
        selection = self["menu"].getCurrent()
        if selection:
            self.close(selection)

    def cancel(self):
        self.close(None)


def main(session):
    session.open(StalkerPortalConverter)


def Plugins(**kwargs):
    return PluginDescriptor(
        name="Stalker Portal Converter",
        description=_("Convert Stalker Portal to M3U playlist with actual channels"),
        where=PluginDescriptor.WHERE_PLUGINMENU,
        icon="plugin.png",
        fnc=main)
