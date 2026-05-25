import discord
from discord.ext import commands, tasks
from discord import app_commands
import config
import aiohttp
import json
import asyncio
from datetime import datetime, timedelta, timezone
import re
import random
import os

class GiveawaySystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_giveaways = {}
        self.giveaways_file = "giveaway.json"
        self.allowed_user_ids = [1234, 1234]
        self.allowed_role_ids = [1234, 1234]
        self.msk_tz = timezone(timedelta(hours=3))
        self.load_giveaways()

    def _to_aware_utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _to_msk(self, dt: datetime) -> datetime:
        return self._to_aware_utc(dt).astimezone(self.msk_tz)
        
    async def check_permission(self, interaction: discord.Interaction):
        member_roles = getattr(interaction.user, "roles", [])
        has_allowed_role = any(role.id in self.allowed_role_ids for role in member_roles)
        if interaction.user.id not in self.allowed_user_ids and not has_allowed_role:
            embed = discord.Embed(
                title="Доступ запрещён",
                description="У вас нет прав на использование команд розыгрышей.",
                color=config.COLORS["ERROR"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True
        
    def load_giveaways(self):
        if os.path.exists(self.giveaways_file):
            try:
                with open(self.giveaways_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for giveaway_id, giveaway_data in data.items():
                    giveaway_data['end_time'] = self._to_aware_utc(datetime.fromisoformat(giveaway_data['end_time']))
                    giveaway_data['created_at'] = self._to_aware_utc(datetime.fromisoformat(giveaway_data['created_at']))
                    
                    if 'thread_id' in giveaway_data:
                        giveaway_data['thread'] = None
                        
                    self.active_giveaways[giveaway_id] = giveaway_data
                    
                print(f"Загружено {len(self.active_giveaways)} розыгрышей из файла.")
                
            except Exception as e:
                print(f"Ошибка загрузки розыгрышей: {e}")
                
    def save_giveaways(self):
        try:
            save_data = {}
            for giveaway_id, giveaway_data in self.active_giveaways.items():
                save_data[giveaway_id] = giveaway_data.copy()
                
                save_data[giveaway_id]['end_time'] = giveaway_data['end_time'].isoformat()
                save_data[giveaway_id]['created_at'] = giveaway_data['created_at'].isoformat()
                
                if 'thread' in save_data[giveaway_id]:
                    del save_data[giveaway_id]['thread']
                    
            with open(self.giveaways_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Ошибка сохранения розыгрышей: {e}")
            
    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        current_time = self._now_utc()
        to_remove = []
        
        for giveaway_id, giveaway_data in list(self.active_giveaways.items()):
            if giveaway_data.get('status') == 'active' and current_time >= giveaway_data["end_time"]:
                await self.end_giveaway(giveaway_id, giveaway_data)
                to_remove.append(giveaway_id)
            elif giveaway_data.get('status') == 'active':
                await self.update_giveaway_embed(giveaway_id, giveaway_data)
        
        for giveaway_id in to_remove:
            if giveaway_id in self.active_giveaways:
                del self.active_giveaways[giveaway_id]
                
        self.save_giveaways()
    
    def parse_time_string(self, time_str):
        time_str = time_str.strip().lower()
        
        total_seconds = 0
        
        day_patterns = [
            r'(\d+)\s*d',
            r'(\d+)\s*day',
            r'(\d+)\s*days',
            r'(\d+)\s*д',
            r'(\d+)\s*дн',
            r'(\d+)\s*день',
            r'(\d+)\s*дня',
            r'(\d+)\s*дней'
        ]
        
        for pattern in day_patterns:
            match = re.search(pattern, time_str)
            if match:
                try:
                    days = int(match.group(1))
                    total_seconds += days * 86400
                    time_str = time_str.replace(match.group(0), '')
                    break
                except:
                    pass
        
        hour_patterns = [
            r'(\d+)\s*h',
            r'(\d+)\s*hour',
            r'(\d+)\s*hours',
            r'(\d+)\s*ч',
            r'(\d+)\s*час',
            r'(\d+)\s*часа',
            r'(\d+)\s*часов'
        ]
        
        for pattern in hour_patterns:
            match = re.search(pattern, time_str)
            if match:
                try:
                    hours = int(match.group(1))
                    total_seconds += hours * 3600
                    time_str = time_str.replace(match.group(0), '')
                    break
                except:
                    pass
        
        minute_patterns = [
            r'(\d+)\s*m',
            r'(\d+)\s*min',
            r'(\d+)\s*minute',
            r'(\d+)\s*minutes',
            r'(\d+)\s*м',
            r'(\d+)\s*мин',
            r'(\d+)\s*минута',
            r'(\d+)\s*минуты',
            r'(\d+)\s*минут'
        ]
        
        for pattern in minute_patterns:
            match = re.search(pattern, time_str)
            if match:
                try:
                    minutes = int(match.group(1))
                    total_seconds += minutes * 60
                    time_str = time_str.replace(match.group(0), '')
                    break
                except:
                    pass
        
        if total_seconds == 0:
            try:
                numbers = re.findall(r'\d+', time_str)
                if numbers:
                    minutes = int(numbers[0])
                    total_seconds = minutes * 60
            except:
                pass
        
        if total_seconds < 60:
            total_seconds = 60
            
        return total_seconds
    
    def format_time_left(self, end_time):
        now = self._now_utc()
        if now >= end_time:
            return "**Завершён**"
        
        delta = end_time - now
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        seconds = delta.seconds % 60
        
        if days > 0:
            result = f"**{days}**д"
            if hours > 0:
                result += f" **{hours}**ч"
            return result
        elif hours > 0:
            result = f"**{hours}**ч"
            if minutes > 0:
                result += f" **{minutes}**м"
            return result
        elif minutes > 0:
            return f"**{minutes}**м"
        else:
            return f"**{seconds}**с"
    
    def format_end_time(self, end_time):
        return self._to_msk(end_time).strftime("%d.%m.%Y %H:%M MSK")
    
    def create_giveaway_content(self, giveaway_data):
        end_time_formatted = self.format_end_time(giveaway_data['end_time'])
        time_left = self.format_time_left(giveaway_data['end_time'])
        status = giveaway_data.get('status', 'active')
        
        content_text = f"# РОЗЫГРЫШ\n\n"
        
        if status == 'active':
            content_text += f"## {giveaway_data['prize']}\n\n"
        elif status == 'ended':
            content_text += f"## {giveaway_data['prize']} (ЗАВЕРШЁН)\n\n"
        elif status == 'paused':
            content_text += f"## {giveaway_data['prize']} (ПРИОСТАНОВЛЕН)\n\n"
        
        winners_count = giveaway_data.get('winners_count', 1)
        if winners_count > 1:
            content_text += f"**Победителей:** {winners_count}\n\n"
        
        if giveaway_data.get('required_roles'):
            roles_text = "\n".join([f"<@&{role_id}>" for role_id in giveaway_data['required_roles']])
            content_text += f"**Требуемые роли:**\n{roles_text}\n\n"
        else:
            content_text += f"**Участие:** Открыто для всех\n\n"
        
        participants_count = len(giveaway_data['participants'])
        content_text += f"**Заканчивается:** {end_time_formatted}\n"
        
        if status == 'active':
            content_text += f"**Осталось:** {time_left}\n\n"
        else:
            content_text += f"**Статус:** {self.get_status_text(status)}\n\n"
        
        content_text += f"**Участников:** {participants_count}\n\n"
        
        if status == 'active':
            content_text += "Нажмите на кнопку ниже, чтобы участвовать!"
        elif status == 'paused':
            content_text += "Розыгрыш приостановлен."
        
        return content_text
    
    def get_status_text(self, status):
        status_texts = {
            'active': 'Активен',
            'ended': 'Завершён',
            'paused': 'Приостановлен'
        }
        return status_texts.get(status, status)
    
    async def send_giveaway_message(self, channel, giveaway_data, giveaway_id):
        try:
            content_text = self.create_giveaway_content(giveaway_data)
            
            component_data = {
                'type': 17,
                'accent_color': None,
                'spoiler': False,
                'components': [{
                    'type': 10,
                    'content': content_text
                }]
            }
            
            headers = {
                'Authorization': f'Bot {config.TOKEN}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'content': None,
                'components': [component_data],
                'flags': 32768
            }
            
            url = f'https://discord.com/api/v10/channels/{channel.id}/messages'
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        message_data = await response.json()
                        message_id = message_data['id']
                        message = await channel.fetch_message(message_id)
                        return message
                    else:
                        error_text = await response.text()
                        print(f"API Error when sending: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            print(f"Error sending message: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def update_giveaway_embed(self, giveaway_id, giveaway_data):
        try:
            if 'message_id' not in giveaway_data:
                return
            
            channel = self.bot.get_channel(giveaway_data['channel_id'])
            if not channel:
                return
            
            content_text = self.create_giveaway_content(giveaway_data)
            
            component_data = {
                'type': 17,
                'accent_color': None,
                'spoiler': False,
                'components': [{
                    'type': 10,
                    'content': content_text
                }]
            }
            
            headers = {
                'Authorization': f'Bot {config.TOKEN}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'content': None,
                'components': [component_data],
                'flags': 32768
            }
            
            url = f'https://discord.com/api/v10/channels/{channel.id}/messages/{giveaway_data["message_id"]}'
            
            async with aiohttp.ClientSession() as session:
                async with session.patch(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        return True
                    elif response.status == 404:
                        print(f"Giveaway message {giveaway_id} not found.")
                        return False
                    else:
                        error_text = await response.text()
                        print(f"API Error when updating: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            print(f"Error updating embed: {e}")
            return False
    
    async def restore_giveaways_on_startup(self):
        print("\nStarting restoration of active giveaways...")
        
        restored_count = 0
        failed_count = 0
        
        for giveaway_id, giveaway_data in list(self.active_giveaways.items()):
            try:
                status = giveaway_data.get('status', 'active')
                
                if status == 'active':
                    print(f"  Restoring giveaway: {giveaway_id}")
                    print(f"     Prize: {giveaway_data['prize']}")
                    print(f"     Ends: {giveaway_data['end_time']}")
                    
                    channel = self.bot.get_channel(giveaway_data['channel_id'])
                    if not channel:
                        print(f"     Channel {giveaway_data['channel_id']} not found, skipping.")
                        failed_count += 1
                        continue
                    
                    success = await self.update_giveaway_embed(giveaway_id, giveaway_data)
                    if not success:
                        print(f"     Failed to update embed.")
                        failed_count += 1
                        continue
                    
                    await self.restore_giveaway_button(giveaway_id, giveaway_data)
                    await self.restore_giveaway_thread(giveaway_id, giveaway_data)
                    
                    restored_count += 1
                    print(f"     Giveaway restored.")
                else:
                    print(f"  Skipping inactive giveaway: {giveaway_id} (status: {status})")
                    
            except Exception as e:
                print(f"     Error restoring giveaway {giveaway_id}: {e}")
                failed_count += 1
        
        print(f"\nRestoration Summary:")
        print(f"   Successfully restored: {restored_count}")
        print(f"   Failed to restore: {failed_count}")
        print(f"   Total in memory: {len(self.active_giveaways)}")
        
        if not self.check_giveaways.is_running():
            self.check_giveaways.start()
            print(f"   Giveaway check task started.")
    
    async def restore_giveaway_button(self, giveaway_id, giveaway_data):
        try:
            channel = self.bot.get_channel(giveaway_data['channel_id'])
            if not channel:
                return
            
            status = giveaway_data.get('status', 'active')
            view = discord.ui.View(timeout=None)
            
            async def participate_callback(interaction: discord.Interaction):
                await self.handle_participation(interaction, giveaway_id, giveaway_data)
            
            if status == 'active':
                button = discord.ui.Button(
                    label="Участвовать",
                    style=discord.ButtonStyle.green,
                    custom_id=f"giveaway_{giveaway_id}",
                    emoji="\U0001f389"
                )
                button.callback = participate_callback
                view.add_item(button)
            
            if 'button_message_id' in giveaway_data:
                try:
                    button_message = await channel.fetch_message(giveaway_data['button_message_id'])
                    await button_message.edit(view=view)
                    print(f"     Button updated (message: {giveaway_data['button_message_id']})")
                except Exception as e:
                    print(f"     Failed to update button: {e}, creating a new one.")
                    button_message = await channel.send(view=view)
                    giveaway_data['button_message_id'] = button_message.id
                    print(f"     New button created.")
            else:
                button_message = await channel.send(view=view)
                giveaway_data['button_message_id'] = button_message.id
                print(f"     Button created (new message).")
            
            self.save_giveaways()
            
        except Exception as e:
            print(f"     Error restoring button: {e}")
    
    async def restore_giveaway_thread(self, giveaway_id, giveaway_data):
        try:
            if 'thread_id' not in giveaway_data:
                print(f"     Thread was not created previously.")
                return
            
            channel = self.bot.get_channel(giveaway_data['channel_id'])
            if not channel:
                return
            
            status = giveaway_data.get('status', 'active')
            
            try:
                message = await channel.fetch_message(giveaway_data['message_id'])
                thread = discord.utils.get(message.threads, id=giveaway_data['thread_id'])
                
                if thread:
                    if status == 'active':
                        await thread.edit(archived=False, locked=False)
                    giveaway_data['thread'] = thread
                    print(f"     Thread restored (ID: {thread.id})")
                else:
                    print(f"     Thread not found, but was recorded previously.")
                    giveaway_data['thread'] = None
                    
            except Exception as e:
                print(f"     Error restoring thread: {e}")
                giveaway_data['thread'] = None
                
        except Exception as e:
            print(f"     Error working with thread: {e}")
    
    async def create_giveaway_interface(self, interaction, giveaway_data, giveaway_id, restore=False):
        try:
            status = giveaway_data.get('status', 'active')
            
            if not restore:
                message = await self.send_giveaway_message(interaction.channel, giveaway_data, giveaway_id)
            else:
                channel = self.bot.get_channel(giveaway_data['channel_id'])
                if not channel:
                    embed = discord.Embed(
                        title="Ошибка",
                        description="Канал розыгрыша не найден!",
                        color=config.COLORS["ERROR"]
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                await self.update_giveaway_embed(giveaway_id, giveaway_data)
                message = await channel.fetch_message(giveaway_data['message_id'])
            
            if not message:
                embed = discord.Embed(
                    title="Розыгрыш создан!" if not restore else "Розыгрыш восстановлен!",
                    description=f"Розыгрыш **{giveaway_data['prize']}** {'создан' if not restore else 'восстановлен'}!",
                    color=config.COLORS["SUCCESS"]
                )
                message = await interaction.channel.send(embed=embed)
            
            if not restore:
                giveaway_data['message_id'] = message.id
            else:
                giveaway_data['message_id'] = message.id
            
            view = discord.ui.View(timeout=None)
            
            async def participate_callback(interaction: discord.Interaction):
                await self.handle_participation(interaction, giveaway_id, giveaway_data)
            
            if status == 'active':
                button = discord.ui.Button(
                    label="Участвовать",
                    style=discord.ButtonStyle.green,
                    custom_id=f"giveaway_{giveaway_id}",
                    emoji="\U0001f389"
                )
                button.callback = participate_callback
                view.add_item(button)
            
            if 'button_message_id' in giveaway_data:
                try:
                    channel = self.bot.get_channel(giveaway_data['channel_id'])
                    button_message = await channel.fetch_message(giveaway_data['button_message_id'])
                    await button_message.edit(view=view)
                except:
                    button_message = await interaction.channel.send(view=view)
                    giveaway_data['button_message_id'] = button_message.id
            else:
                button_message = await interaction.channel.send(view=view)
                giveaway_data['button_message_id'] = button_message.id
            
            if 'thread_id' in giveaway_data:
                try:
                    channel = self.bot.get_channel(giveaway_data['channel_id'])
                    message = await channel.fetch_message(giveaway_data['message_id'])
                    thread = discord.utils.get(message.threads, id=giveaway_data['thread_id'])
                    
                    if thread:
                        if status == 'active':
                            await thread.edit(archived=False, locked=False)
                        giveaway_data['thread'] = thread
                    else:
                        thread = await self.create_giveaway_thread(message, giveaway_data)
                        giveaway_data['thread'] = thread
                        giveaway_data['thread_id'] = thread.id
                except:
                    thread = await self.create_giveaway_thread(message, giveaway_data)
                    giveaway_data['thread'] = thread
                    giveaway_data['thread_id'] = thread.id
            else:
                thread = await self.create_giveaway_thread(message, giveaway_data)
                giveaway_data['thread'] = thread
                giveaway_data['thread_id'] = thread.id
            
            if not restore:
                success_embed = discord.Embed(
                    title="Розыгрыш создан!",
                    description=f"Розыгрыш **{giveaway_data['prize']}** успешно создан!",
                    color=config.COLORS["SUCCESS"]
                )
                success_embed.add_field(name="Победителей", value=str(giveaway_data.get('winners_count', 1)), inline=True)
                success_embed.add_field(name="Заканчивается", value=discord.utils.format_dt(giveaway_data['end_time'], 'F'), inline=True)
                success_embed.add_field(name="Сообщение", value=f"[Перейти к розыгрышу]({message.jump_url})", inline=False)
                success_embed.add_field(name="Ветка", value=f"Создана ветка для отслеживания участников.", inline=False)
                
                await interaction.followup.send(embed=success_embed, ephemeral=True)
            
            self.save_giveaways()
            
        except Exception as e:
            print(f"Error creating interface: {e}")
            import traceback
            traceback.print_exc()
            
            embed = discord.Embed(
                title="Предупреждение",
                description=f"Не удалось создать интерфейс розыгрыша: {str(e)}",
                color=config.COLORS["WARNING"]
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def create_giveaway_thread(self, message, giveaway_data):
        thread_name = f"Розыгрыш: {giveaway_data['prize'][:50]}"
        
        try:
            thread = await message.create_thread(
                name=thread_name,
                reason="Ветка для отслеживания участников розыгрыша.",
                auto_archive_duration=1440
            )
        except:
            thread = None
        
        if thread:
            winners_count = giveaway_data.get('winners_count', 1)
            status = giveaway_data.get('status', 'active')
            
            thread_embed = discord.Embed(
                title="Участники розыгрыша",
                description=(
                    f"**Приз:** {giveaway_data['prize']}\n"
                    f"**Победителей:** {winners_count}\n"
                    f"**Заканчивается:** {discord.utils.format_dt(giveaway_data['end_time'], 'F')}\n"
                    f"**Статус:** {self.get_status_text(status)}\n\n"
                    f"Здесь будут отображаться участники розыгрыша."
                ),
                color=config.COLORS["INFO"]
            )
            thread_embed.set_footer(text=f"ID: {list(self.active_giveaways.keys())[list(self.active_giveaways.values()).index(giveaway_data)]}")
            await thread.send(embed=thread_embed)
        
        return thread
    
    @tasks.loop(seconds=60)
    async def update_giveaway_embeds(self):
        if not self.active_giveaways:
            return
        
        for giveaway_id, giveaway_data in list(self.active_giveaways.items()):
            if giveaway_data.get('status') == 'active':
                if 'thread_id' in giveaway_data and not giveaway_data.get('thread'):
                    try:
                        channel = self.bot.get_channel(giveaway_data['channel_id'])
                        if channel:
                            message = await channel.fetch_message(giveaway_data['message_id'])
                            giveaway_data['thread'] = discord.utils.get(message.threads, id=giveaway_data['thread_id'])
                    except:
                        pass
                
                await self.update_giveaway_embed(giveaway_id, giveaway_data)
    
    async def handle_participation(self, interaction: discord.Interaction, giveaway_id: str, giveaway_data: dict):
        if giveaway_data.get('status') != 'active':
            embed = discord.Embed(
                title="Розыгрыш неактивен",
                description="Этот розыгрыш в данный момент неактивен!",
                color=config.COLORS["ERROR"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if self._now_utc() >= giveaway_data['end_time']:
            embed = discord.Embed(
                title="Розыгрыш завершён",
                description="Этот розыгрыш уже закончился!",
                color=config.COLORS["ERROR"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if giveaway_data.get('required_roles'):
            member_roles = [role.id for role in interaction.user.roles]
            has_required_role = any(role_id in member_roles for role_id in giveaway_data['required_roles'])
            
            if not has_required_role:
                role_mentions = []
                for role_id in giveaway_data['required_roles']:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        role_mentions.append(role.mention)
                
                embed = discord.Embed(
                    title="Доступ запрещён",
                    description=f"Требуемые роли для участия:\n{' '.join(role_mentions)}",
                    color=config.COLORS["ERROR"]
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        
        if interaction.user.id in giveaway_data['participants']:
            embed = discord.Embed(
                title="Уже участвуете",
                description="Вы уже зарегистрированы в этом розыгрыше!",
                color=config.COLORS["INFO"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        giveaway_data['participants'].append(interaction.user.id)
        await self.update_giveaway_embed(giveaway_id, giveaway_data)
        
        participants_count = len(giveaway_data['participants'])
        winners_count = giveaway_data.get('winners_count', 1)
        
        embed = discord.Embed(
            title="Вы участвуете!",
            description=(
                f"Вы успешно зарегистрировались в розыгрыше **{giveaway_data['prize']}**!\n\n"
                f"**Шанс на победу:** {winners_count}/{participants_count}\n"
                f"**Всего участников:** {participants_count}\n"
                f"**Победителей:** {winners_count}"
            ),
            color=config.COLORS["SUCCESS"]
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        try:
            thread = giveaway_data.get('thread')
            if not thread and 'thread_id' in giveaway_data:
                try:
                    channel = self.bot.get_channel(giveaway_data['channel_id'])
                    if channel:
                        message = await channel.fetch_message(giveaway_data['message_id'])
                        thread = discord.utils.get(message.threads, id=giveaway_data['thread_id'])
                        giveaway_data['thread'] = thread
                except:
                    pass
            
            if thread:
                embed = discord.Embed(
                    description=f"{interaction.user.mention} присоединился к розыгрышу!",
                    color=config.COLORS["SUCCESS"]
                )
                embed.add_field(name="Шанс", value=f"{winners_count}/{participants_count}", inline=True)
                embed.add_field(name="Всего", value=str(participants_count), inline=True)
                embed.set_footer(text=f"Участник #{participants_count}")
                await thread.send(embed=embed)
        except Exception as e:
            print(f"Error sending to thread: {e}")
        
        self.save_giveaways()
    
    async def end_giveaway(self, giveaway_id: str, giveaway_data: dict):
        channel = self.bot.get_channel(giveaway_data['channel_id'])
        
        if not channel:
            return
        
        try:
            button_message = await channel.fetch_message(giveaway_data['button_message_id'])
            await button_message.edit(view=None)
        except:
            pass
        
        participants_count = len(giveaway_data['participants'])
        winners_count = giveaway_data.get('winners_count', 1)
        
        final_content = f"# РОЗЫГРЫШ ЗАВЕРШЁН\n\n"
        final_content += f"## {giveaway_data['prize']}\n\n"
        
        if winners_count > 1:
            final_content += f"**Победителей:** {winners_count}\n\n"
        
        if giveaway_data.get('required_roles'):
            roles_text = "\n".join([f"<@&{role_id}>" for role_id in giveaway_data['required_roles']])
            final_content += f"**Требуемые роли:**\n{roles_text}\n\n"
        else:
            final_content += f"**Участие:** Открыто для всех\n\n"
        
        final_content += f"**Заканчивался:** {self.format_end_time(giveaway_data['end_time'])}\n\n"
        final_content += f"**Участников:** {participants_count}\n\n"
        
        if not giveaway_data['participants']:
            final_content += "**К сожалению, не было участников.**"
            await self.send_final_embed(channel, giveaway_data, final_content, [])
        else:
            if winners_count >= participants_count:
                winners = giveaway_data['participants'].copy()
            else:
                winners = random.sample(giveaway_data['participants'], winners_count)
            
            winner_members = []
            winner_mentions = []
            
            for winner_id in winners:
                winner = channel.guild.get_member(winner_id)
                if winner:
                    winner_members.append(winner)
                    winner_mentions.append(winner.mention)
                else:
                    winner_mentions.append(f"*Пользователь покинул сервер*")
            
            if winner_mentions:
                final_content += f"**ПОБЕДИТЕЛИ:**\n"
                if len(winner_mentions) == 1:
                    final_content += f"{winner_mentions[0]}"
                else:
                    for i, mention in enumerate(winner_mentions, 1):
                        final_content += f"{i}. {mention}\n"
            
            await self.send_final_embed(channel, giveaway_data, final_content, winner_members)
            
            for winner in winner_members:
                try:
                    winner_embed = discord.Embed(
                        title="ПОЗДРАВЛЯЕМ!",
                        description=(
                            f"Вы выиграли **{giveaway_data['prize']}** в розыгрыше на сервере **{channel.guild.name}**!\n\n"
                            f"**Шанс на победу:** {winners_count}/{participants_count}\n"
                            f"**Всего участников:** {participants_count}\n"
                            f"**Победителей:** {winners_count}"
                        ),
                        color=config.COLORS["SUCCESS"]
                    )
                    winner_embed.set_footer(text="Свяжитесь с организатором для получения приза.")
                    await winner.send(embed=winner_embed)
                except:
                    pass
        
        try:
            thread = giveaway_data.get('thread')
            if not thread and 'thread_id' in giveaway_data:
                try:
                    message = await channel.fetch_message(giveaway_data['message_id'])
                    thread = discord.utils.get(message.threads, id=giveaway_data['thread_id'])
                except:
                    pass
                    
            if thread:
                await thread.edit(archived=True, locked=True)
        except:
            pass
        
        giveaway_data['status'] = 'ended'
        self.save_giveaways()
    
    async def send_final_embed(self, channel, giveaway_data, content, winners):
        try:
            component_data = {
                'type': 17,
                'accent_color': None,
                'spoiler': False,
                'components': [{
                    'type': 10,
                    'content': content
                }]
            }
            
            headers = {
                'Authorization': f'Bot {config.TOKEN}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'content': None,
                'components': [component_data],
                'flags': 32768
            }
            
            url = f'https://discord.com/api/v10/channels/{channel.id}/messages/{giveaway_data["message_id"]}'
            
            async with aiohttp.ClientSession() as session:
                await session.patch(url, headers=headers, json=payload)
                
        except Exception as e:
            print(f"Error sending final embed: {e}")
            embed_color = config.COLORS["SUCCESS"] if winners else config.COLORS["ERROR"]
            embed = discord.Embed(
                title="Розыгрыш завершён!",
                description=content,
                color=embed_color
            )
            await channel.send(embed=embed)
    
    @app_commands.command(name="gstart", description="Создать новый розыгрыш")
    @app_commands.describe(
        приз="Приз для розыгрыша",
        победители="Количество победителей (по умолчанию: 1)",
        роли="ID ролей для участия, разделённые запятыми (или - если не требуются)",
        время="Время до окончания (например: 4d 1h 1m или 5ч 30м или 1д)"
    )
    async def giveaway_command(self, interaction: discord.Interaction, приз: str, победители: int = 1, роли: str = "-", время: str = "24h"):
        if not await self.check_permission(interaction):
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            if победители < 1:
                embed = discord.Embed(
                    title="Ошибка",
                    description="Количество победителей должно быть не меньше 1!",
                    color=config.COLORS["ERROR"]
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            if победители > 50:
                embed = discord.Embed(
                    title="Ошибка",
                    description="Слишком много победителей! Максимум 50.",
                    color=config.COLORS["ERROR"]
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            total_seconds = self.parse_time_string(время)
            if total_seconds == 0:
                embed = discord.Embed(
                    title="Ошибка",
                    description="Неверный формат времени!\n\n**Допустимые форматы:**\n* `4д 1ч 30м`\n* `5h 30m`\n* `3d`\n* `2h`\n* `45m`\n* `1д`\n* `2ч`\n* `30м`",
                    color=config.COLORS["ERROR"]
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            end_time = self._now_utc() + timedelta(seconds=total_seconds)
            
            required_roles = []
            if роли != "-":
                role_ids = [role_id.strip() for role_id in роли.split(',')]
                for role_id in role_ids:
                    if role_id.isdigit():
                        required_roles.append(int(role_id))
            
            giveaway_id = f"giveaway_{interaction.id}_{int(self._now_utc().timestamp())}"
            
            giveaway_data = {
                'prize': приз,
                'winners_count': победители,
                'end_time': end_time,
                'required_roles': required_roles,
                'participants': [],
                'channel_id': interaction.channel.id,
                'creator_id': interaction.user.id,
                'guild_id': interaction.guild_id,
                'created_at': self._now_utc(),
                'status': 'active'
            }
            
            self.active_giveaways[giveaway_id] = giveaway_data
            await self.create_giveaway_interface(interaction, giveaway_data, giveaway_id)
            
            if not self.check_giveaways.is_running():
                self.check_giveaways.start()
            
        except Exception as e:
            print(f"Error creating giveaway: {e}")
            import traceback
            traceback.print_exc()
            
            embed = discord.Embed(
                title="Ошибка",
                description=f"Не удалось создать розыгрыш: {str(e)}",
                color=config.COLORS["ERROR"]
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="giveaway-list", description="Список активных розыгрышей")
    async def giveaway_list(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            return
            
        guild_giveaways = {}
        for g_id, g_data in self.active_giveaways.items():
            if g_data['guild_id'] == interaction.guild_id:
                guild_giveaways[g_id] = g_data
        
        if not guild_giveaways:
            embed = discord.Embed(
                title="Розыгрыши",
                description="Нет сохранённых розыгрышей.",
                color=config.COLORS["INFO"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Все розыгрыши",
            description=f"Всего розыгрышей: {len(guild_giveaways)}",
            color=config.COLORS["INFO"]
        )
        
        for giveaway_id, giveaway_data in guild_giveaways.items():
            time_left = self.format_time_left(giveaway_data['end_time'])
            participants_count = len(giveaway_data['participants'])
            winners_count = giveaway_data.get('winners_count', 1)
            status = giveaway_data.get('status', 'active')
            
            embed.add_field(
                name=f"{giveaway_data['prize'][:50]} [{status.upper()}]",
                value=(
                    f"**ID:** `{giveaway_id[:20]}...`\n"
                    f"**Победителей:** {winners_count}\n"
                    f"**Участников:** {participants_count}\n"
                    f"**Осталось:** {time_left}\n"
                    f"**Статус:** {self.get_status_text(status)}"
                ),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="giveaway-end", description="Завершить розыгрыш досрочно")
    @app_commands.describe(
        giveaway_id="ID розыгрыша (можно найти в /giveaway-list)"
    )
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: str):
        if not await self.check_permission(interaction):
            return
            
        if giveaway_id not in self.active_giveaways:
            embed = discord.Embed(
                title="Ошибка",
                description="Розыгрыш с таким ID не найден.",
                color=config.COLORS["ERROR"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        giveaway_data = self.active_giveaways[giveaway_id]
        
        member_roles = getattr(interaction.user, "roles", [])
        has_allowed_role = any(role.id in self.allowed_role_ids for role in member_roles)
        if (
            interaction.user.id != giveaway_data['creator_id']
            and interaction.user.id not in self.allowed_user_ids
            and not has_allowed_role
        ):
            embed = discord.Embed(
                title="Доступ запрещён",
                description="Вы не являетесь создателем этого розыгрыша.",
                color=config.COLORS["ERROR"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await self.end_giveaway(giveaway_id, giveaway_data)
        giveaway_data['status'] = 'ended'
        
        embed = discord.Embed(
            title="Розыгрыш завершён",
            description=f"Розыгрыш **{giveaway_data['prize']}** завершён досрочно.",
            color=config.COLORS["SUCCESS"]
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        self.save_giveaways()
    
    @app_commands.command(name="giveaway-restore", description="Восстановить розыгрыш")
    @app_commands.describe(
        giveaway_id="ID розыгрыша (можно найти в /giveaway-list)",
        новое_время="Новое время до окончания (например: 4d 1h 1m или - чтобы оставить текущее)"
    )
    async def giveaway_restore(self, interaction: discord.Interaction, giveaway_id: str, новое_время: str = "-"):
        if not await self.check_permission(interaction):
            return
            
        await interaction.response.defer(ephemeral=True)
        
        if giveaway_id not in self.active_giveaways:
            embed = discord.Embed(
                title="Ошибка",
                description="Розыгрыш с таким ID не найден!",
                color=config.COLORS["ERROR"]
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        giveaway_data = self.active_giveaways[giveaway_id]
        
        if новое_время != "-":
            total_seconds = self.parse_time_string(новое_время)
            if total_seconds == 0:
                embed = discord.Embed(
                    title="Ошибка",
                    description="Неверный формат времени!",
                    color=config.COLORS["ERROR"]
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            giveaway_data['end_time'] = self._now_utc() + timedelta(seconds=total_seconds)
        
        giveaway_data['status'] = 'active'
        
        print(f"\nВосстановление розыгрыша по команде:")
        print(f"   Приз: {giveaway_data['prize']}")
        print(f"   ID: {giveaway_id}")
        print(f"   Новое время окончания: {giveaway_data['end_time']}")
        
        success = await self.update_giveaway_embed(giveaway_id, giveaway_data)
        if not success:
            print(f"   Не удалось обновить embed.")
            embed = discord.Embed(
                title="Ошибка",
                description="Не удалось обновить сообщение розыгрыша!",
                color=config.COLORS["ERROR"]
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        await self.restore_giveaway_button(giveaway_id, giveaway_data)
        await self.restore_giveaway_thread(giveaway_id, giveaway_data)
        
        success_embed = discord.Embed(
            title="Розыгрыш восстановлен!",
            description=f"Розыгрыш **{giveaway_data['prize']}** успешно восстановлен!",
            color=config.COLORS["SUCCESS"]
        )
        success_embed.add_field(name="Победителей", value=str(giveaway_data.get('winners_count', 1)), inline=True)
        success_embed.add_field(name="Новое время окончания", value=discord.utils.format_dt(giveaway_data['end_time'], 'F'), inline=True)
        success_embed.add_field(name="Участников", value=str(len(giveaway_data['participants'])), inline=True)
        success_embed.add_field(name="Статус", value="Активен", inline=True)
        
        if новое_время != "-":
            success_embed.add_field(name="Время обновлено", value=f"Установлено новое время: {новое_время}", inline=False)
        
        await interaction.followup.send(embed=success_embed, ephemeral=True)
        
        if not self.check_giveaways.is_running():
            self.check_giveaways.start()
            print(f"   Задача проверки розыгрышей запущена.")
    
    @app_commands.command(name="giveaway-info", description="Информация о розыгрыше")
    @app_commands.describe(
        giveaway_id="ID розыгрыша (можно найти в /giveaway-list)"
    )
    async def giveaway_info(self, interaction: discord.Interaction, giveaway_id: str):
        if not await self.check_permission(interaction):
            return
            
        if giveaway_id not in self.active_giveaways:
            embed = discord.Embed(
                title="Ошибка",
                description="Розыгрыш с таким ID не найден!",
                color=config.COLORS["ERROR"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        giveaway_data = self.active_giveaways[giveaway_id]
        
        embed = discord.Embed(
            title=f"Информация о розыгрыше",
            color=config.COLORS["INFO"]
        )
        
        status = giveaway_data.get('status', 'active')
        
        embed.add_field(name="Приз", value=giveaway_data['prize'], inline=False)
        embed.add_field(name="Статус", value=f"{self.get_status_text(status)}", inline=True)
        embed.add_field(name="Победителей", value=str(giveaway_data.get('winners_count', 1)), inline=True)
        embed.add_field(name="Участников", value=str(len(giveaway_data['participants'])), inline=True)
        embed.add_field(name="Создан", value=discord.utils.format_dt(giveaway_data['created_at'], 'F'), inline=False)
        embed.add_field(name="Заканчивается", value=discord.utils.format_dt(giveaway_data['end_time'], 'F'), inline=True)
        embed.add_field(name="Осталось", value=self.format_time_left(giveaway_data['end_time']), inline=True)
        
        creator = interaction.guild.get_member(giveaway_data['creator_id'])
        creator_name = creator.mention if creator else f"Неизвестно ({giveaway_data['creator_id']})"
        embed.add_field(name="Создатель", value=creator_name, inline=True)
        
        embed.add_field(name="ID розыгрыша", value=f"`{giveaway_id}`", inline=False)
        
        if 'message_id' in giveaway_data:
            embed.add_field(
                name="Ссылки",
                value=(
                    f"[Сообщение](https://discord.com/channels/{giveaway_data['guild_id']}/{giveaway_data['channel_id']}/{giveaway_data['message_id']})\n"
                    f"Канал: <#{giveaway_data['channel_id']}>"
                ),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"\nБот готов, начинаю восстановление розыгрышей...")
        await asyncio.sleep(5)
        await self.restore_giveaways_on_startup()

async def setup(bot):
    cog = GiveawaySystem(bot)
    await bot.add_cog(cog)