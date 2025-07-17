import discord
from discord.ext import commands
from discord.ui import Button, View
from datetime import timedelta
from discord import app_commands, Interaction, Embed, Role, Member, User
from discord.ext import commands, tasks
from typing import Optional, Literal
from discord.ui import View, Button, button
from discord import ButtonStyle
import json
import os
import requests
import config
import contextlib
import traceback
import datetime
import time
import asyncio
import sqlite3
import random

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.bans = True

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
# Replace with your flagged server IDs and log channel ID

# Channels
LOG_CHANNEL_ID = 1395146652628684820  # Replace with your actual log channel ID
channel_id = 1395146652628684820  # Replace with your actual log channel ID
APPROVAL_CHANNEL_ID = 1395146652628684820  # Replace with your actual log channel ID

FLAGGED_SERVER_IDS = { ... }  # Add server IDs here

def load_verified_users():
    if os.path.exists("verified_users.json"):
        with open("verified_users.json", "r") as f:
            return json.load(f)
    return {}

###########################################################
@bot.event
async def on_ready():
    print(f"[DEBUG] on_ready triggered")

    # Attempt to sync application commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    # Print bot identity info
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    # Restore saved status
    try:
        await apply_saved_status()
    except Exception as e:
        print(f"❌ Failed to restore saved status: {e}")

###########################################################
class VerifyView(View):
    def __init__(self):
        super().__init__()
        oauth_url = (
            f"https://discord.com/oauth2/authorize?client_id={config.CLIENT_ID}"
            f"&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Fcallback"
            f"&scope=identify%20guilds"
        )
        self.add_item(Button(label="Click to Verify", url=oauth_url))

@bot.command(name="verify")
async def verify(ctx):
    view = VerifyView()
    await ctx.send("\U0001f510 Please verify using the button below:", view=view)

@bot.command(name="servers")
async def servers(ctx, user: discord.User = None):
    required_role_id = 1373933102396608527
    if not any(role.id == required_role_id for role in ctx.author.roles):
        await ctx.send("\u274c You do not have the required role to use this command.")
        return

    verified_users = load_verified_users()
    target_user = user or ctx.author
    user_id = str(target_user.id)

    if user_id not in verified_users:
        msg = "\u274c That user has not verified." if user else "\u274c You need to verify first! Use `!verify`."
        await ctx.send(msg)
        return

    access_token = verified_users[user_id]
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get("https://discord.com/api/users/@me/guilds", headers=headers)

    if response.status_code != 200:
        await ctx.send("\u274c Failed to fetch guilds. Ask the user to verify again.")
        return

    guilds = response.json()
    if not guilds:
        await ctx.send("\u26a0\ufe0f No guilds found.")
        return

    lines = []
    for guild in guilds:
        guild_id = int(guild["id"])
        name = guild["name"]
        flagged = guild_id in FLAGGED_SERVER_IDS
        prefix = "\ud83d\udea8 FLAGGED: " if flagged else "\u2022 "
        lines.append(f"{prefix}{name}")

    result = "\n".join(lines)
    await ctx.send(f"\u2705 Servers for **{target_user.name}**:\n```{result}```")

class RoleRequestView(View):
    def __init__(self, user: Member, role: Role):
        super().__init__(timeout=None)
        self.user = user
        self.role = role

    # ===================== CONFIG SETUP =====================
REQUEST_CHANNEL_CONFIG_FILE = "request_channel_config.json"

def load_request_channel_config():
    if os.path.exists(REQUEST_CHANNEL_CONFIG_FILE):
        with open(REQUEST_CHANNEL_CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_request_channel_config(data):
    with open(REQUEST_CHANNEL_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

request_channel_config = load_request_channel_config()

# ===================== SET REQUEST CHANNEL COMMAND =====================
@bot.tree.command(name="setrequestchannel", description="Set the channel where role requests will be sent.")
@app_commands.describe(channel="The channel to send role requests to")
async def setrequestchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Only the server owner can set the request channel.", ephemeral=True)
        return

    request_channel_config[str(interaction.guild.id)] = channel.id
    save_request_channel_config(request_channel_config)

    await interaction.response.send_message(f"✅ Role request channel set to {channel.mention}", ephemeral=True)

# ===================== ROLE REQUEST VIEW =====================
class RoleRequestView(View):
    def __init__(self, user: Member, role: Role):
        super().__init__(timeout=None)
        self.user = user
        self.role = role

    @discord.ui.button(label="Approve Role Request", style=discord.ButtonStyle.green)
    async def approve_button(self, interaction: Interaction, button: Button):
        if not has_role_manager_permission(interaction.user):
            await interaction.response.send_message("❌ You don’t have permission to approve this request.", ephemeral=True)
            return

        if interaction.user.top_role <= self.role:
            await interaction.response.send_message("❌ You cannot approve this request; your top role is not high enough.", ephemeral=True)
            return

        await self.user.add_roles(self.role)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_field_at(1, name="Approved By", value=interaction.user.mention, inline=False)
        embed.set_footer(text=f"✅ Role Request Approved by {interaction.user}")

        new_view = View()
        new_view.add_item(Button(label=f"Approved by {interaction.user.name}", style=discord.ButtonStyle.green, disabled=True))

        await interaction.response.edit_message(embed=embed, view=new_view)

    @discord.ui.button(label="Deny Role Request", style=discord.ButtonStyle.red)
    async def deny_button(self, interaction: Interaction, button: Button):
        if not has_role_manager_permission(interaction.user):
            await interaction.response.send_message("❌ You don’t have permission to deny this request.", ephemeral=True)
            return

        if interaction.user.top_role <= self.role:
            await interaction.response.send_message("❌ You cannot deny this request; your top role is not high enough.", ephemeral=True)
            return

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_field_at(1, name="Approved By", value=interaction.user.mention, inline=False)
        embed.set_footer(text=f"❌ Role Request Denied by {interaction.user}")

        new_view = View()
        new_view.add_item(Button(label=f"Denied by {interaction.user.name}", style=discord.ButtonStyle.red, disabled=True))

        await interaction.response.edit_message(embed=embed, view=new_view)

# ===================== /requestrole COMMAND =====================
@bot.tree.command(name="requestrole", description="Request a role to be approved by staff.")
@app_commands.describe(role="The role you are requesting", approver="The staff member you'd like to approve this request (optional)")
async def request_role(interaction: Interaction, role: Role, approver: Member = None):
    embed = Embed(title="Role Request", color=discord.Color.purple())
    embed.add_field(name="Requester", value=f"<@{interaction.user.id}>", inline=False)
    embed.add_field(name="Approved By", value="Pending", inline=False)
    embed.add_field(name="Role", value=f"{role.mention} | {role.name} | {role.id}", inline=False)

    if approver:
        embed.add_field(name="Requested Approver", value=f"<@{approver.id}>", inline=False)

    embed.set_footer(text=f"• Today at {interaction.created_at.strftime('%I:%M %p')}")
    embed.set_author(name=f"@! {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    view = RoleRequestView(user=interaction.user, role=role)

    # ✅ Dynamically get request channel from config
    channel_id = request_channel_config.get(str(interaction.guild.id))
    channel = bot.get_channel(channel_id) if channel_id else None

    if channel:
        await channel.send(content=f"<@{approver.id}>" if approver else None, embed=embed, view=view)
        await interaction.response.send_message("✅ Role request submitted for approval.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Role request channel not set. Ask the owner to use `/setrequestchannel`.", ephemeral=True)

# File path for storing allowed role managers
DATA_FILE = "role_managers.json"

# Load allowed role manager roles from JSON file
def load_role_managers():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

# Save allowed role manager roles to JSON file
def save_role_managers(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Load data on startup
allowed_role_managers = load_role_managers()


# Helper: Check if user has a role manager role
def has_role_manager_permission(member: Member):
    guild_roles = allowed_role_managers.get(str(member.guild.id), [])
    return any(role.id in guild_roles for role in member.roles)


### /setrolemanager command ###
@bot.tree.command(name="setrolemanager", description="Allow a role to use /assignrole and /unassignrole and /requestrole Approval and denying.")
@app_commands.describe(role="The role to grant permission")
async def setrolemanager(interaction: Interaction, role: Role):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Only the server owner can use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)

    if guild_id not in allowed_role_managers:
        allowed_role_managers[guild_id] = []

    if role.id in allowed_role_managers[guild_id]:
        await interaction.response.send_message(f"ℹ️ {role.mention} already has permission.", ephemeral=True)
        return

    allowed_role_managers[guild_id].append(role.id)
    save_role_managers(allowed_role_managers)

    await interaction.response.send_message(f"✅ {role.mention} can now use `/assignrole` and `/unassignrole` & Approve Role Request.", ephemeral=True)


### /assignrole command ###
@bot.tree.command(name="assignrole", description="Assign a role to a user.")
@app_commands.describe(user="The user to assign the role to", role="The role to assign")
async def assignrole(interaction: Interaction, user: Member, role: Role):
    if not has_role_manager_permission(interaction.user):
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return

    if role >= interaction.user.top_role:
        await interaction.response.send_message("❌ You can only assign roles lower than your top role.", ephemeral=True)
        return

    await user.add_roles(role)
    embed = Embed(title="✅ Role Assigned", description=f"{role.mention} has been added to {user.mention}.", color=discord.Color.green())
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


### /unassignrole command ###
@bot.tree.command(name="unassignrole", description="Remove a role from a user.")
@app_commands.describe(user="The user to remove the role from", role="The role to remove")
async def unassignrole(interaction: Interaction, user: Member, role: Role):
    if not has_role_manager_permission(interaction.user):
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return

    if role >= interaction.user.top_role:
        await interaction.response.send_message("❌ You can only remove roles lower than your top role.", ephemeral=True)
        return

    await user.remove_roles(role)
    embed = Embed(title="🗑️ Role Removed", description=f"{role.mention} has been removed from {user.mention}.", color=discord.Color.red())
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

##### Mass Unrole #####
@bot.tree.command(name="massunrole", description="Remove all roles from a user and list them in an embed.")
@app_commands.describe(user="The user to remove all roles from")
async def massunrole(interaction: Interaction, user: Member):
    # Defer response to prevent timeout
    await interaction.response.defer()

    if not interaction.user.guild_permissions.manage_roles:
        await interaction.followup.send("❌ You don't have permission to use this command.", ephemeral=True)
        return

    roles_to_remove = [
        role for role in user.roles
        if role != interaction.guild.default_role and role < interaction.user.top_role
    ]

    if not roles_to_remove:
        await interaction.followup.send(f"⚠️ {user.mention} has no removable roles.", ephemeral=True)
        return

    try:
        # Remove roles one by one in case of permission issues or large role sets
        for role in roles_to_remove:
            await user.remove_roles(role, reason="Mass role removal")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to remove roles: {e}", ephemeral=True)
        return

    # Prepare removed roles list for embed
    removed_roles_list = "\n".join([f"- {role.mention}" for role in roles_to_remove])
    removed_roles_list = removed_roles_list[:3500] or "None"

    embed = discord.Embed(
        title="🧹 Mass Role Removal",
        description=f"Removed all removable roles from {user.mention}.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Removed Roles", value=removed_roles_list, inline=False)
    embed.set_footer(text=f"Action performed by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)

# Global role permission config
GLOBAL_ROLE_CONFIG_FILE = "global_role_config.json"
if os.path.exists(GLOBAL_ROLE_CONFIG_FILE):
    with open(GLOBAL_ROLE_CONFIG_FILE, "r") as f:
        global_role_config = json.load(f)
else:
    global_role_config = {}

# Utility to check global permission
async def is_globally_authorized(interaction: discord.Interaction) -> bool:
    guild = interaction.guild
    if not guild:
        return False

    if guild.owner_id == interaction.user.id:
        return True

    allowed_roles = global_role_config.get(str(guild.id), [])
    user_role_ids = [role.id for role in interaction.user.roles]

    return any(role_id in user_role_ids for role_id in allowed_roles)

# /setglobalrole command
@bot.tree.command(name="setglobalrole", description="Set roles allowed to use global moderation commands.")
@app_commands.describe(role="Role to allow access to global moderation commands")
async def setglobalrole(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Only the server owner can set the global roles.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    if guild_id not in global_role_config:
        global_role_config[guild_id] = []

    if role.id in global_role_config[guild_id]:
        await interaction.response.send_message(f"⚠️ `{role.name}` is already authorized.", ephemeral=True)
        return

    global_role_config[guild_id].append(role.id)

    with open(GLOBAL_ROLE_CONFIG_FILE, "w") as f:
        json.dump(global_role_config, f)

    await interaction.response.send_message(f"✅ `{role.name}` has been added to global role permissions.", ephemeral=True)

# === APPROVAL VIEW ===
class StyledGlobalBanView(View):
    def __init__(self, user: discord.User, reason: str, server: str, requester: discord.Member):
        super().__init__(timeout=None)
        self.user = user
        self.reason = reason
        self.server = server
        self.requester = requester

    def is_authorized(self, member: discord.Member) -> bool:
        guild_id = str(member.guild.id)
        allowed_roles = global_role_config.get(guild_id, [])
        user_role_ids = [r.id for r in member.roles]

        return (
            member.guild.owner_id == member.id or
            any(rid in allowed_roles for rid in user_role_ids)
        )

    @discord.ui.button(label="Approve Ban", style=ButtonStyle.success)
    async def approve(self, interaction: Interaction, button: Button):
        if not self.is_authorized(interaction.user):
            return await interaction.response.send_message("❌ You don't have permission to approve.", ephemeral=True)

        if interaction.user.id == self.requester.id:
            return await interaction.response.send_message("❌ You cannot approve your own blacklist request.", ephemeral=True)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="Status", value=f"✅ Approved by {interaction.user.mention}", inline=False)
        embed.set_footer(text=f"✅ Ban Approved by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        view = View()
        view.add_item(Button(label=f"✅ Approved by {interaction.user.display_name}", style=ButtonStyle.success, disabled=True))

        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Deny", style=ButtonStyle.danger)
    async def deny(self, interaction: Interaction, button: Button):
        if not self.is_authorized(interaction.user):
            return await interaction.response.send_message("❌ You don't have permission to deny.", ephemeral=True)

        for guild in interaction.client.guilds:
            try:
                await guild.unban(self.user, reason="[GLOBAL BAN REVERSED]")
            except Exception:
                pass

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value=f"❌ Denied by {interaction.user.mention}", inline=False)
        embed.set_footer(text=f"❌ Ban Denied by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        view = View()
        view.add_item(Button(label=f"❌ Denied by {interaction.user.display_name}", style=ButtonStyle.danger, disabled=True))

        await interaction.response.edit_message(embed=embed, view=view)

class ConfirmBlacklistView(View):
    def __init__(self, user: discord.User, reason: str, requester: discord.Member):
        super().__init__(timeout=60)
        self.user = user
        self.reason = reason
        self.requester = requester

    @discord.ui.button(label="Confirm Global Ban", style=ButtonStyle.danger)
    async def confirm(self, interaction: Interaction, button: Button):
        if interaction.user != self.requester:
            return await interaction.response.send_message("Only the command author can confirm this.", ephemeral=True)

        for guild in interaction.client.guilds:
            try:
                await guild.ban(self.user, reason=f"[GLOBAL BLACKLIST] {self.reason}")
            except Exception:
                pass

        receipt_embed = discord.Embed(title="Global Ban", color=discord.Color.green())
        receipt_embed.add_field(name="Houston Blacklist Processed", value="All Systems Operational", inline=False)
        receipt_embed.add_field(name="Status", value=f"{self.user.mention} has been globally banned and sent to Management.", inline=False)
        receipt_embed.set_footer(text=f"Blacklisted by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        await interaction.response.edit_message(embed=receipt_embed, view=None)
        await interaction.channel.send(embed=receipt_embed)

        server_name = interaction.guild.name if interaction.guild else "Unknown Server"
        review_embed = discord.Embed(title="Global Ban Review", color=discord.Color.red())
        review_embed.description = (
            "**Please follow these steps:**\n"
            "- Right click this message and click **Create Thread**\n"
            "- Post evidence (clips, messages, screenshots)\n"
            "- Add more context if needed"
        )
        review_embed.add_field(name="Member", value=f"{self.user.mention}", inline=True)
        review_embed.add_field(name="Member ID", value=f"{self.user.id}", inline=True)
        review_embed.add_field(name="Server", value=server_name, inline=True)
        review_embed.add_field(name="Staff Member", value=self.requester.mention, inline=False)
        review_embed.add_field(name="Reason", value=self.reason, inline=False)
        review_embed.add_field(name="Alt Accounts", value=f"{self.user.mention} Alts: (add manually if needed)", inline=False)
        review_embed.set_footer(text="Waiting for review")

        approval_channel = interaction.client.get_channel(APPROVAL_CHANNEL_ID)
        view = StyledGlobalBanView(user=self.user, reason=self.reason, server=server_name, requester=self.requester)

        if approval_channel:
            message = await approval_channel.send(embed=review_embed, view=view)
            thread = await message.create_thread(name=f"Evidence - {self.user.name}")
            await thread.send(
                f"{self.requester.mention}, please provide evidence for the global ban in this thread.\n\n"
                "**Evidence should include:**\n"
                "- Screenshots\n"
                "- Message links\n"
                "- Detailed explanation\n"
                "- Any additional context"
            )

    @discord.ui.button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: Interaction, button: Button):
        if interaction.user != self.requester:
            return await interaction.response.send_message("Only the command author can cancel.", ephemeral=True)
        await interaction.response.edit_message(content="❌ Blacklist cancelled.", embed=None, view=None)

@bot.tree.command(name="globalban", description="Globally ban a user and submit for staff approval.")
@app_commands.describe(
    user="User to globally ban",
    reason="Reason for the global ban"
)
async def globalblacklist(interaction: Interaction, user: discord.User, reason: str):
    if not await is_globally_authorized(interaction):
        return await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)

    embed = discord.Embed(title="Confirm Global Ban", color=discord.Color.red())
    embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"Action requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    view = ConfirmBlacklistView(user=user, reason=reason, requester=interaction.user)
    await interaction.response.send_message(embed=embed, view=view)
# /unglobalblacklist command
@bot.tree.command(name="unglobalban", description="Remove global blacklist from a user")
@app_commands.describe(user="User to unblacklist")
async def unglobalblacklist(interaction: discord.Interaction, user: discord.User):
    if not await is_globally_authorized(interaction):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    failed_guilds = []
    for guild in bot.guilds:
        try:
            await guild.unban(user, reason="[GLOBAL UNBLACKLIST]")
        except Exception:
            failed_guilds.append(guild.name)

    embed = Embed(title="Global Ban", color=discord.Color.green())
    embed.add_field(name="Houston Blacklist Processed", value="All Systems Operational", inline=False)
    embed.add_field(
        name="Status",
        value=f"{user.mention} has been removed from the global ban list and unbanned from all available servers.",
        inline=False
    )
    embed.set_footer(text=f"Unblacklisted by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=embed)

    await interaction.response.send_message(embed=embed)

class BlacklistBanView(View):
    def __init__(self, banned_user_id, banned_by, reason):
        super().__init__(timeout=None)
        self.banned_user_id = banned_user_id
        self.banned_by = banned_by
        self.reason = reason

    @discord.ui.button(label="Approve ✅", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"✅ Ban for <@{self.banned_user_id}> has been approved and remains active.", ephemeral=True)

    @discord.ui.button(label="Deny ❌", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Logic to unban the user
        await interaction.guild.unban(discord.Object(id=self.banned_user_id))
        await interaction.response.send_message(f"❌ Ban for <@{self.banned_user_id}> has been denied. User has been unbanned.", ephemeral=True)

    @discord.ui.button(label="UnGlobalBan 🔓", style=discord.ButtonStyle.danger)
    async def unglobalban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.guild.unban(discord.Object(id=self.banned_user_id))
        await interaction.response.send_message(f"🔓 User <@{self.banned_user_id}> has been removed from the global blacklist.", ephemeral=True)


@bot.command()
async def blacklistban(ctx, user: discord.User, *, reason: str):
    view = BlacklistBanView(user.id, ctx.author.id, reason)

    # Ban logic (global network API if needed, here just as a placeholder)
    await ctx.guild.ban(user, reason=f"Global Blacklist Ban: {reason}")

    # Send approval message
    channel = bot.get_channel(APPROVAL_CHANNEL_ID)
    msg = await channel.send(
        embed=discord.Embed(
            title="🔒 Global Ban Request",
            description=f"**User:** <@{user.id}> (`{user.id}`)\n"
                        f"**Banned by:** <@{ctx.author.id}> (`{ctx.author.id}`)\n"
                        f"**Reason:** {reason}",
            color=discord.Color.red()
        ),
        view=view
    )

    # Create thread and ping staff member
    thread = await msg.create_thread(name=f"Proof: {user.name}")
    await thread.send(f"<@{ctx.author.id}> please provide proof for the blacklist ban of <@{user.id}>.")

# /globalkick command
@bot.tree.command(name="globalkick", description="Globally kick a user from all servers")
@app_commands.describe(user="User to globally kick", reason="Reason for kicking")
async def globalkick(interaction: discord.Interaction, user: discord.User, reason: str):
    if not await is_globally_authorized(interaction):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    log_embed = discord.Embed(
        title="🚪 Global Kick",
        color=discord.Color.orange(),
        description="Houston Kick Processed, All Systems Operational"
    )
    log_embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
    log_embed.add_field(name="Reason", value=reason, inline=False)
    log_embed.set_footer(text=f"Kicked by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    confirm_embed = discord.Embed(
        description=f"✅ **{user}** has been globally kicked.",
        color=discord.Color.green()
    )

    failed_guilds = []
    for guild in bot.guilds:
        member = guild.get_member(user.id)
        if member:
            try:
                await guild.kick(member, reason=f"[GLOBAL KICK] {reason}")
            except Exception:
                failed_guilds.append(guild.name)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=log_embed)

    await interaction.response.send_message(embed=confirm_embed)
    ########################## Additional Discord Bot Commands#############################

#### SET ACCESS ROLES ####
@bot.tree.command(name="chat_moderation", description="Allow a role to use moderation commands")
@app_commands.describe(role="The role to allow")
async def chat_moderation(interaction: Interaction, role: discord.Role):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Only the server owner can use this command.", ephemeral=True)
        return

    guild_id = interaction.guild_id
    if guild_id not in allowed_roles_per_guild:
        allowed_roles_per_guild[guild_id] = []

    if role.id not in allowed_roles_per_guild[guild_id]:
        allowed_roles_per_guild[guild_id].append(role.id)

    await interaction.response.send_message(f"✅ Role {role.mention} is now allowed to use moderation commands.")

#### ROLE CHECK HELPER ####
def has_moderation_role(member: discord.Member):
    guild_id = member.guild.id
    allowed_roles = allowed_roles_per_guild.get(guild_id, [])
    return any(role.id in allowed_roles for role in member.roles)

#### SLOWMODE COMMAND ####
@bot.tree.command(name="slowmode", description="Set slowmode in the current channel.")
@app_commands.describe(seconds="Slowmode duration in seconds")
async def slowmode(interaction: Interaction, seconds: int):
    if not has_moderation_role(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.channel.edit(slowmode_delay=seconds)
    embed = discord.Embed(
        title="Slowmode Updated",
        description=f"Set to {seconds} seconds.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

#### PURGE COMMAND ####
@bot.tree.command(name="purge", description="Bulk delete messages")
@app_commands.describe(amount="Number of messages to delete")
async def purge(interaction: Interaction, amount: int):
    if not has_moderation_role(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer()
    deleted = await interaction.channel.purge(limit=amount)
    embed = discord.Embed(
        title="Messages Purged",
        description=f"Deleted {len(deleted)} messages.",
        color=discord.Color.red()
    )
    await interaction.followup.send(embed=embed)

#### AVATAR COMMAND ####
@bot.tree.command(name="avatar", description="View someone's avatar")
@app_commands.describe(user="The user whose avatar to show")
async def avatar(interaction: Interaction, user: discord.User = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user.name}'s Avatar", color=discord.Color.blurple())
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

#### USERINFO COMMAND ####
@bot.tree.command(name="userinfo", description="Get user info")
@app_commands.describe(user="The user to lookup")
async def userinfo(interaction: Interaction, user: Member = None):
    user = user or interaction.user
    await interaction.response.defer()

    embed = discord.Embed(title=f"User Info - {user}", color=discord.Color.green())
    embed.add_field(name="Username", value=user.name, inline=True)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Created", value=user.created_at.strftime('%Y-%m-%d %H:%M:%S'), inline=False)
    embed.add_field(name="Joined", value=user.joined_at.strftime('%Y-%m-%d %H:%M:%S'), inline=False)

    roles = [role.mention for role in user.roles if role.name != "@everyone"]
    roles_display = ", ".join(roles) if roles else "No roles"
    embed.add_field(name="Roles", value=roles_display, inline=False)

    embed.set_thumbnail(url=user.display_avatar.url)
    await interaction.followup.send(embed=embed)

#### SERVERINFO COMMAND ####
@bot.tree.command(name="serverinfo", description="Get server information")
async def serverinfo(interaction: Interaction):
    guild = interaction.guild
    embed = discord.Embed(title="Server Info", color=discord.Color.blue())
    embed.add_field(name="Server Name", value=guild.name, inline=True)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Member Count", value=guild.member_count, inline=True)
    embed.add_field(name="Guilds Bot is in", value=f"{len(bot.guilds)}", inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.set_footer(text="Bot Info Requested", icon_url=interaction.user.display_avatar.url)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    await interaction.response.send_message(embed=embed)

#### PING COMMAND ####
@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="Pong!", description=f"Latency: {latency}ms", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed)

#### BAN COMMAND ####
@bot.tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(user="User to ban", reason="Reason for the ban")
async def ban(interaction: Interaction, user: Member, reason: str = "No reason provided"):
    await interaction.guild.ban(user, reason=reason)
    embed = discord.Embed(title="User Banned", description=f"{user} has been banned.\nReason: {reason}", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

#### ROLEINFO COMMAND ####
@bot.tree.command(name="roleinfo", description="Get info about a role")
@app_commands.describe(role="The role to look up")
async def roleinfo(interaction: Interaction, role: discord.Role):
    embed = discord.Embed(title=f"Role Info - {role.name}", color=role.color)
    embed.add_field(name="Role ID", value=role.id, inline=True)
    embed.add_field(name="Color", value=str(role.color), inline=True)
    embed.add_field(name="Members", value=str(len(role.members)), inline=True)
    embed.add_field(name="Mentionable", value=str(role.mentionable), inline=True)
    embed.add_field(name="Created At", value=role.created_at.strftime('%Y-%m-%d %H:%M:%S'), inline=False)
    await interaction.response.send_message(embed=embed)

# Dictionary to store allowed role IDs per guild
allowed_roles_per_guild = {}

###########################################################
# Utility: Check if user has permission to use massrole commands
def is_allowed(member: discord.Member) -> bool:
    allowed_roles = allowed_roles_per_guild.get(member.guild.id, [])
    return any(role.id in allowed_roles for role in member.roles) or member.id == member.guild.owner_id

@bot.tree.command(name="massrole_add", description="Mass add a role to all members below your top role")
@app_commands.describe(role="Role to add to all members")
async def massrole_add(interaction: discord.Interaction, role: discord.Role):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("❌ You don't have permission to use this.", ephemeral=True)

    await interaction.response.defer(thinking=True)

    added = 0
    async for member in interaction.guild.fetch_members(limit=None):
        if role not in member.roles and interaction.user.top_role > role and member != interaction.user:
            try:
                await member.add_roles(role, reason="Mass role add")
                added += 1
            except discord.Forbidden:
                continue
            except Exception as e:
                print(f"Error adding role to {member.name}: {e}")
                continue

    embed = discord.Embed(
        title="✅ Mass Role Add",
        description=f"Added {role.mention} to `{added}` users.",
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed)

###########################################################
@bot.tree.command(name="massrole_remove", description="Mass remove a role from all members")
@app_commands.describe(role="Role to remove from all members")
async def massrole_remove(interaction: discord.Interaction, role: discord.Role):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("❌ You don't have permission to use this.", ephemeral=True)

    await interaction.response.defer(thinking=True)

    removed = 0
    async for member in interaction.guild.fetch_members(limit=None):
        if role in member.roles and interaction.user.top_role > role and member != interaction.user:
            try:
                await member.remove_roles(role, reason="Mass role remove")
                removed += 1
            except discord.Forbidden:
                continue
            except Exception as e:
                print(f"Error removing role from {member.name}: {e}")
                continue

    embed = discord.Embed(
        title="✅ Mass Role Remove",
        description=f"Removed {role.mention} from `{removed}` users.",
        color=discord.Color.red()
    )
    await interaction.followup.send(embed=embed)

###########################################################
@bot.tree.command(name="massrole_allow", description="Allow a role to use massrole commands (Owner only)")
@app_commands.describe(role="Role to allow")
async def massrole_allow(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("❌ Only the server owner can use this command.", ephemeral=True)

    allowed_roles = allowed_roles_per_guild.setdefault(interaction.guild.id, [])
    if role.id not in allowed_roles:
        allowed_roles.append(role.id)

    embed = discord.Embed(
        title="✅ Role Allowed",
        description=f"{role.mention} is now allowed to use massrole commands.",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed)

######################## Temp Role Command ##################################
# In-memory dict to store allowed role per guild
allowed_temprole_roles = {}  # {guild_id: role_id}


@bot.tree.command(name="settemprolerole", description="Set the role allowed to use /temprole")
@app_commands.describe(role="The role allowed to use /temprole")
async def settemprolerole(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Only the server owner can set the allowed role.", ephemeral=True)
        return

    allowed_temprole_roles[interaction.guild.id] = role.id
    await interaction.response.send_message(f"✅ Users with the role {role.mention} can now use `/temprole`.", ephemeral=True)


@bot.tree.command(name="temprole", description="Temporarily assign a role to a user")
@app_commands.describe(
    choices="Add",
    member="The member to modify",
    role="The role to assign temporarily",
    time="Amount of time",
    timetype="Time unit (Minutes, Hours, Days, Weeks, Months)"
)
@app_commands.choices(
    choices=[app_commands.Choice(name="Add", value="add")],
    timetype=[
        app_commands.Choice(name="Minutes", value="minutes"),
        app_commands.Choice(name="Hours", value="hours"),
        app_commands.Choice(name="Days", value="days"),
        app_commands.Choice(name="Weeks", value="weeks"),
        app_commands.Choice(name="Months", value="months")
    ]
)
async def temprole(
    interaction: discord.Interaction,
    choices: app_commands.Choice[str],
    member: discord.Member,
    role: discord.Role,
    time: int,
    timetype: app_commands.Choice[str]
):
    # ✅ Only allow users with the allowed role
    allowed_role_id = allowed_temprole_roles.get(interaction.guild.id)
    if allowed_role_id:
        allowed_role = interaction.guild.get_role(allowed_role_id)
        if allowed_role not in interaction.user.roles and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("❌ You don't have the required role to use this command.", ephemeral=True)
            return
    else:
        await interaction.response.send_message("⚠️ No allowed role set. Ask the server owner to use `/settemprolerole`.", ephemeral=True)
        return

    if choices.value != "add":
        await interaction.response.send_message("❌ Only 'Add' is supported for now.", ephemeral=True)
        return

    # ✅ Role hierarchy check
    author_top_role = interaction.user.top_role
    if role >= author_top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ You can't assign a role higher or equal to your highest role.", ephemeral=True)
        return

    multipliers = {
        "minutes": 60,
        "hours": 3600,
        "days": 86400,
        "weeks": 604800,
        "months": 2592000  # Approximate
    }

    seconds = time * multipliers[timetype.value]

    try:
        await member.add_roles(role, reason="Temporary role assigned")
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to add that role.", ephemeral=True)
        return
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to add role: {e}", ephemeral=True)
        return

    remove_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    timestamp = int(remove_time.timestamp())

    embed = discord.Embed(
        title="Temporary Role Assigned ✅",
        description=f"{role.mention} added to {member.mention} for **{time} {timetype.name}**.\n"
                    f"⏳ Will be removed <t:{timestamp}:R>",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

    # Background task to remove role
    async def remove_later(member: discord.Member, role: discord.Role, delay: int):
        await asyncio.sleep(delay)
        try:
            guild_member = interaction.guild.get_member(member.id)
            if guild_member and role in guild_member.roles:
                await guild_member.remove_roles(role, reason="Temporary role expired")
                print(f"✅ Role {role.name} removed from {guild_member.display_name}")
            else:
                print(f"⚠️ Role {role.name} not found on member at removal time.")
        except Exception as e:
            print(f"❌ Failed to remove role: {e}")

    asyncio.create_task(remove_later(member, role, seconds))
# ✅ 1. Load/save functions go first
def load_welcome_data():
    if os.path.exists(WELCOME_FILE):
        with open(WELCOME_FILE, "r") as f:
            return json.load(f)
    return {}

def save_welcome_data(data):
    with open(WELCOME_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ✅ 2. Set welcome channel command
@bot.tree.command(name="setwelcome", description="Set the welcome channel for new members.")
@app_commands.describe(channel="The channel to send welcome messages in")
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ You must be an admin to use this command.", ephemeral=True
        )
        return

    data = load_welcome_data()
    data[str(interaction.guild.id)] = channel.id
    save_welcome_data(data)

    await interaction.response.send_message(
        f"✅ Welcome channel set to {channel.mention}", ephemeral=True
    )

# ✅ 3. Send message when someone joins
@bot.event
async def on_member_join(member: discord.Member):
    data = load_welcome_data()
    guild_id = str(member.guild.id)

    if guild_id in data:
        channel = member.guild.get_channel(data[guild_id])
        if channel:
            await channel.send(f"👋 Welcome to the server, {member.mention}!")
CONFIG_FILE = "autorole_config.json"

# Load/save functions
def load_autorole_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_autorole_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(autorole_config, f, indent=4)

autorole_config = load_autorole_config()

# Confirmation button UI
class ConfirmAutoRole(discord.ui.View):
    def __init__(self, author: discord.User, channel: discord.TextChannel, role: discord.Role):
        super().__init__(timeout=60)
        self.author = author
        self.channel = channel
        self.role = role

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ You can't interact with this.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        autorole_config[str(interaction.guild.id)] = {
            "channel_id": self.channel.id,
            "role_id": self.role.id
        }
        save_autorole_config()  # Save to file

        embed = discord.Embed(
            title="✅ Auto Role Enabled",
            description=f"New members will receive {self.role.mention} when they join.",
            color=discord.Color.green()
        )
        embed.add_field(name="Notification Channel", value=self.channel.mention)
        embed.set_footer(text=f"Set by {self.author.name}")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Auto role setup cancelled.", embed=None, view=None)
        self.stop()

# Slash command to set auto-role
@bot.tree.command(name="autorole", description="Set an auto-role to give members when they join.")
@app_commands.describe(channel="The channel for join notifications", role="The role to give on join")
async def autorole(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    if interaction.user != interaction.guild.owner:
        return await interaction.response.send_message("❌ Only the server owner can use this command.", ephemeral=True)

    embed = discord.Embed(
        title="⚙️ Confirm Auto Role Setup",
        description="Please confirm the following auto role configuration:",
        color=discord.Color.orange()
    )
    embed.add_field(name="Role to Assign", value=role.mention, inline=True)
    embed.add_field(name="Notification Channel", value=channel.mention, inline=True)
    embed.set_footer(text=f"Action requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

    view = ConfirmAutoRole(interaction.user, channel, role)
    await interaction.response.send_message(embed=embed, view=view)

# Event that triggers when a member joins
@bot.event
async def on_member_join(member: discord.Member):
    config = autorole_config.get(str(member.guild.id))
    if config:
        role = member.guild.get_role(config["role_id"])
        channel = member.guild.get_channel(config["channel_id"])
        if role:
            try:
                await member.add_roles(role, reason="Auto role on join")
                if channel:
                    embed = discord.Embed(
                        title="🎉 New Member Joined!",
                        description=f"Welcome to the server, {member.mention}!",
                        color=discord.Color.blurple()
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.add_field(name="Role Assigned", value=role.mention, inline=True)
                    embed.set_footer(text=f"Member Count: {member.guild.member_count}")
                    await channel.send(content=member.mention, embed=embed)
            except discord.Forbidden:
                print(f"Missing permissions to assign {role.name} in {member.guild.name}")            
# ------------------------ Mappings ------------------------
status_mapping = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.do_not_disturb,
    "invisible": discord.Status.invisible,
}

activity_mapping = {
    "playing": discord.ActivityType.playing,
    "streaming": discord.ActivityType.streaming,
    "listening": discord.ActivityType.listening,
    "watching": discord.ActivityType.watching,
    "competing": discord.ActivityType.competing,
}

STATUS_FILE = "bot_status.json"

def save_status(status: str, activity_type: str, activity_text: str):
    with open(STATUS_FILE, "w") as f:
        json.dump({
            "status": status,
            "activity_type": activity_type,
            "activity_text": activity_text
        }, f)
    print(f"[SAVED] {status=} {activity_type=} {activity_text=}")

def load_status():
    if not os.path.exists(STATUS_FILE):
        return None
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load status file: {e}")
        return None

async def apply_saved_status():
    data = load_status()
    if not data:
        print("[INFO] No status to restore.")
        return

    status = data["status"]
    activity_type = data["activity_type"]
    activity_text = data["activity_text"]

    if status == "invisible":
        await bot.change_presence(status=discord.Status.invisible, activity=None)
        print("[STATUS] Restored to Invisible (no activity)")
        return

    name = f"Protecting {activity_text}" if activity_type == "playing" else activity_text
    activity = discord.Activity(type=activity_mapping[activity_type], name=name)
    await bot.change_presence(status=status_mapping[status], activity=activity)

    print(f"[STATUS] Restored to {status} - {activity_type} {name}")

@bot.tree.command(name="setstatus", description="Set the bot's status and activity (Server Owner Only).")
@app_commands.describe(
    status="The bot's status",
    activity_type="The type of activity",
    activity_text="The activity description"
)
@app_commands.choices(
    status=[
        app_commands.Choice(name="Online", value="online"),
        app_commands.Choice(name="Idle", value="idle"),
        app_commands.Choice(name="Do Not Disturb", value="dnd"),
        app_commands.Choice(name="Invisible", value="invisible"),
    ],
    activity_type=[
        app_commands.Choice(name="Protecting", value="playing"),
        app_commands.Choice(name="Streaming", value="streaming"),
        app_commands.Choice(name="Listening", value="listening"),
        app_commands.Choice(name="Watching", value="watching"),
        app_commands.Choice(name="Competing", value="competing"),
    ]
)
async def setstatus(
    interaction: discord.Interaction,
    status: app_commands.Choice[str],
    activity_type: app_commands.Choice[str],
    activity_text: str
):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Only the server owner can use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    name = f"Protecting {activity_text}" if activity_type.value == "playing" else activity_text
    activity = None if status.value == "invisible" else discord.Activity(type=activity_mapping[activity_type.value], name=name)
    status_obj = status_mapping[status.value]

    await bot.change_presence(status=status_obj, activity=activity)
    save_status(status.value, activity_type.value, activity_text)

    await interaction.followup.send(
        embed=discord.Embed(
            title="✅ Bot Status Updated",
            description=f"**Status:** {status.name}\n**Activity:** {activity_type.name} {name}",
            color=discord.Color.green()
        )
    )
# Load role config from file
ROLE_CONFIG_FILE = "timeout_role_config.json"
if os.path.exists(ROLE_CONFIG_FILE):
    with open(ROLE_CONFIG_FILE, "r") as f:
        timeout_role_config = json.load(f)
else:
    timeout_role_config = {}

# Helper to check authorization
async def is_authorized(interaction: discord.Interaction) -> bool:
    guild = interaction.guild
    if not guild:
        return False

    # Server owner always allowed
    if guild.owner_id == interaction.user.id:
        return True

    timeout_role_ids = timeout_role_config.get(str(guild.id), [])
    if not isinstance(timeout_role_ids, list):
        timeout_role_ids = [timeout_role_ids]  # backward compatibility

    for role_id in timeout_role_ids:
        role = guild.get_role(role_id)
        if role and role in interaction.user.roles:
            return True

    return False

# Set Timeout Role Command
@bot.tree.command(name="settimeoutrole", description="Set the roles allowed to use global timeout")
@app_commands.describe(role="Role allowed to use global timeout")
async def settimeoutrole(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Only the server owner can set the timeout roles.", ephemeral=True)
        return

    guild_id_str = str(interaction.guild.id)
    timeout_role_ids = timeout_role_config.get(guild_id_str, [])
    if not isinstance(timeout_role_ids, list):
        timeout_role_ids = [timeout_role_ids]  # backward compatibility

    if role.id in timeout_role_ids:
        await interaction.response.send_message(f"⚠️ `{role.name}` is already an authorized timeout role.", ephemeral=True)
        return

    timeout_role_ids.append(role.id)
    timeout_role_config[guild_id_str] = timeout_role_ids

    with open(ROLE_CONFIG_FILE, "w") as f:
        json.dump(timeout_role_config, f)

    await interaction.response.send_message(f"✅ `{role.name}` has been added to the list of timeout roles.", ephemeral=True)

# Global Timeout Command
@bot.tree.command(name="globaltimeout", description="Globally timeout a user from all servers.")
@app_commands.describe(user="User to timeout", duration="Duration (1m, 1h, 1d, 1w)", reason="Reason for timeout")
async def globaltimeout(interaction: discord.Interaction, user: discord.User, duration: str, reason: str):
    if not await is_authorized(interaction):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    if user.id == interaction.user.id:
        await interaction.response.send_message("❌ You cannot timeout yourself.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        multipliers = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
        unit = duration[-1].lower()
        amount = int(duration[:-1])
        if unit not in multipliers:
            raise ValueError("Invalid time unit")
        seconds = amount * multipliers[unit]
        timeout_delta = timedelta(seconds=seconds)
    except:
        await interaction.followup.send("❌ Invalid duration format. Use `1m`, `1h`, `1d`, or `1w`.")
        return

    for guild in bot.guilds:
        member = guild.get_member(user.id)
        if member:
            try:
                await member.timeout(timeout_delta, reason=f"[GLOBAL TIMEOUT] {reason}")
            except:
                pass

    embed = discord.Embed(
        title="**Global Timeout Executed**",
        description=(
            "**Houston Timeout Processed**\n"
            "All Systems Operational\n\n"
            "**Status**\n"
            f"{user.mention} has been timed out from all available servers for **{duration}**.\n"
            f"**Reason:** {reason}"
        ),
        color=0x00FF00
    )
    embed.set_footer(text=f"⏱️ Timed out by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=embed)

# Global Untimeout Command
@bot.tree.command(name="unglobaltimeout", description="Remove global timeout from a user.")
@app_commands.describe(user="User to untimeout")
async def unglobaltimeout(interaction: discord.Interaction, user: discord.User):
    if not await is_authorized(interaction):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer()

    for guild in bot.guilds:
        member = guild.get_member(user.id)
        if member:
            try:
                await member.timeout(None, reason="[GLOBAL UNTIMEOUT] Manual removal")
            except:
                pass

    embed = discord.Embed(
        title="**Global Timeout Removed**",
        description=(
            "**Houston Timeout Removal Processed**\n"
            "All Systems Operational\n\n"
            "**Status**\n"
            f"{user.mention} has been un-timed out and restored across all available servers."
        ),
        color=0x57F287
    )
    embed.set_footer(text=f"🔓 Un-timed out by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=embed)
@bot.tree.command(name="credits", description="Show bot development credits and rights.")
async def credits(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Bot Credits & Rights",
        description="Information about the bot's development and usage.",
        color=discord.Color.purple()
    )

    embed.add_field(name="👤 Developed By", value="**realcrow2**", inline=False)
    embed.add_field(name="🆔 Discord ID", value="`1228084539138506845`", inline=False)
    embed.add_field(
        name="📦 Built With",
        value=(
            "- Python 3.8+\n"
            "- discord.py (App Commands)\n"
            "- Custom persistent systems for roles, moderation, and global tools"
        ),
        inline=False
    )
    embed.add_field(
        name="🔒 Rights & Usage",
        value=(
            "This bot was developed by realcrow2 for personal or community use.\n"
            "Redistribution, resale, or cloning without permission is prohibited.\n"
            "All systems and code are owned by realcrow2."
        ),
        inline=False
    )
    embed.set_footer(text="For questions or support, contact realcrow2 on Discord.")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="assignmultiplerole", description="Assign up to 10 roles to a user")
@app_commands.describe(
    user="User to assign roles to",
    role1="Role 1",
    role2="Role 2",
    role3="Role 3",
    role4="Role 4",
    role5="Role 5",
    role6="Role 6",
    role7="Role 7",
    role8="Role 8",
    role9="Role 9",
    role10="Role 10"
)
async def assignmultiplerole(
    interaction: discord.Interaction,
    user: discord.Member,
    role1: discord.Role = None,
    role2: discord.Role = None,
    role3: discord.Role = None,
    role4: discord.Role = None,
    role5: discord.Role = None,
    role6: discord.Role = None,
    role7: discord.Role = None,
    role8: discord.Role = None,
    role9: discord.Role = None,
    role10: discord.Role = None
):
    if not await is_globally_authorized(interaction):
        return await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)

    roles = [r for r in [role1, role2, role3, role4, role5, role6, role7, role8, role9, role10] if r is not None]
    if not roles:
        return await interaction.response.send_message("⚠️ You must provide at least one role.", ephemeral=True)

    added_roles = []
    failed_roles = []

    for role in roles:
        if role in user.roles:
            continue
        try:
            await user.add_roles(role, reason=f"Assigned by {interaction.user}")
            added_roles.append(role.name)
        except discord.Forbidden:
            failed_roles.append(role.name)
        except discord.HTTPException:
            failed_roles.append(role.name)

    embed = discord.Embed(title="🎯 Role Assignment", color=discord.Color.blurple())
    embed.add_field(name="User", value=f"{user.mention}", inline=False)
    if added_roles:
        embed.add_field(name="✅ Roles Added", value=", ".join(added_roles), inline=False)
    if failed_roles:
        embed.add_field(name="❌ Failed Roles", value=", ".join(failed_roles), inline=False)
    embed.set_footer(text=f"Assigned by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.response.send_message(embed=embed)

###############################################################################
# Alt-Account Checker Bot Module
# Python 3.8+ with discord.py v2.x
###############################################################################
import discord
from discord import app_commands
from datetime import datetime, timedelta, timezone
import json, os

# ------------------ Config Paths ------------------
ALT_CH_CONFIG_FILE = "alt_check_channels.json"     # guild_id : channel_id
ALT_ROLE_CONFIG_FILE = "alt_roles.json"            # guild_id : role_id
DENIED_USERS_FILE = "denied_users.json"            # guild_id : [user_ids]
GLOBAL_ROLE_CONFIG_FILE = "global_roles.json"      # guild_id : [role_ids]

# ------------------ In‑Memory Stores -------------
ALT_CH_CONFIG: dict[str, int] = {}
ALT_ROLE_CONFIG: dict[str, int] = {}
DENIED_USERS: dict[str, list[int]] = {}
global_role_config: dict[str, list[int]] = {}

# ------------------ Load/Save Helpers -------------

def load_configs():
    """Load all JSON configs into memory."""
    for path, target in [
        (ALT_CH_CONFIG_FILE, ALT_CH_CONFIG),
        (ALT_ROLE_CONFIG_FILE, ALT_ROLE_CONFIG),
        (DENIED_USERS_FILE, DENIED_USERS),
        (GLOBAL_ROLE_CONFIG_FILE, global_role_config),
    ]:
        if os.path.isfile(path):
            with open(path, "r") as f:
                target.update(json.load(f))


def save_json(path: str, data: dict):
    """Persist a single config dict to disk."""
    with open(path, "w") as f:
        json.dump(data, f)


def user_is_authorized(inter: discord.Interaction) -> bool:
    """Return True if interaction user is owner or has a global mod role."""
    if inter.user.id == inter.guild.owner_id:
        return True
    ids = global_role_config.get(str(inter.guild.id), [])
    return any(r.id in ids for r in inter.user.roles)


async def ensure_denied_role(guild: discord.Guild) -> discord.Role:
    """Fetch or create the role that marks denied users."""
    gid = str(guild.id)
    role_id = ALT_ROLE_CONFIG.get(gid)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return role

    # Fallback to a default role name
    role = discord.utils.get(guild.roles, name="Censored member")
    if role is None:
        role = await guild.create_role(
            name="Censored member",
            colour=discord.Colour.red(),
            reason="Alt-check denial role created automatically"
        )
    return role

# ---------------------------------------------------------------------------
# Slash Commands
# ---------------------------------------------------------------------------

@bot.tree.command(name="setaltcheckchannel", description="Owner‑only: set the channel for alt‑check embeds.")
@app_commands.describe(channel="Channel to send alt‑check embeds")
async def setaltcheckchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Only the server owner can do this.", ephemeral=True)
        return

    ALT_CH_CONFIG[str(interaction.guild.id)] = channel.id
    save_json(ALT_CH_CONFIG_FILE, ALT_CH_CONFIG)
    await interaction.response.send_message(f"✅ Alt‑check embeds will go to {channel.mention}.", ephemeral=True)


@bot.tree.command(name="setaltrole", description="Owner‑only: set the role applied when users are denied.")
@app_commands.describe(role="Role to apply to denied users")
async def setaltrole(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Only the server owner can set the alt‑check role.", ephemeral=True)
        return

    ALT_ROLE_CONFIG[str(interaction.guild.id)] = role.id
    save_json(ALT_ROLE_CONFIG_FILE, ALT_ROLE_CONFIG)
    await interaction.response.send_message(f"✅ `{role.name}` will now be applied to denied users.", ephemeral=True)

# ---------------------------------------------------------------------------
# Approval / Denial Button View
# ---------------------------------------------------------------------------

class AltReviewView(discord.ui.View):
    """Buttons for approving or denying a flagged member."""

    def __init__(self, member: discord.Member):
        super().__init__(timeout=86400)  # 24 h
        self.member = member

    async def _not_allowed(self, interaction: discord.Interaction):
        await interaction.response.send_message("🚫 You aren't allowed to do that.", ephemeral=True)

    # ---------------- Approve ----------------
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, inter: discord.Interaction, _: discord.ui.Button):
        if not user_is_authorized(inter):
            return await self._not_allowed(inter)

        gid = str(inter.guild.id)

        # Remove from denied list & role if there
        if self.member.id in DENIED_USERS.get(gid, []):
            DENIED_USERS[gid].remove(self.member.id)
            save_json(DENIED_USERS_FILE, DENIED_USERS)
            role = await ensure_denied_role(inter.guild)
            if role in self.member.roles:
                await self.member.remove_roles(role, reason="Alt‑check approved")

        embed = inter.message.embeds[0]
        embed.add_field(name="Status", value=f"✅ **Approved** by {inter.user.mention}", inline=False)
        for c in self.children:
            c.disabled = True
        await inter.message.edit(embed=embed, view=self)
        await inter.response.send_message("Approved and role removed (if any). 👍", ephemeral=True)
        self.stop()

    # ---------------- Deny -------------------
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="⛔")
    async def deny(self, inter: discord.Interaction, _: discord.ui.Button):
        if not user_is_authorized(inter):
            return await self._not_allowed(inter)

        role = await ensure_denied_role(inter.guild)
        await self.member.add_roles(role, reason="Alt‑check denied")

        gid = str(inter.guild.id)
        DENIED_USERS.setdefault(gid, [])
        if self.member.id not in DENIED_USERS[gid]:
            DENIED_USERS[gid].append(self.member.id)
            save_json(DENIED_USERS_FILE, DENIED_USERS)

        embed = inter.message.embeds[0]
        embed.add_field(name="Status", value=f"⛔ **Denied** by {inter.user.mention}", inline=False)
        for c in self.children:
            c.disabled = True
        await inter.message.edit(embed=embed, view=self)
        await inter.response.send_message("Denied and role applied. 🚫", ephemeral=True)
        self.stop()

# ---------------------------------------------------------------------------
# Member Join Listener
# ---------------------------------------------------------------------------

@bot.event
async def on_member_join(member: discord.Member):
    """Triggered whenever a member (not a bot) joins."""
    if member.bot:
        return

    gid = str(member.guild.id)
    previously_denied = member.id in DENIED_USERS.get(gid, [])

    # Reapply restriction role immediately if they were denied before
    if previously_denied:
        role = await ensure_denied_role(member.guild)
        await member.add_roles(role, reason="Rejoined - reapplying denial role")

    account_age = datetime.now(timezone.utc) - member.created_at

    # If not previously denied AND account age acceptable, do nothing
    if not previously_denied and account_age >= timedelta(days=30 * 5):
        return

    channel_id = ALT_CH_CONFIG.get(gid)
    if not channel_id:
        return

    channel = member.guild.get_channel(channel_id)
    if not channel:
        return

    # Select embed style
    if previously_denied:
        title = "🟠 Previously Denied Member Rejoined"
        colour = discord.Colour.orange()
        description = (
            f"{member.mention} was previously **denied** and has rejoined the server.\n"
            "Use the buttons below to approve or deny again."
        )
    else:
        title = "⚠️ Possible Alt Account Detected"
        colour = discord.Colour.gold()
        description = (
            f"{member.mention} joined but their account is only **{account_age.days} days** old.\n"
            "Use the buttons below to approve or deny."
        )

    emb = discord.Embed(title=title, description=description, colour=colour, timestamp=datetime.utcnow())
    emb.set_author(name=str(member), icon_url=member.display_avatar.url)
    await channel.send(embed=emb, view=AltReviewView(member))

BLACKLIST_FILE = "blacklist.json"

def load_blacklist():
    return json.load(open(BLACKLIST_FILE)) if os.path.exists(BLACKLIST_FILE) else {}

def save_blacklist(data):
    with open(BLACKLIST_FILE, "w") as f:
        json.dump(data, f, indent=4)

blacklisted_users = load_blacklist()

def is_user_blacklisted(user_id: int) -> bool:
    return str(user_id) in blacklisted_users

@bot.tree.command(name="blacklist", description="Blacklist a user from using the bot")
@app_commands.describe(user="User to blacklist", reason="Reason for blacklisting")
async def blacklist(interaction: Interaction, user: discord.User, reason: str):
    if not await is_globally_authorized(interaction):
        return await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)

    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)

    member = guild.get_member(user.id)
    if member is None:
        return await interaction.response.send_message("❌ User must be in the server to be blacklisted and assigned a role.", ephemeral=True)

    user_id = str(user.id)
    if user_id in blacklisted_users:
        return await interaction.response.send_message(f"⚠️ {user.mention} is already blacklisted.", ephemeral=True)

    blacklisted_users[user_id] = {
        "reason": reason,
        "blacklisted_by": interaction.user.id,
        "timestamp": datetime.utcnow().isoformat()
    }
    save_blacklist(blacklisted_users)

    # Assign blacklist role and remove all others
    role_id = 1395337907774034031
    role = guild.get_role(role_id)
    if role is not None:
        try:
            # Remove all roles except the blacklist role
            roles_to_remove = [r for r in member.roles if r.id != guild.id and r != role]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Blacklisted: {reason}")
            
            # Add the blacklist role (if they don't already have it)
            if role not in member.roles:
                await member.add_roles(role, reason=f"Blacklisted: {reason}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I don't have permission to modify roles for this user.", ephemeral=True)
        except discord.HTTPException:
            return await interaction.response.send_message("❌ Failed to modify roles due to an unexpected error.", ephemeral=True)
    else:
        return await interaction.response.send_message("❌ Blacklist role not found in this server.", ephemeral=True)

    # Confirmation embed
    embed = discord.Embed(title="🚫 User Blacklisted", color=discord.Color.red())
    embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"Blacklisted by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unblacklist", description="Remove a user from the blacklist")
@app_commands.describe(user="User to unblacklist")
async def unblacklist(interaction: Interaction, user: discord.User):
    if not await is_globally_authorized(interaction):
        return await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)

    user_id = str(user.id)
    if user_id not in blacklisted_users:
        return await interaction.response.send_message(f"ℹ️ {user.mention} is not blacklisted.", ephemeral=True)

    del blacklisted_users[user_id]
    save_blacklist(blacklisted_users)

    guild = interaction.guild
    if guild:
        member = guild.get_member(user.id)
        if member:
            role_id = 1395337907774034031
            role = guild.get_role(role_id)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="User unblacklisted")
                except discord.Forbidden:
                    return await interaction.response.send_message("❌ I don't have permission to remove the blacklist role.", ephemeral=True)
                except discord.HTTPException:
                    return await interaction.response.send_message("❌ Failed to remove the blacklist role due to an unexpected error.", ephemeral=True)

    embed = discord.Embed(title="✅ User Unblacklisted", color=discord.Color.green())
    embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
    embed.set_footer(text=f"Unblacklisted by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.response.send_message(embed=embed)

# ---------------------------------------------------------------------------
# on_ready
# ---------------------------------------------------------------------------

@bot.tree.command(
    name="sync",
    description="Owner-only (plus Crow) • Force-sync all application commands",
)
async def sync_commands(interaction: discord.Interaction):
    ALLOWED_IDS = {
        interaction.guild.owner_id,   # server owner
        1228084539138506845           # Crow  (replace with the ID you gave)
    }

    if interaction.user.id not in ALLOWED_IDS:
        return await interaction.response.send_message(
            "❌ You don’t have permission to sync commands.", ephemeral=True
        )

    await interaction.response.defer(thinking=True, ephemeral=True)

    synced = await bot.tree.sync()
    await interaction.followup.send(
        f"✅ Synced **{len(synced)}** application commands.", ephemeral=True
    )

@bot.event
async def on_ready():
    load_configs()
    print(f"Logged in as {bot.user} (ID {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print("Slash‑command sync failed:", e)
# Run the bot
bot.run(config.BOT_TOKEN)
