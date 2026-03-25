import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

TOKEN = os.getenv("TOKEN")
RULES_CHANNEL = "rules"
SESSIONS_CHANNEL = "sessions"
PROFILE_CHANNELS = ["brat", "mb"]
ROLES_CHANNEL = "roles"

# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────

def load_profiles():
    if os.path.exists("profiles.json"):
        with open("profiles.json", "r") as f:
            return json.load(f)
    return {}

def save_profiles(data):
    with open("profiles.json", "w") as f:
        json.dump(data, f, indent=4)

def load_sessions():
    if os.path.exists("sessions.json"):
        with open("sessions.json", "r") as f:
            return json.load(f)
    return {}

def save_sessions(data):
    with open("sessions.json", "w") as f:
        json.dump(data, f, indent=4)

# ─────────────────────────────────────────────
# INITIALIZATION
# ─────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

active_sessions = {}

# ─────────────────────────────────────────────
# ROLE MESSAGES CONFIG
# ─────────────────────────────────────────────

ROLE_MESSAGES = {
    "age": {
        "title": "🎂 Age",
        "description": "React to get your age role. You can only have one at a time.",
        "roles": {
            "1️⃣": "18-25",
            "2️⃣": "26-35",
            "3️⃣": "36+"
        }
    },
    "location": {
        "title": "🌍 Location",
        "description": "React to get your location role. You can only have one at a time.",
        "roles": {
            "🇪🇺": "Europe",
            "🌎": "North America",
            "🌱": "South America",
            "🏯": "Asia",
            "🌅": "Africa",
            "🌊": "Oceania"
        }
    },
    "status": {
        "title": "👤 Status",
        "description": "React to get your status role. You can only have one at a time.",
        "roles": {
            "🔴": "Sub",
            "🟡": "Switch",
            "🟣": "Domme"
        }
    }
}

def load_role_message_ids():
    if os.path.exists("role_message_ids.json"):
        with open("role_message_ids.json", "r") as f:
            return {int(k): v for k, v in json.load(f).items()}
    return {}

def save_role_message_ids(data):
    with open("role_message_ids.json", "w") as f:
        json.dump(data, f, indent=4)

role_message_ids = load_role_message_ids()

# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f"✅ Bot connected as {bot.user}")
    print(f"✅ {len(synced)} slash commands synced")
    for cmd in synced:
        print(f"  - /{cmd.name}")


@bot.event
async def on_raw_reaction_add(payload):
    if payload.member.bot:
        return

    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)

    # Rules
    if channel.name == RULES_CHANNEL:
        if str(payload.emoji) != "✅":
            return
        role = discord.utils.get(guild.roles, name="Member")
        if role and role not in payload.member.roles:
            await payload.member.add_roles(role)
        return

    # Reaction roles
    if payload.message_id not in role_message_ids:
        return

    category = role_message_ids[payload.message_id]
    data = ROLE_MESSAGES[category]
    emoji = str(payload.emoji)

    if emoji not in data["roles"]:
        return

    role_name = data["roles"][emoji]
    new_role = discord.utils.get(guild.roles, name=role_name)
    if not new_role:
        return

    old_roles = [discord.utils.get(guild.roles, name=r) for r in data["roles"].values()]
    old_roles = [r for r in old_roles if r and r in payload.member.roles and r != new_role]
    if old_roles:
        await payload.member.remove_roles(*old_roles)

    await payload.member.add_roles(new_role)


@bot.event
async def on_raw_reaction_remove(payload):
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return

    if payload.message_id not in role_message_ids:
        return

    category = role_message_ids[payload.message_id]
    data = ROLE_MESSAGES[category]
    emoji = str(payload.emoji)

    if emoji not in data["roles"]:
        return

    role_name = data["roles"][emoji]
    role = discord.utils.get(guild.roles, name=role_name)
    if role and role in member.roles:
        await member.remove_roles(role)

# ─────────────────────────────────────────────
# VIEWS
# ─────────────────────────────────────────────

class SessionView(discord.ui.View):
    def __init__(self, requester, domme):
        super().__init__(timeout=300)
        self.requester = requester
        self.domme = domme

    @discord.ui.button(label="Accept ✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.domme:
            await interaction.response.send_message("Only the requested domme can accept this session!", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.requester: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            self.domme: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_threads=True)
        }
        channel = await guild.create_text_channel(
            f"session-{self.requester.display_name}-x-{self.domme.display_name}",
            overwrites=overwrites
        )

        active_sessions[channel.id] = {
            "requester": self.requester,
            "domme": self.domme
        }

        await interaction.response.send_message(f"✅ Session accepted! Head over to {channel.mention}!")
        await channel.send(
            f"🔒 **Private Session — {self.requester.mention} x {self.domme.mention}**\n\n"
            f"Enjoy your session! When you're done, use `/session end` to archive this channel as a private thread."
        )

    @discord.ui.button(label="Decline ❌", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.domme:
            await interaction.response.send_message("Only the requested domme can decline this session!", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"❌ **{self.domme.display_name}** has declined the session request.")

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# ─────────────────────────────────────────────
# COMMANDS — RULES
# ─────────────────────────────────────────────

@bot.tree.command(name="post-rules", description="[Admin] Post the rules message in #rules")
@app_commands.checks.has_permissions(administrator=True)
async def post_rules(interaction: discord.Interaction):
    channel = discord.utils.get(interaction.guild.text_channels, name=RULES_CHANNEL)
    if not channel:
        await interaction.response.send_message(f"❌ Channel `#{RULES_CHANNEL}` not found!", ephemeral=True)
        return

    embed = discord.Embed(
        title="📋 Server Rules",
        description=(
            "*By joining this server, you agree to follow the rules below.*\n\n"
            "─────────────────────\n\n"
            "**1. 🤝 Mutual Respect**\n"
            "Respect is mandatory towards all members, no exceptions. "
            "Any form of insult, harassment or toxic behavior will be sanctioned.\n\n"
            "**2. 🚫 Zero Tolerance for Hate Speech**\n"
            "Racist, homophobic, sexist or any other discriminatory remarks "
            "are strictly forbidden and will result in an immediate ban.\n\n"
            "**3. 📢 No Unauthorized Advertising**\n"
            "Any advertising without prior authorization from an administrator is forbidden "
            "and will result in an immediate ban.\n\n"
            "**4. 🔒 No Leaks**\n"
            "It is strictly forbidden to share leaked content from platforms "
            "such as OnlyFans or MYM. Offenders will be permanently banned.\n\n"
            "**5. 🔞 Adult Content**\n"
            "All content shared on this server must exclusively feature people "
            "who are 18 years of age or older. Violations will result in an immediate ban and may be reported.\n\n"
            "**6. 👑 Findom Activity**\n"
            "No unauthorized findom activity or promotion is allowed on this server. "
            "Only approved findommes are permitted to offer or advertise their services. "
            "If you wish to become a findomme on this server, please contact an administrator. "
            "Any unauthorized findom activity will result in an immediate ban.\n\n"
            "─────────────────────\n"
            "✅ *React with ✅ below to confirm that you have read and accepted these rules.*"
        ),
        color=0x5865f2
    )
    msg = await channel.send(embed=embed)
    await msg.add_reaction("✅")
    await interaction.response.send_message(f"✅ Rules posted in {channel.mention}!", ephemeral=True)

# ─────────────────────────────────────────────
# COMMANDS — ROLES
# ─────────────────────────────────────────────

@bot.tree.command(name="post-roles", description="[Admin] Post the role selection messages in #roles")
@app_commands.checks.has_permissions(administrator=True)
async def post_roles(interaction: discord.Interaction):
    channel = discord.utils.get(interaction.guild.text_channels, name=ROLES_CHANNEL)
    if not channel:
        await interaction.response.send_message(f"❌ Channel `#{ROLES_CHANNEL}` not found!", ephemeral=True)
        return

    await interaction.response.send_message(f"✅ Posting role messages in {channel.mention}!", ephemeral=True)

    for category, data in ROLE_MESSAGES.items():
        embed = discord.Embed(title=data["title"], color=0x9b59b6)
        description = data["description"] + "\n\n"
        for emoji, role_name in data["roles"].items():
            description += f"{emoji} — **{role_name}**\n"
        embed.description = description

        msg = await channel.send(embed=embed)
        role_message_ids[msg.id] = category
        save_role_message_ids(role_message_ids)

        for emoji in data["roles"].keys():
            await msg.add_reaction(emoji)

# ─────────────────────────────────────────────
# COMMANDS — PROFILES
# ─────────────────────────────────────────────

profile_group = app_commands.Group(name="profile", description="Manage domme profiles")

# Stocke les créations de profils en cours
profile_sessions = {}
    
# ─────────────────────────────────────────────
# COMMANDS — SESSIONS
# ─────────────────────────────────────────────

session_group = app_commands.Group(name="session", description="Manage sessions")

@session_group.command(name="request", description="Send a session request to a domme")
@app_commands.describe(domme="The domme you want to contact")
async def session_request(interaction: discord.Interaction, domme: discord.Member):
    if interaction.channel.name != SESSIONS_CHANNEL:
        await interaction.response.send_message(
            f"❌ Session requests can only be made in `#{SESSIONS_CHANNEL}`!",
            ephemeral=True
        )
        return
    if domme == interaction.user:
        await interaction.response.send_message("You can't send a session request to yourself!", ephemeral=True)
        return
    if domme.bot:
        await interaction.response.send_message("You can't send a session request to a bot!", ephemeral=True)
        return
    role = discord.utils.get(interaction.guild.roles, name="findommes")
    if role not in domme.roles:
        await interaction.response.send_message(
            f"❌ You can only send a session request to a **findomme**!",
            ephemeral=True
        )
        return

    view = SessionView(interaction.user, domme)
    await interaction.response.send_message(
        f"💌 **{interaction.user.mention} is requesting a session with {domme.mention}!**\n"
        f"{domme.mention}, do you accept this request?",
        view=view
    )


@session_group.command(name="end", description="End the session and archive the channel as a private thread")
async def session_end(interaction: discord.Interaction):
    if interaction.channel.id not in active_sessions:
        await interaction.response.send_message(
            "This command can only be used inside a session channel!",
            ephemeral=True
        )
        return

    session = active_sessions[interaction.channel.id]
    if interaction.user not in [session["requester"], session["domme"]]:
        await interaction.response.send_message("You are not part of this session!", ephemeral=True)
        return

    await interaction.response.send_message(
        "📁 **Session ended!** Archiving as a private thread in 5 seconds..."
    )
    await asyncio.sleep(5)

    thread = await interaction.channel.create_thread(
        name=f"archive-{session['requester'].display_name}-x-{session['domme'].display_name}",
        type=discord.ChannelType.private_thread
    )
    await thread.add_user(session["requester"])
    await thread.add_user(session["domme"])
    await thread.send(
        f"🔒 **Session Archive**\n"
        f"Participants: {session['requester'].mention} & {session['domme'].mention}\n"
        f"This thread is private and only visible to both of you."
    )

    del active_sessions[interaction.channel.id]
    await interaction.channel.delete()

bot.tree.add_command(session_group)

bot.run(TOKEN)
