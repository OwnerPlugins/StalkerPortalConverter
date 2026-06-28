<h1 align="center">📺 Stalker Portal Playlist Converter</h1>

[![Version](https://img.shields.io/badge/Version-1.6-blue.svg)](https://github.com/Belfagor2005/StalkerPortalConverter)
[![Enigma2](https://img.shields.io/badge/Enigma2-Plugin-ff6600.svg)](https://www.enigma2.net)
[![Python](https://img.shields.io/badge/Python-2.7%2B-blue.svg)](https://www.python.org)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python package](https://github.com/Belfagor2005/StalkerPortalConverter/actions/workflows/pylint.yml/badge.svg)](https://github.com/Belfagor2005/StalkerPortalConverter/actions/workflows/pylint.yml)
[![Ruff Status](https://github.com/Belfagor2005/StalkerPortalConverter/actions/workflows/ruff.yml/badge.svg)](https://github.com/Belfagor2005/StalkerPortalConverter/actions/workflows/ruff.yml)

[![Visitors](https://komarev.com/ghpvc/?username=Belfagor2005&label=Repository%20Views&color=blueviolet)](https://github.com/Belfagor2005)
[![Donate](https://img.shields.io/badge/_-Donate-red.svg?logo=githubsponsors&labelColor=555555&style=for-the-badge)](https://ko-fi.com/lululla)
[![Donate](https://img.shields.io/badge/_-Donate-green.svg?logo=githubsponsors&labelColor=555555&style=for-the-badge)](https://paypal.me/belfagor2005)


<p align="center">
  <img src="https://github.com/Belfagor2005/StalkerPortalConverter/blob/main/usr/lib/enigma2/python/Plugins/Extensions/StalkerPortalConverter/plugin.png?raw=true" height="140">
</p>

---

## 📺 Screenshots

<p align="center">
  <img src="https://github.com/Belfagor2005/StalkerPortalConverter/blob/main/screen/screen.jpeg?raw=true" height="220">
  <img src="https://github.com/Belfagor2005/StalkerPortalConverter/blob/main/screen/main.jpeg?raw=true" height="220">
</p>

<p align="center">
  <img src="https://github.com/Belfagor2005/StalkerPortalConverter/blob/main/screen/playlist_management.jpeg?raw=true" height="220">
  <img src="https://github.com/Belfagor2005/StalkerPortalConverter/blob/main/screen/playlist_management2.jpeg?raw=true" height="220">
</p>

---

## 🔧 Overview

This plugin allows you to convert a list of **Stalker Portal** URLs and MAC addresses from a `playlist.txt` file into **usable M3U playlists**.

### 🚀 Features

* 🧠 **Smart parsing**: Recognizes multiple formats of portal and MAC combinations
* 📁 **Custom folder selection** for output
* ⚡ **Very fast**: \~13,000 channels converted in about 1 minute
* 💻 Output is easily viewable and usable on PC or media players
* 🧾 Supports **multiple MACs per portal** and **shared MAC usage**
* 🔐 **Account info extraction**: Retrieves credentials, subscription expiry, status, and connection limits from the server
* 🎞️ **TV bouquet conversion**: Convert playlists to Enigma2-compatible TV bouquet format
* ⬆️ **In-plugin updater**: Update the plugin directly from the user interface
* 🌐 **Integrated Web Server**: Manage playlists and settings through a built-in browser interface

---
## 🎮 How to Use

| *Button      | Action               | Description                                   |
| ------------ | -------------------- | --------------------------------------------- |
| 🔴 **RED**   | Clear Field          | Clears current portal and MAC input fields    |
| 🟢 **GREEN** | Convert to M3U/TV E2 | Generates the M3U playlist and saves to file  |
| 🟡 **YELLOW**| Select Output Folder | Opens folder selector and sets playlist path  |
| 🔵 **BLUE**  | Edit Config          | Opens configuration page for advanced options |
| ℹ️ **INFO**  | Show Help            | Displays help and usage instructions          |
| 🔢 **Key 1** | Show Code            | Displays the current access code/token        |
| 🔢 **Key 0** | New Code             | Generates a new access code for web interface |
| ⌨️ **TXT**   | Start Web Server     | Launches the integrated web control interface |

---


### ⚙️ **Settings Menu Options**

Use the **Settings** menu to configure the following options:

| *Key 🔢 / Button ⌨️            | Option                           | Description                             |
| ------------------------------ | -------------------------------- | --------------------------------------- |
| 🖥️ **Edit Portal URL**         | Change the portal URL            | Modify the portal used for IPTV         |
| 🖥️ **Edit MAC Address**        | Modify the MAC address           | Update your MAC address                 |
| 📁 **Change Output Directory** | Select a custom output directory | Set a different folder for output       |
| 🗑️ **Delete Playlist File**    | Remove the existing playlist     | Deletes the current playlist file       |
| ℹ️ **Information**             | Show help and usage instructions | Displays user guide and info            |

---

### 📄 Input Format (`playlist.txt`)

*Case-sensitive. The following formats are supported:

#### ✅ Standard Format

```
Panel: http://example.com:80/c/
MAC: 00:1A:79:XX:XX:XX
```

#### ✅ Compact Format

```
http://example.com/c/ # My Portal
00:1A:79:XX:XX:XX
```

#### ✅ Multiple MACs per Portal

```
Portal: http://server.com:8080/c
MAC1: 00:1A:79:AA:AA:AA
MAC2: 00:1A:79:BB:BB:BB
```

#### ✅ Unlabeled MAC

```
Panel http://example.com/c
00:1A:79:XX:XX:XX
```

#### ✅ Shared MAC (for multiple portals)

```
http://server1.com/c/
http://server2.com/c/ # Uses same MAC as server1
00:1A:79:XX:XX:XX
```

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
* Green Label: **"Show Code"**
* Red Label: **"New Code"**
* Below the buttons, you see hints: **"1-SHOW"**, **"0-NEW"**

#### To reveal the full code:

* Press **"1"** on the remote control.
* The full code is shown (e.g., **"Access Code: 123456"**).
* After 10 seconds, it returns to the masked view (e.g., **"12••34"**).

#### To generate a new code:

* Press **"0"** on the remote control.
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

### 📂 Output

* Standard `.m3u` files for each portal
* Grouped and channelized for easy use

---

### 📝 License
This project is licensed under the MIT License - see the LICENSE file for details.


*** by Lululla
