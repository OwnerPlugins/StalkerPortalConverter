#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function
from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from os.path import isdir, exists, dirname, join
from os import access, popen, environ, system, listdir, W_OK, statvfs
import importlib.util
import gettext
import sys
# ═════════════════════════════════════════════════════════════════════
#
#  UTILITY INIT
#  Version: 1.4
#  Created by Lululla (https://github.com/Belfagor2005)
#  License: CC BY-NC-SA 4.0
#  https://creativecommons.org/licenses/by-nc-sa/4.0
#
#  Last Modified: "15:14 - 20250423"
#
#  Credits:
#
# 👨‍💻 Original Developers: Lululla
# ✍️ (2024-07-20)
#
# ⚖️ License: GNU General Public License (v2 or later)
#    You must NOT remove credits and must share modified code.
# ═════════════════════════════════════════════════════════════════════
__author__ = "Lululla"
__email__ = "ekekaz@gmail.com"
__copyright__ = 'Copyright (c) 2024 Lululla'
__license__ = "GPL-v2"
__version__ = "1.6"

isDreambox = exists("/usr/bin/apt-get")


def check_and_install_requests():
    if importlib.util.find_spec("requests") is not None:
        return True   # già installato

    python_version = sys.version_info.major
    pkg_manager_cmd = "apt-get -y install " if isDreambox else "opkg install "
    package_name = "python-requests" if python_version == 2 else "python3-requests"
    system(pkg_manager_cmd + package_name)
    # eventualmente verifica se ora è installato
    return importlib.util.find_spec("requests") is not None


check_and_install_requests()


PY3 = sys.version_info[0] >= 3
if PY3:
    from urllib.request import urlopen
    from urllib.error import URLError
    from urllib.request import Request
else:
    from urllib2 import urlopen
    from urllib2 import URLError
    from urllib2 import Request


PluginLanguageDomain = "StalkerPortalConverter"
PluginLanguagePath = "Extensions/StalkerPortalConverter/locale"

plugin_path = dirname(sys.modules[__name__].__file__)
AgentRequest = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.3'
installer_url = 'aHR0cHM6Ly9yYXcuZ2l0aHVidXNlcmNvbnRlbnQuY29tL0JlbGZhZ29yMjAwNS9TdGFsa2VyUG9ydGFsQ29udmVydGVyL21haW4vaW5zdGFsbGVyLnNo'
developer_url = 'aHR0cHM6Ly9hcGkuZ2l0aHViLmNvbS9yZXBvcy9CZWxmYWdvcjIwMDUvU3RhbGtlclBvcnRhbENvbnZlcnRlcg=='


def localeInit():
    if isDreambox:
        lang = language.getLanguage()[:2]
        environ["LANGUAGE"] = lang
    if PluginLanguageDomain and PluginLanguagePath:
        gettext.bindtextdomain(
            PluginLanguageDomain,
            resolveFilename(
                SCOPE_PLUGINS,
                PluginLanguagePath))


def _(txt):
    if isDreambox:
        return gettext.dgettext(PluginLanguageDomain, txt) if txt else ""
    else:
        translated = gettext.dgettext(PluginLanguageDomain, txt)
        if translated:
            return translated
        else:
            print(
                "[%s] fallback to default translation for %s" %
                (PluginLanguageDomain, txt))
            return gettext.gettext(txt)


localeInit()
language.addCallback(localeInit)


def b64decoder(s):
    s = str(s).strip()
    import base64
    import sys
    try:
        output = base64.b64decode(s)
        if sys.version_info[0] == 3:
            output = output.decode('utf-8')
        return output
    except Exception:
        padding = len(s) % 4
        if padding == 1:
            print('Invalid base64 string: {}'.format(s))
            return ""
        elif padding == 2:
            s += b'=='
        elif padding == 3:
            s += b'='
        else:
            return ""
        output = base64.b64decode(s)
        if sys.version_info[0] == 3:
            output = output.decode('utf-8')
        return output


def check_version(currversion, installer_url, AgentRequest):
    """Version control with advanced number format management"""
    print("[Version Check] Starting...")
    remote_version = "0.0"
    remote_changelog = "No changelog available"
    import base64
    try:
        decoded_url = base64.b64decode(installer_url).decode("utf-8")
        if not decoded_url.startswith(("http://", "https://")):
            raise ValueError("Invalid URL protocol")

        req = Request(
            decoded_url,
            headers={
                "User-Agent": AgentRequest,
                "Cache-Control": "no-cache"
            }
        )

        with urlopen(req, timeout=15) as response:
            if response.getcode() != 200:
                raise URLError("HTTP Status: %d" % response.getcode())

            data = response.read().decode("utf-8")

            if data:
                lines = data.split("\n")
                remote_version = "0.0"
                remote_changelog = "No changelog available"

                for line in lines:
                    if line.startswith("version"):
                        parts = line.split("=")
                        if len(parts) > 1:
                            remote_version = parts[1].strip().strip("'")
                    if line.startswith("changelog"):
                        parts = line.split("=")
                        if len(parts) > 1:
                            remote_changelog = parts[1].strip().strip("'")
                            break

                new_version = remote_version or "Unknown"
                new_changelog = remote_changelog or "No changelog available"

                return new_version, new_changelog, currversion < remote_version

    except Exception as e:
        print("Error while checking version:", e)
        return None, None, False


def get_mounted_devices():
    """Recovers mounted devices with write permissions"""
    from Components.Harddisk import harddiskmanager
    from Tools.Directories import SCOPE_MEDIA

    devices = [
        (resolveFilename(SCOPE_MEDIA, "hdd"), _("Hard Disk")),
        (resolveFilename(SCOPE_MEDIA, "usb"), _("USB Drive"))
    ]

    devices.append(("/tmp/", _("Temporary Storage")))

    try:
        devices += [
            (p.mountpoint, p.description or _("Disk"))
            for p in harddiskmanager.getMountedPartitions()
            if p.mountpoint and access(p.mountpoint, W_OK)
        ]

        net_dir = resolveFilename(SCOPE_MEDIA, "net")
        if isdir(net_dir):
            devices += [(join(net_dir, d), _("Network"))
                        for d in listdir(net_dir)]

    except Exception as e:
        print("ERROR", "Mount error: %s" % str(e))

    unique_devices = {}
    for p, d in devices:
        path = p.rstrip("/") + "/"
        if isdir(path):
            unique_devices[path] = d

    return list(unique_devices.items())


def fetch_system_timezone():
    """
    Retrieve the system timezone by reading from /usr/config/timezone_config.
    If the file is missing or invalid, returns 'Europe/London' as a fallback.
    """
    timezone_file = '/usr/config/timezone_config'
    fallback_timezone = 'Europe/London'

    try:
        if exists(timezone_file):
            with open(timezone_file, 'r') as file:
                tz = file.read().strip()
                if '/' in tz and not tz.startswith('#'):
                    return tz
    except (IOError, PermissionError):
        pass

    return fallback_timezone


def has_enough_free_space(path, min_bytes_required=50 * 1024 * 1024):
    """Check if the given path has at least min_bytes_required free space."""
    statv = statvfs(path)
    free_bytes = statv.f_bavail * statv.f_frsize
    return free_bytes >= min_bytes_required


def get_cpu_count():
    """Get number of CPU cores from /proc/cpuinfo"""
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()
        return cpuinfo.count("processor\t:")
    except BaseException:
        return 1  # Fallback to single core


def write_debug_line(label, value=None, filename="/tmp/stalker_convert.log"):
    try:
        with open(filename, "a") as f:
            if value is not None:
                f.write(label + ": " + str(value) + "\n")
            else:
                f.write(label + "\n")
    except Exception:
        pass


def cleanName(name):
    import unicodedata
    if not name:
        return ""

    name = unicodedata.normalize(
        "NFKD", name).encode(
        "ASCII", "ignore").decode("ASCII")
    name = name.replace('\xc2\x86', '').replace('\xc2\x87', '')
    name = name.replace('"', '').replace("'", '')
    name = name.replace('(', '').replace(')', '')
    name = name.replace('&', 'e').replace('*', 'x')
    name = name.replace('[', '').replace(']', '')
    name = name.replace('{', '(').replace('}', ')')
    name = ' '.join(name.split())

    return name.strip()


def wgetsts():
    wgetsts = False
    cmd22 = 'find /usr/bin -name "wget"'
    res = popen(cmd22).read()
    if 'wget' not in res.lower():
        if exists("/var/lib/dpkg/status"):
            cmd23 = 'apt-get update && apt-get install wget'
            popen(cmd23)
            wgetsts = True
        else:
            cmd23 = 'opkg update && opkg install wget'
            popen(cmd23)
            wgetsts = True
        return wgetsts
