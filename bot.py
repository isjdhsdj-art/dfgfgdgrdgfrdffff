import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Select, Modal, TextInput, Button
import json
import os
import logging
import asyncio
import io
from datetime import datetime, timezone
import chat_exporter
from typing import Optional
import config

token_bot = config.token_bot
log_channel_id = config.log_channel_id
rating_channel_id = config.rating_channel_id
ticket_category_id = getattr(config, 'ticket_category_id', None)

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

if not os.path.exists("data"):
    os.makedirs("data")

def series_gradient(text, start_rgb=(255, 255, 0), end_rgb=(0, 0, 255)):
    lines = text.splitlines()
    total_chars = sum(len(line) for line in lines)
    result = ""
    idx = 0
    for line in lines:
        for ch in line:
            t = idx / max(total_chars - 1, 1)
            r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
            g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
            b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
            result += f"\033[38;2;{r};{g};{b}m{ch}\033[0m"
            idx += 1
        result += "\n"
    return result

ascii_art = r"""
 __   __        _____ _             _ _        
 \ \ / /       / ____| |           | (_)       
  \ V / _ __  | (___ | |_ _   _  __| |_  ___   
   > < | '__|  \___ \| __| | | |/ _` | |/ _ \  
  / . \| |     ____) | |_| |_| | (_| | | (_) | 
 /_/ \_\_|    |_____/ \__|\__,_|\__,_|_|\___/  
"""

studio_text = "Xr Studio"
series_text = "Coded By Series"

try:
    terminal_width = os.get_terminal_size().columns
except OSError:
    terminal_width = 80

max_ascii_width = max(len(line) for line in ascii_art.splitlines())
left_pad_ascii = max(0, (terminal_width - max_ascii_width) // 2)
colored_ascii = series_gradient(ascii_art)
for line in colored_ascii.splitlines():
    print(' ' * left_pad_ascii + line)
print()

studio_len = len(studio_text)
left_pad_studio = max(0, (terminal_width - studio_len) // 2)
colored_studio = series_gradient(studio_text)
print(' ' * left_pad_studio + colored_studio)

series_len = len(series_text)
left_pad_series = max(0, (terminal_width - series_len) // 2)
colored_series = series_gradient(series_text)
print(' ' * left_pad_series + colored_series)

class SeriesBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.ticket_counter = 1
        self.sections = {}
        self.tickets = {}
        self.setup_messages = {}
        self.data_file = "data/data.json"
        self.sections_file = "data/sections.json"
        self.tickets_file = "data/tickets.json"
        self.setup_file = "data/setup.json"
        self.counter_lock = asyncio.Lock()
        self.load_data()

    def load_data(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.ticket_counter = data.get('last_ticket', 1)
            if os.path.exists(self.sections_file):
                with open(self.sections_file, 'r', encoding='utf-8') as f:
                    self.sections = json.load(f)
            if os.path.exists(self.tickets_file):
                with open(self.tickets_file, 'r', encoding='utf-8') as f:
                    self.tickets = json.load(f)
            if os.path.exists(self.setup_file):
                with open(self.setup_file, 'r', encoding='utf-8') as f:
                    self.setup_messages = json.load(f)
        except Exception as e:
            logger.error(f"Data load error: {e}")

    def save_data(self):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({'last_ticket': self.ticket_counter}, f, indent=4)
        except Exception as e:
            logger.error(f"Save data error: {e}")

    def save_sections(self):
        try:
            with open(self.sections_file, 'w', encoding='utf-8') as f:
                json.dump(self.sections, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Save sections error: {e}")

    def save_tickets(self):
        try:
            with open(self.tickets_file, 'w', encoding='utf-8') as f:
                json.dump(self.tickets, f, indent=4)
        except Exception as e:
            logger.error(f"Save tickets error: {e}")

    def save_setup(self):
        try:
            with open(self.setup_file, 'w', encoding='utf-8') as f:
                json.dump(self.setup_messages, f, indent=4)
        except Exception as e:
            logger.error(f"Save setup error: {e}")

    async def setup_hook(self):
        await self.add_cog(SeriesCommands(self))
        await self.tree.sync()
        logger.info("Slash commands synced")

bot = SeriesBot()

async def create_ticket_core(interaction: discord.Interaction, section_id: str):
    if not interaction.guild:
        return await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
    if not interaction.channel:
        return await interaction.response.send_message("❌ حدث خطأ في القناة.", ephemeral=True)
    section = bot.sections.get(section_id)
    if not section:
        return await interaction.response.send_message("❌ القسم مو موجود.", ephemeral=True)
    guild = interaction.guild
    user = interaction.user

    async with bot.counter_lock:
        open_tickets_count = 0
        for data in bot.tickets.values():
            if data.get('opener_id') == user.id:
                open_tickets_count += 1
        if open_tickets_count >= 3:
            return await interaction.response.send_message("❌ ما تقدر تفتح أكثر من 3 تذاكر في نفس الوقت.", ephemeral=True)
        for ch_id, data in bot.tickets.items():
            if data.get('opener_id') == user.id and data.get('section_id') == section_id:
                channel = guild.get_channel(int(ch_id))
                if channel:
                    return await interaction.response.send_message(f"❌ عندك تذكرة مفتوحة بالفعل: {channel.mention}", ephemeral=True)
        ticket_number = bot.ticket_counter
        bot.ticket_counter += 1
        bot.save_data()

    channel_name = f"ticket-{ticket_number}"
    category = None
    section_category_id = section.get('category_id')
    if section_category_id:
        category = guild.get_channel(int(section_category_id))
    if not category and ticket_category_id:
        category = guild.get_channel(ticket_category_id)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    role = guild.get_role(int(section['role_id']))
    if role:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    try:
        channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=category, reason=f"Ticket opened by {user}")
    except discord.Forbidden:
        return await interaction.response.send_message("❌ البوت ما عنده صلاحية ينشئ قنوات.", ephemeral=True)

    embed_data = section.get('embed', {})
    embed_title = embed_data.get('title', f"تذكرة #{ticket_number} - {section['title']}")
    embed_description = embed_data.get('description', f"مرحبا {user.mention},\n{section.get('welcome_message', 'الدعم راح يساعدك قريبا.')}")
    embed_color = embed_data.get('color')
    if embed_color:
        try:
            embed_color = int(embed_color)
        except:
            embed_color = discord.Color.blue().value
    else:
        embed_color = discord.Color.blue().value
    embed = discord.Embed(
        title=embed_title,
        description=embed_description,
        color=embed_color
    )
    image_url = embed_data.get('image_url')
    if image_url:
        embed.set_image(url=image_url)
    footer = embed_data.get('footer')
    if footer:
        embed.set_footer(text=footer)

    view = SeriesTicketButtons(ticket_number, section_id)
    msg = await channel.send(embed=embed, view=view)

    mention_text = f"{user.mention}"
    if role:
        mention_text += f" {role.mention}"
    await channel.send(mention_text)

    bot.tickets[str(channel.id)] = {
        'number': ticket_number,
        'section_id': section_id,
        'message_id': msg.id,
        'claimed_by': None,
        'opener_id': user.id
    }
    bot.save_tickets()
    await interaction.response.send_message(f"✅ تم فتح التذكرة: {channel.mention}", ephemeral=True)

class SeriesTicketButtons(View):
    def __init__(self, ticket_number: int, section_id: str):
        super().__init__(timeout=None)
        self.ticket_number = ticket_number
        self.section_id = section_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
            return False

        section = bot.sections.get(self.section_id)
        if not section:
            await interaction.response.send_message("❌ القسم مو موجود.", ephemeral=True)
            return False

        role_id = int(section['role_id'])
        user_roles = [r.id for r in interaction.user.roles]

        ticket = bot.tickets.get(str(interaction.channel.id))
        is_support = role_id in user_roles
        is_claimer = ticket and ticket.get("claimed_by") == interaction.user.id

        if not (is_support or is_claimer):
            await interaction.response.send_message("❌ ما عندك صلاحية تستخدم أزرار التذكرة.", ephemeral=True)
            return False

        return True

    @discord.ui.button(label="استلام", emoji="🙋‍♂️", style=discord.ButtonStyle.primary, custom_id="claim")
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        section = bot.sections.get(self.section_id)
        if not section:
            return await interaction.response.send_message("❌ القسم مو موجود.", ephemeral=True)

        role_id = int(section['role_id'])
        if role_id not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message("❌ ما عندك صلاحية تستلم التذكرة هذي.", ephemeral=True)

        channel_id = str(interaction.channel.id)
        async with bot.counter_lock:
            if channel_id not in bot.tickets:
                return await interaction.response.send_message("❌ التذكرة غير موجودة.", ephemeral=True)
            if bot.tickets[channel_id].get('claimed_by'):
                return await interaction.response.send_message("❌ التذكرة مستلمة من قبل.", ephemeral=True)
            bot.tickets[channel_id]['claimed_by'] = interaction.user.id
            bot.save_tickets()

        overwrites = dict(interaction.channel.overwrites)
        overwrites[interaction.user] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        if interaction.guild.default_role in overwrites:
            overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        if role_id in overwrites:
            overwrites[role_id] = discord.PermissionOverwrite(view_channel=False, send_messages=False)
        try:
            await interaction.channel.edit(overwrites=overwrites)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ ما عندي صلاحية تعديل القناة.", ephemeral=True)

        await interaction.channel.send(f"✅ {interaction.user.mention} استلم التذكرة.")
        await interaction.response.send_message("✅ تم الاستلام.", ephemeral=True)

    @discord.ui.button(label="اغلاق", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        modal = SeriesCloseModal(self.ticket_number, self.section_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="سجل", emoji="📄", style=discord.ButtonStyle.secondary, custom_id="transcript")
    async def transcript_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        try:
            transcript = await chat_exporter.export(interaction.channel)
            if transcript is None:
                logger.warning(f"Transcript export returned None for ticket {self.ticket_number}")
                return await interaction.followup.send("❌ فشل في انشاء السجل (قد تكون القناة فارغة).", ephemeral=True)
            file = discord.File(io.BytesIO(transcript.encode()), filename=f"transcript-{self.ticket_number}.html")
            await interaction.followup.send(file=file, ephemeral=True)
        except Exception as e:
            logger.error(f"Transcript error: {e}")
            await interaction.followup.send("❌ صار خطأ.", ephemeral=True)

    @discord.ui.button(label="اعادة تسمية", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="rename")
    async def rename_button(self, interaction: discord.Interaction, button: Button):
        modal = SeriesRenameModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="اضافة عضو", emoji="➕", style=discord.ButtonStyle.success, custom_id="add")
    async def add_button(self, interaction: discord.Interaction, button: Button):
        modal = SeriesAddModal()
        await interaction.response.send_modal(modal)

class SeriesRatingView(View):
    def __init__(self, ticket_number: int, section_name: str, opener_id: int, closer_name: str):
        super().__init__(timeout=None)
        self.ticket_number = ticket_number
        self.section_name = section_name
        self.opener_id = opener_id
        self.closer_name = closer_name
        self.rated = False

    @discord.ui.button(label="⭐", style=discord.ButtonStyle.secondary, custom_id="rate1")
    async def rate_1(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 1)

    @discord.ui.button(label="⭐⭐", style=discord.ButtonStyle.secondary, custom_id="rate2")
    async def rate_2(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 2)

    @discord.ui.button(label="⭐⭐⭐", style=discord.ButtonStyle.secondary, custom_id="rate3")
    async def rate_3(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 3)

    @discord.ui.button(label="⭐⭐⭐⭐", style=discord.ButtonStyle.secondary, custom_id="rate4")
    async def rate_4(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 4)

    @discord.ui.button(label="⭐⭐⭐⭐⭐", style=discord.ButtonStyle.secondary, custom_id="rate5")
    async def rate_5(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 5)

    async def handle_rating(self, interaction: discord.Interaction, stars: int):
        if self.rated:
            await interaction.response.send_message("❌ لقد قيمت التذكرة من قبل.", ephemeral=True)
            return
        self.rated = True
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass
        channel = bot.get_channel(rating_channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(rating_channel_id)
            except:
                pass
        if channel:
            embed = discord.Embed(
                title="⭐ تقييم جديد",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="العضو", value=interaction.user.mention, inline=True)
            embed.add_field(name="عدد النجوم", value="⭐" * stars, inline=True)
            embed.add_field(name="رقم التذكرة", value=f"#{self.ticket_number}", inline=True)
            embed.add_field(name="القسم", value=self.section_name, inline=True)
            embed.add_field(name="أغلق بواسطة", value=self.closer_name, inline=True)
            await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ شكرا لتقييمك! ({'⭐' * stars})", ephemeral=True)

class SeriesCloseModal(Modal, title="اغلاق التذكرة"):
    reason = TextInput(label="سبب الاغلاق", style=discord.TextStyle.paragraph, required=True)
    def __init__(self, ticket_number: int, section_id: str):
        super().__init__()
        self.ticket_number = ticket_number
        self.section_id = section_id
    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
        if not interaction.channel:
            return await interaction.response.send_message("❌ حدث خطأ.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        guild = interaction.guild
        channel_id = str(channel.id)
        ticket_info = bot.tickets.get(channel_id, {})
        opener_id = ticket_info.get('opener_id')
        claimed_by_id = ticket_info.get('claimed_by')
        closer = interaction.user
        await channel.send("⏳ راح نغلق التذكرة بعد 5 ثواني...")
        await asyncio.sleep(5)
        try:
            transcript = await chat_exporter.export(channel)
            transcript_file = None
            if transcript:
                filename = f"ticket-{self.ticket_number}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.html"
                transcript_file = discord.File(io.BytesIO(transcript.encode()), filename=filename)
            log_channel = None
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if not log_channel:
                    try:
                        log_channel = await guild.fetch_channel(log_channel_id)
                    except:
                        pass
            if log_channel:
                embed = discord.Embed(
                    title=f"📋 سجل اغلاق تذكرة #{self.ticket_number}",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="القسم", value=bot.sections.get(self.section_id, {}).get('title', 'غير معروف'), inline=True)
                embed.add_field(name="رقم التذكرة", value=str(self.ticket_number), inline=True)
                embed.add_field(name="فاتح التذكرة", value=f"<@{opener_id}>" if opener_id else "غير معروف", inline=True)
                embed.add_field(name="مستلم التذكرة", value=f"<@{claimed_by_id}>" if claimed_by_id else "ما استلمها احد", inline=True)
                embed.add_field(name="أغلق بواسطة", value=closer.mention, inline=True)
                embed.add_field(name="سبب الاغلاق", value=self.reason.value, inline=False)
                await log_channel.send(embed=embed, file=transcript_file)
            if opener_id:
                user = bot.get_user(opener_id)
                if not user:
                    try:
                        user = await bot.fetch_user(opener_id)
                    except:
                        user = None
                if user:
                    try:
                        embed_dm = discord.Embed(
                            title=f"تم اغلاق تذكرتك #{self.ticket_number}",
                            description=f"القسم: {bot.sections.get(self.section_id, {}).get('title', 'غير معروف')}\nأغلق بواسطة: {closer.mention}",
                            color=discord.Color.blue()
                        )
                        section = bot.sections.get(self.section_id, {})
                        embed_data = section.get('embed', {})
                        image_url = embed_data.get('image_url')
                        if image_url:
                            embed_dm.set_image(url=image_url)
                        view = SeriesRatingView(self.ticket_number, bot.sections.get(self.section_id, {}).get('title', 'غير معروف'), opener_id, closer.name)
                        await user.send(embed=embed_dm, file=transcript_file, view=view)
                    except discord.Forbidden:
                        logger.warning(f"Cannot DM user {opener_id}")
                    except Exception as e:
                        logger.error(f"DM error: {e}")
            bot.tickets.pop(channel_id, None)
            bot.save_tickets()
            await channel.delete(reason=f"Ticket #{self.ticket_number} closed by {closer}")
        except Exception as e:
            logger.error(f"Close error: {e}")
            await interaction.followup.send("❌ صار خطأ اثناء الاغلاق.", ephemeral=True)

class SeriesRenameModal(Modal, title="اعادة تسمية القناة"):
    new_name = TextInput(label="الاسم الجديد", placeholder="ادخل الاسم الجديد", required=True, max_length=100)
    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.channel:
            return await interaction.response.send_message("❌ حدث خطأ.", ephemeral=True)
        try:
            await interaction.channel.edit(name=self.new_name.value)
            await interaction.response.send_message(f"✅ تم تغيير اسم القناة الى `{self.new_name.value}`.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ ما عندي صلاحية.", ephemeral=True)
        except Exception as e:
            logger.error(f"Rename error: {e}")
            await interaction.response.send_message("❌ فشل في تغيير الاسم.", ephemeral=True)

class SeriesAddModal(Modal, title="اضافة عضو"):
    member_id = TextInput(label="رقم العضو (ID)", placeholder="ادخل رقم العضو", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.channel or not interaction.guild:
            return await interaction.response.send_message("❌ حدث خطأ.", ephemeral=True)
        try:
            member_id = int(self.member_id.value)
        except ValueError:
            return await interaction.response.send_message("❌ الرقم غير صالح.", ephemeral=True)
        member = interaction.guild.get_member(member_id)
        if not member:
            try:
                member = await interaction.guild.fetch_member(member_id)
            except discord.NotFound:
                return await interaction.response.send_message("❌ العضو مو موجود في السيرفر.", ephemeral=True)
            except Exception as e:
                logger.error(f"Fetch member error: {e}")
                return await interaction.response.send_message("❌ صار خطأ في جلب العضو.", ephemeral=True)
        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ ما عندي صلاحية.", ephemeral=True)
        await interaction.response.send_message(f"✅ تم اضافة {member.mention} للتذكرة.", ephemeral=True)

class SeriesSectionSelect(Select):
    def __init__(self, sections: dict):
        options = []
        for sec_id, sec_data in sections.items():
            emoji = sec_data.get('emoji')
            options.append(discord.SelectOption(
                label=sec_data['title'],
                description=sec_data['description'],
                emoji=emoji if emoji else None,
                value=sec_id
            ))
        super().__init__(placeholder="اختر القسم المناسب...", min_values=1, max_values=1, options=options, custom_id="ticket_select")
    async def callback(self, interaction: discord.Interaction):
        await create_ticket_core(interaction, self.values[0])

class SeriesSectionButton(Button):
    def __init__(self, section_id: str, label: str, emoji: Optional[str]):
        clean_id = section_id.replace(' ', '_')
        custom_id = f"section_btn_{clean_id}"
        if emoji:
            super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.primary, custom_id=custom_id)
        else:
            super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=custom_id)
        self.section_id = section_id
    async def callback(self, interaction: discord.Interaction):
        await create_ticket_core(interaction, self.section_id)

class SeriesSectionsView(View):
    def __init__(self, sections: dict):
        super().__init__(timeout=None)
        for sec_id, sec_data in sections.items():
            self.add_item(SeriesSectionButton(sec_id, sec_data['title'], sec_data.get('emoji')))

class SeriesSetupView(View):
    def __init__(self, sections: dict):
        super().__init__(timeout=None)
        self.add_item(SeriesSectionSelect(sections))

class SeriesCommands(commands.Cog):
    def __init__(self, bot: SeriesBot):
        self.bot = bot

    @app_commands.command(name="add_section", description="اضافة قسم جديد")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def add_section(
        self,
        interaction: discord.Interaction,
        section_id: str,
        title: str,
        description: str,
        role: discord.Role,
        emoji: Optional[str] = None,
        welcome_message: str = "الدعم راح يساعدك قريبا.",
        category: Optional[discord.CategoryChannel] = None
    ):
        if not interaction.guild:
            return await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
        if section_id in self.bot.sections:
            return await interaction.response.send_message("❌ المعرف هذا موجود من قبل. اختر واحد ثاني.", ephemeral=True)
        cleaned_id = section_id.strip().replace(' ', '_')
        if cleaned_id != section_id:
            section_id = cleaned_id
        self.bot.sections[section_id] = {
            'title': title,
            'description': description,
            'emoji': emoji,
            'role_id': str(role.id),
            'welcome_message': welcome_message,
            'category_id': str(category.id) if category else None,
            'embed': {}
        }
        self.bot.save_sections()
        await interaction.response.send_message(f"✅ تم اضافة القسم `{section_id}`.", ephemeral=True)

    @app_commands.command(name="setup", description="اعداد لوحة التذاكر")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.choices(style=[
        app_commands.Choice(name="قائمة", value="menu"),
        app_commands.Choice(name="ازرار", value="buttons")
    ])
    async def setup(self, interaction: discord.Interaction, style: str = "menu"):
        if not interaction.guild:
            return await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
        if not self.bot.sections:
            return await interaction.response.send_message("❌ مافي اقسام مضافة. استخدم /add_section اول.", ephemeral=True)
        embed = discord.Embed(
            title="🎫 نظام التذاكر",
            description="اختار القسم المناسب عشان تفتح تذكرة جديدة.",
            color=discord.Color.green()
        )
        if style == "menu":
            view = SeriesSetupView(self.bot.sections)
        else:
            view = SeriesSectionsView(self.bot.sections)
        await interaction.response.send_message("✅ جاري انشاء اللوحة...", ephemeral=True)
        msg = await interaction.channel.send(embed=embed, view=view)
        self.bot.setup_messages[str(msg.id)] = {
            'type': style,
            'sections': list(self.bot.sections.keys()),
            'channel_id': interaction.channel.id,
            'guild_id': interaction.guild.id
        }
        self.bot.save_setup()

    @app_commands.command(name="edit_section", description="تعديل قسم موجود")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_section(
        self,
        interaction: discord.Interaction,
        section_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        role: Optional[discord.Role] = None,
        welcome_message: Optional[str] = None,
        category: Optional[discord.CategoryChannel] = None,
        embed_title: Optional[str] = None,
        embed_description: Optional[str] = None,
        embed_color: Optional[str] = None,
        embed_footer: Optional[str] = None
    ):
        if not interaction.guild:
            return await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
        if section_id not in self.bot.sections:
            return await interaction.response.send_message("❌ القسم مو موجود.", ephemeral=True)
        section = self.bot.sections[section_id]
        if title is not None:
            section['title'] = title
        if description is not None:
            section['description'] = description
        if emoji is not None:
            section['emoji'] = emoji
        if role is not None:
            section['role_id'] = str(role.id)
        if welcome_message is not None:
            section['welcome_message'] = welcome_message
        if category is not None:
            section['category_id'] = str(category.id)

        if 'embed' not in section:
            section['embed'] = {}

        if embed_title is not None:
            section['embed']['title'] = embed_title
        if embed_description is not None:
            section['embed']['description'] = embed_description
        if embed_color is not None:
            section['embed']['color'] = embed_color
        if embed_footer is not None:
            section['embed']['footer'] = embed_footer

        self.bot.save_sections()
        await interaction.response.send_message(f"✅ تم تعديل القسم `{section_id}`.", ephemeral=True)

    @app_commands.command(name="set_image", description="تعيين صورة للتذكرة")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def set_image(
        self,
        interaction: discord.Interaction,
        section_id: str,
        image: discord.Attachment
    ):
        if not interaction.guild:
            return await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
        if section_id not in self.bot.sections:
            return await interaction.response.send_message("❌ القسم مو موجود.", ephemeral=True)
        if not image.content_type or not image.content_type.startswith('image/'):
            return await interaction.response.send_message("❌ المرفق ليس صورة.", ephemeral=True)
        section = self.bot.sections[section_id]
        if 'embed' not in section:
            section['embed'] = {}
        section['embed']['image_url'] = image.url
        self.bot.save_sections()
        await interaction.response.send_message(f"✅ تم تعيين الصورة للقسم `{section_id}`.", ephemeral=True)

    @app_commands.command(name="delete_section", description="حذف قسم")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_section(self, interaction: discord.Interaction, section_id: str):
        if not interaction.guild:
            return await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
        if section_id not in self.bot.sections:
            return await interaction.response.send_message("❌ القسم مو موجود.", ephemeral=True)
        del self.bot.sections[section_id]
        self.bot.save_sections()
        await interaction.response.send_message(f"✅ تم حذف القسم `{section_id}`.", ephemeral=True)

    @app_commands.command(name="list_sections", description="عرض كل الاقسام")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def list_sections(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ هذا الأمر فقط في السيرفر.", ephemeral=True)
        if not self.bot.sections:
            return await interaction.response.send_message("📭 مافي اقسام مضافة.", ephemeral=True)
        embed = discord.Embed(title="📋 قائمة الاقسام", color=discord.Color.blue())
        for sec_id, sec_data in self.bot.sections.items():
            emoji_display = sec_data.get('emoji') or ''
            value = f"**الوصف:** {sec_data['description']}\n**الايموجي:** {emoji_display}\n**الرتبة:** <@&{sec_data['role_id']}>\n**رسالة الترحيب:** {sec_data.get('welcome_message', 'غير محددة')}"
            if sec_data.get('category_id'):
                value += f"\n**الفئة:** <#{sec_data['category_id']}>"
            embed.add_field(name=f"{emoji_display} {sec_data['title']} (`{sec_id}`)", value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    for channel_id_str, data in list(bot.tickets.items()):
        channel = bot.get_channel(int(channel_id_str))
        if channel:
            view = SeriesTicketButtons(data['number'], data['section_id'])
            bot.add_view(view, message_id=data['message_id'])
            logger.info(f"Restored view for ticket {channel.name}")
        else:
            logger.warning(f"Channel {channel_id_str} not found, removing from records.")
            del bot.tickets[channel_id_str]
            bot.save_tickets()
    for msg_id_str, setup_data in list(bot.setup_messages.items()):
        guild = bot.get_guild(setup_data['guild_id'])
        if not guild:
            continue
        channel = guild.get_channel(setup_data['channel_id'])
        if not channel:
            continue
        try:
            msg = await channel.fetch_message(int(msg_id_str))
        except discord.NotFound:
            del bot.setup_messages[msg_id_str]
            bot.save_setup()
            continue
        except Exception as e:
            logger.error(f"Error fetching setup message: {e}")
            continue
        if setup_data['type'] == "menu":
            view = SeriesSetupView(bot.sections)
        else:
            sections_subset = {sid: bot.sections[sid] for sid in setup_data['sections'] if sid in bot.sections}
            if not sections_subset:
                continue
            view = SeriesSectionsView(sections_subset)
        bot.add_view(view, message_id=msg.id)
        logger.info(f"Restored setup view (ID: {msg_id_str})")
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if not log_channel:
            try:
                log_channel = await bot.fetch_channel(log_channel_id)
            except:
                pass
        if log_channel:
            logger.info(f"Log channel found: {log_channel.name}")
        else:
            logger.warning(f"Log channel {log_channel_id} not found.")
    if rating_channel_id:
        rating_channel = bot.get_channel(rating_channel_id)
        if not rating_channel:
            try:
                rating_channel = await bot.fetch_channel(rating_channel_id)
            except:
                pass
        if rating_channel:
            logger.info(f"Rating channel found: {rating_channel.name}")
        else:
            logger.warning(f"Rating channel {rating_channel_id} not found.")

if __name__ == "__main__":
    try:
        bot.run(token_bot)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")