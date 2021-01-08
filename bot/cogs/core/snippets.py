from re import compile
from discord import Embed
from discord.ext import commands
from requests import post
import redis

from bot.bot import Bot

sr = compile(r"\{\{\S+\}\}")
special = ["member_count", "user_count", "bot_count"]


class Snippets(commands.Cog):
    """Snippets"""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.redis = redis.Redis(host="redis")

    def getkey(self, key: str):
        v = self.redis.get(key)
        if not v: return v
        return v.decode("utf-8")

    def setkey(self, key: str, value: str):
        self.redis.set(key, value)

    def delkey(self, key: str):
        self.redis.delete(key)

    def fmt(self, key: str):
        return "{{" + key + "}}"

    def find_snippets(self, message) -> dict:
        snips = sr.findall(message.content)
        snips = [s[2:-2] for s in snips]

        valid = {}
        for s in snips:
            s = s.lower()

            # Handle special cases
            if s in special:
                if s == "member_count":
                    valid[self.fmt(s)] = str(message.guild.member_count)
                elif s == "user_count":
                    valid[self.fmt(s)] = str(len([m for m in message.guild.members if not m.bot]))
                elif s == "bot_count":
                    valid[self.fmt(s)] = str(len([m for m in message.guild.members if m.bot]))

                continue

            userkey = f"{message.author.id}:{s}"
            guildkey = f"{message.guild.id}:{s}"
            if data := self.getkey(userkey):
                valid[self.fmt(s)] = data
            elif data := self.getkey(guildkey):
                valid[self.fmt(s)] = data

        return valid

    async def get_hook(self, message):
        hooks = await message.channel.webhooks()
        if not hooks:
            hooks = [await message.channel.create_webhook(name="snippets")]

        return hooks[0]

    @commands.command(name="help")
    async def snippet_help(self, ctx: commands.Context):
        help_text = "**__Available commands:__**\n"
        help_text += "`snippet create <name> <text>` - create a user snippet\n`snippet gcreate <name> <text>` - create a guild snippet*\n"
        help_text += "`snippet delete <name>` - delete a user snippet\n`snippet gdelete <name>` - delete a guild snippet*\n"
        help_text += "`snippet list` - list user snippets\n`snippet glist` - list guild snippets\n`snippet invite` - invite the bot to your server\n"
        help_text += "*these commands require the manage messages role permission\n\n"
        help_text += "**All commands can be called with `snippet <command>` OR `sp <command>`**"
        await ctx.send(help_text)

    @commands.command(name="invite")
    async def snippet_invite(self, ctx: commands.Context):
        desc = f"[Click this link to invite Snippets to your own server](https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=536882176&scope=bot)"
        embed = Embed(colour=0x87ceeb, description=desc)
        await ctx.send(embed=embed)

    @commands.command(name="create")
    async def snippet_create(self, ctx: commands.Context, name: str, *, content: str):
        if name in special:
            return await ctx.send(f"This is a reserved snippet name and cannot be bound to user snippets.")
        key = f"{ctx.author.id}:{name.lower()}"
        if self.getkey(key):
            return await ctx.send(f"You already have a snippet with that name. To delete it you can use `snippet delete {name}`")
        self.setkey(key, content)
        await ctx.send(f"Successfully created the snippet `{name}`, use it by putting `{self.fmt(name)}` in your message.")

    @commands.command(name="delete")
    async def snippet_delete(self, ctx: commands.Context, name: str):
        key = f"{ctx.author.id}:{name.lower()}"
        if not self.getkey(key):
            return await ctx.send("That snippet doesn't exist.")
        self.delkey(key)
        await ctx.send(f"Successfully deleted the snippet `{name}`")

    @commands.command(name="gcreate")
    @commands.has_guild_permissions(manage_messages=True)
    async def snippet_gcreate(self, ctx: commands.Context, name: str, *, content: str):
        if name in special:
            return await ctx.send(f"This is a reserved snippet name and cannot be bound to user snippets.")
        key = f"{ctx.guild.id}:{name.lower()}"
        if self.getkey(key):
            return await ctx.send(f"This guild already has a snippet with that name. To delete it you can use `snippet gdelete {name}`")
        extra = ""
        if self.getkey(f"{ctx.author.id}:{name.lower()}"):
            extra = "\n(You already have a snippet with this name, which will take precedence over guild snippets.)"
        self.setkey(key, content)
        await ctx.send(f"Successfully created the snippet `{name}`, use it by putting `{self.fmt(name)}` in your message.{extra}")

    @commands.command(name="gdelete")
    @commands.has_guild_permissions(manage_messages=True)
    async def snippet_gdelete(self, ctx: commands.Context, name: str):
        key = f"{ctx.guild.id}:{name.lower()}"
        if not self.getkey(key):
            return await ctx.send("That snippet doesn't exist.")
        self.delkey(key)
        await ctx.send(f"Successfully deleted the snippet `{name}`")

    @commands.command(name="snippets", aliases=["snips", "list"])
    async def snippets_list(self, ctx: commands.Context):
        keys = self.redis.keys(f"{ctx.author.id}:*")
        keys = [key.decode("utf-8").split(":", 1)[1] for key in keys]
        keys.sort()
        content = "Your snippets: " + ", ".join(keys)
        if len(content) > 2000:
            content = content[:1997] + "..."
        await ctx.send(content)

    @commands.command(name="gsnippets", aliases=["gsnips", "glist"])
    async def snippets_glist(self, ctx: commands.Context):
        keys = self.redis.keys(f"{ctx.guild.id}:*")
        keys = [key.decode("utf-8").split(":", 1)[1] for key in keys]
        keys.sort()
        content = "This guild's snippets: " + ", ".join(keys)
        if len(content) > 2000:
            content = content[:1997] + "..."
        await ctx.send(content)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        msnips = self.find_snippets(message)
        if not msnips: return

        hook = await self.get_hook(message)

        content = message.content
        for k, v in msnips.items():
            content = content.replace(k, v)

        if len(content) > 2000:
            content = content[:1997] + "..."

        data = {
            "username":message.author.name,
            "avatar_url":str(message.author.avatar_url_as(format="png")),
            "content":content,
            "allowed_mentions":{
                "everyone":False,
                "roles":False,
                "users":False
            }
        }

        await message.delete()
        post(hook.url, json=data)


def setup(bot: Bot):
    bot.add_cog(Snippets(bot))
