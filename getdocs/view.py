from redbot.core import commands  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

from redbot.core.utils.chat_formatting import box

from .types import SearchResults


class DocsSelectOption(discord.SelectOption):
    def __init__(self, original_name: str, *args, **kwargs) -> None:
        self.original_name = original_name
        super().__init__(*args, **kwargs)


class DocsSelect(discord.ui.Select):
    def __init__(self, parent: discord.ui.View, results: SearchResults):
        self._parent = parent
        self.texts = {}
        for name, original_name, url, _ in results.results:
            if name not in self.texts.keys():
                self.texts[name] = url, original_name
        self._options = [
            DocsSelectOption(label=name, original_name=original_name)
            for name, (_, original_name) in self.texts.items()
        ]
        super().__init__(
            placeholder="Select an option.",
            options=self._options,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in [self._parent.ctx.author.id] + list(self._parent.ctx.bot.owner_ids):
            await interaction.response.send_message(
                "You are not allowed to use this interaction.", ephemeral=True
            )
            return
        option = discord.utils.get(self._options, label=self.values[0])
        await self._parent._callback(interaction, option)


class DocsView(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        query: str,
        source,
    ):
        super().__init__(timeout=60 * 5)
        self.ctx = ctx
        self.query = query
        self.source = source
        self._message: discord.Message = None
        self._current = None

    async def _callback(
        self, interaction: discord.Interaction, option: discord.SelectOption
    ):
        await interaction.response.defer()
        await self._update(option.original_name)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        await self._message.edit(view=self)

    async def _update(self, name: str):
        doc = None
        i = 0
        doc = await self.source.get_documentation(name)
        while doc is None and i < len(self.results.results):
            doc = await self.source.get_documentation(self.results.results[i][0])
            if doc is not None:
                break
            i += 1
        if doc is None:
            raise RuntimeError("No results found.")
        examples_button: discord.ui.Button = discord.utils.get(
            self.children, custom_id="show_ex"
        )
        if examples_button:
            examples_button.disabled = not bool(doc.examples)
        attributes_button: discord.ui.Button = discord.utils.get(
            self.children, custom_id="show_attr"
        )
        if attributes_button:
            attributes_button.disabled = not bool(doc.attributes)
        self._current = doc
        embed = doc.to_embed()
        content = None
        if self.source._docs_caching_task is not None and self.source._docs_caching_task.currently_running:
            content = "⚠️ The documentation cache is not yet fully built, building now."
        if self._message is None:
            self._message = await self.ctx.send(content=content, embed=embed, view=self)
        else:
            self._message = await self._message.edit(content=content, embed=embed)

    async def show_examples(self, interaction: discord.Interaction) -> None:
        if interaction.user.id not in [self.ctx.author.id] + list(self.ctx.bot.owner_ids):
            await interaction.response.send_message(
                "You are not allowed to use this interaction.", ephemeral=True
            )
            return
        if not self._current:
            return await interaction.response.send_message(
                "Current variable is somehow empty, so examples aren't loaded.",
                ephemeral=True,
            )
        if not self._current.examples:
            return await interaction.response.send_message(
                "There are no examples available for this option.",
                ephemeral=True,
            )
        await interaction.response.defer()
        if not self._current.name == self._message.embeds[0].title:  # back
            await self._update(self._current.name)
            return

        embeds = []
        for i, example in enumerate(self._current.examples, start=1):
            embed = discord.Embed(
                title=f"Example {i}:" if len(self._current.examples) > 1 else "Example:",
                description=box(example, lang="py"),
                color=discord.Color.green(),
            )
            embeds.append(embed)
        self._message = await self._message.edit(embeds=embeds)

    async def show_attributes(self, interaction: discord.Interaction) -> None:
        if interaction.user.id not in [self.ctx.author.id] + list(self.ctx.bot.owner_ids):
            await interaction.response.send_message(
                "You are not allowed to use this interaction.", ephemeral=True
            )
            return
        if not self._current:
            return await interaction.response.send_message(
                "Current variable is somehow empty, so attributes aren't loaded.",
                ephemeral=True,
            )
        if not self._current.attributes:
            return await interaction.response.send_message(
                "There are no attributes available for this option.",
                ephemeral=True,
            )
        await interaction.response.defer()
        if not self._current.name == self._message.embeds[0].title:  # back
            await self._update(self._current.name)
            return

        def format_attribute(name: str, url: str):
            return f"[{name}]({url})"
        def comprehend_attributes(attributes: typing.List[str]) -> str:
            formatted_attributes = [
                format_attribute(name, url) for name, url in attributes
            ]
            return "\n".join(
                f"> {attribute}" for attribute in formatted_attributes[:limit]
            )

        embeds = []
        for name, attributes in self._current.attributes.items():
            limit = 4096  # maximum embed description limit
            attrs = []
            for attribute in attributes:
                if not attrs:
                    attrs.append([])
                new_attrs = attrs[-1] + [attribute]
                new_text = comprehend_attributes(new_attrs)
                if len(new_text) > limit:
                    attrs.append([])
                attrs[-1].append(attribute)
            for _attrs in attrs:
                embed = discord.Embed(
                    title=name.title(),
                    description="\n".join(
                        format_attribute(name, url) for name, url in _attrs
                    )[:5000 - 1],
                    color=discord.Color.green(),
                )
                embeds.append(embed)
        self._message = await self._message.edit(embeds=embeds)

    async def close_page(self, interaction: discord.Interaction) -> None:
        if interaction.user.id not in [self.ctx.author.id] + list(self.ctx.bot.owner_ids):
            await interaction.response.send_message(
                "You are not allowed to use this interaction.", ephemeral=True
            )
            return
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            pass
        self.stop()
        try:
            await self._message.delete()
        except discord.HTTPException:
            pass

    async def start(self):
        results = await self.source.search(self.query, limit=25, exclude_std=True)
        self.results = results
        if not results or not results.results:
            raise RuntimeError("No results found.")
        select = DocsSelect(self, results)
        self.add_item(select)
        example_button = discord.ui.Button(
            label="Show Examples", custom_id="show_ex", style=discord.ButtonStyle.grey
        )
        example_button.callback = self.show_examples
        self.add_item(example_button)
        attributes_button = discord.ui.Button(
            label="Show Attributes",
            custom_id="show_attr",
            style=discord.ButtonStyle.grey,
        )
        attributes_button.callback = self.show_attributes
        self.add_item(attributes_button)
        close_button = discord.ui.Button(
            emoji="❌",
            custom_id="close_page",
            style=discord.ButtonStyle.grey,
        )
        close_button.callback = self.close_page
        self.add_item(close_button)
        await self._update(results.results[0][1])