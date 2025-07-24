# Main Setup Instructions
https://docs.google.com/presentation/d/12mHVzGmc3WUwCcRmqWXFlLjLb9-afCsoiGUJaZgbwhg/edit?usp=sharing

# ! LabOps Developement

A powerful Discord bot built with `discord.py` featuring role management, verification, global moderation, temporary roles, alt-account detection, and more. Designed for FiveM and multi-server moderation environments.

## Features

* 🔒 Global Ban/Timeout/Kick Commands
* 🛂 Blacklist System With Commands
* 🧾 Role Request System with Approvals
* ⚙️ Role Assign/Unassign/Temporary Roles
* 🚨 Alt Account Detection and Review System
* 🛠️ Welcome & Auto-Role Configuration
* 🧼 Mass Role Management Tools
* 📊 Server & User Info
* 📷 Avatar Viewer
* ⚠️ Moderation Tools (Purge, Slowmode)
* ⏱️ Set Custom Bot Presence

---

## Commands Overview

### 🧾 Role Management

| Command               | Description                               |
| --------------------- | ----------------------------------------- |
| `/requestrole`        | Request a role, sends to approval channel |
| `/assignrole`         | Assign a role to a user                   |
| `/unassignrole`       | Remove a role from a user                 |
| `/setrolemanager`     | Allow a role to manage roles              |
| `/assignmultiplerole` | Assign up to 10 roles to a user           |

### 🔁 Mass Role Tools

| Command            | Description                                     |
| ------------------ | ----------------------------------------------- |
| `/massrole_add`    | Add a role to all members                       |
| `/massrole_remove` | Remove a role from all members                  |
| `/massrole_allow`  | Allow a role to use mass role commands          |
| `/massunrole`      | Remove all roles from a user (except @everyone) |

### ⏳ Temporary Roles

| Command            | Description                                |
| ------------------ | ------------------------------------------ |
| `/settemprolerole` | Set a role allowed to use temp role system |
| `/temprole`        | Temporarily assign a role to a user        |

### 🌐 Global Moderation

| Command            | Description                                       |
| ------------------ | ------------------------------------------------- |
| `/globalban`       | Ban a user from all servers and send for approval |
| `/unglobalban`     | Unban a user from all servers                     |
| `/globalkick`      | Kick a user from all servers                      |
| `/globaltimeout`   | Timeout a user from all servers                   |
| `/unglobaltimeout` | Remove timeout from all servers                   |
| `/setglobalrole`   | Allow roles to use global commands                |

### ⚙️ Setup & Permissions

| Command               | Description                           |
| --------------------- | ------------------------------------- |
| `/setrequestchannel`  | Set the role request approval channel |
| `/settimeoutrole`     | Allow a role to use timeout commands  |
| `/setaltcheckchannel` | Set the alt detection log channel     |
| `/setaltrole`         | Set role for flagged/denied users     |

### 👤 Alt Detection & Review

| Trigger          | Description                                       |
| ---------------- | ------------------------------------------------- |
| `on_member_join` | Detects new accounts or previously denied members |
| `AltReviewView`  | Buttons to Approve/Deny user                      |
| `/blacklist`     | Blacklist A User                                  |
| `/unblacklist`   | unBlacklist A User                                |

### 🎉 Welcome & Auto-Role

| Command       | Description                                  |
| ------------- | -------------------------------------------- |
| `/setwelcome` | Set welcome channel for new users            |
| `/autorole`   | Automatically assign role on join and log it |

### 🧹 Moderation Tools

| Command     | Description                 |
| ----------- | --------------------------- |
| `/slowmode` | Set channel slowmode        |
| `/purge`    | Delete a number of messages |
| `/ban`      | Ban a user from the server  |

### 🛠️ Utility

| Command       | Description                        |
| ------------- | ---------------------------------- |
| `/avatar`     | Show a user's avatar               |
| `/userinfo`   | Show user info                     |
| `/serverinfo` | Show server info                   |
| `/ping`       | Check bot latency                  |
| `/roleinfo`   | Show info about a role             |
| `/setstatus`  | Set custom bot status and activity |
| `/credits`    | Show developer credits and rights  |

---

## Setup Requirements

* Python 3.8+
* `discord.py` (2.0+)
* Required files:

  * `config.py` (includes `CLIENT_ID`, `BOT_TOKEN`, etc.)
  * `verified_users.json`, `role_managers.json`, etc.
  * See code for specific file requirements

## License

Copyright (c) realcrow2
All rights reserved.

---

## Developer

* **Discord:** realcrow2 (`1228084539138506845`)
* **GitHub:** https://github.com/realcrow2

---

*Contributions and suggestions are welcome. DM on Discord to get in touch.*
)
