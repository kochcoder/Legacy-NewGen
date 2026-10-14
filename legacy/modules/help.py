# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import difflib
import inspect
import logging
import re
import typing

from legacytl.extensions.html import CUSTOM_EMOJIS
from legacytl.tl.types import Message

from .. import loader, utils
from ..inline.screens import Screen, escape, plural
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

PAGE_SIZE = 15
OPEN_LIMIT = 8
SUMMARY = 48


def _emojify(text: str) -> str:
    """Classic `<emoji document_id=N>` tags to the rich `<tg-emoji>` form"""
    return text.replace("<emoji document_id=", "<tg-emoji emoji-id=").replace(
        "</emoji>", "</tg-emoji>"
    )


@loader.tds
class Help(loader.Module):
    strings = {
        "name": "Help",
        "modules_count": "{} module|{} modules",
        "prefix_badge": "prefix {}",
        "hidden_badge": "{} hidden",
        "restricted": "Some modules are not shown because you lack rights",
        "builtin_section": "Built-in",
        "external_section": "Modules",
        "nothing": "Nothing to show",
        "no_commands_badge": "no commands",
        "hidden_title": "Hidden modules",
        "hidden_hint": "Show a module back with {}helphide <name>",
        "hidden_none": "No hidden modules",
        "unhide_short": "unhide",
        "unhide_all": "Unhide all",
        "hidden_done": "🙈 Module hidden",
        "shown_done": "👁 Module shown",
        "shown_all_done": "👁 All modules shown",
        "commands": "Commands",
        "no_commands": "No commands",
        "inline": "Inline",
        "builtin_badge": "built-in",
        "external_badge": "external",
        "settings_btn": "⚙ Settings",
        "hide_btn": "Hide",
        "unhide_btn": "Unhide",
        "missing": "🚫 Module {} not found",
    }

    strings_ru = {
        "modules_count": "{} модуль|{} модуля|{} модулей",
        "prefix_badge": "префикс {}",
        "hidden_badge": "{} скрыто",
        "restricted": "Некоторые модули не показаны из-за отсутствия прав",
        "builtin_section": "Встроенные",
        "external_section": "Модули",
        "nothing": "Нечего показать",
        "no_commands_badge": "нет команд",
        "hidden_title": "Скрытые модули",
        "hidden_hint": "Вернуть модуль можно через {}helphide <название>",
        "hidden_none": "Нет скрытых модулей",
        "unhide_short": "вернуть",
        "unhide_all": "Вернуть все",
        "hidden_done": "🙈 Модуль скрыт",
        "shown_done": "👁 Модуль возвращен",
        "shown_all_done": "👁 Все модули возвращены",
        "commands": "Команды",
        "no_commands": "Нет команд",
        "inline": "Инлайн",
        "builtin_badge": "встроенный",
        "external_badge": "внешний",
        "settings_btn": "⚙ Настройки",
        "hide_btn": "Скрыть",
        "unhide_btn": "Вернуть",
        "missing": "🚫 Модуль {} не найден",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "core_emoji",
                "<emoji document_id=6030550768426159669>🛡</emoji>",
                lambda: "Core module bullet",
            ),
            loader.ConfigValue(
                "plain_emoji",
                "<emoji document_id=5861640841524680405>✅</emoji>",
                lambda: "Plain module bullet",
            ),
            loader.ConfigValue(
                "empty_emoji",
                "<emoji document_id=5251741320690551495>👎</emoji>",
                lambda: "Empty modules bullet",
            ),
            loader.ConfigValue(
                "desc_icon",
                "<emoji document_id=5253521692008917018>🌙</emoji>",
                lambda: "Desc emoji",
            ),
            loader.ConfigValue(
                "expandable",
                True,
                lambda: "If the blockquote will be expandable",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "hide_core_modules",
                False,
                lambda: "Hide all core modules",
                on_change=lambda: (
                    self.set(
                        "hide",
                        (
                            list(
                                {
                                    *self.get("hide", []),
                                    *[
                                        m.__class__.__name__
                                        for m in self.allmodules.modules
                                        if getattr(m, "__origin__", None) == "<core>"
                                    ],
                                }
                            )
                            if self.config["hide_core_modules"]
                            else [
                                m
                                for m in self.get("hide", [])
                                if getattr(self.lookup(m), "__origin__") != "<core>"
                            ]
                        ),
                    )
                ),
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "show_cmds",
                True,
                lambda: "Displays a short list of commands next to the module",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "help_banner_url",
                "https://i.postimg.cc/MpWWpjSP/Legacy-New-Gen.jpg",
                lambda: "Banner URL for .help",
            ),
        )

    @loader.command()
    async def helphide(self, message: Message):
        if not (modules := utils.get_args_split_by(message, ["\n", ","])):
            await utils.answer(message, self.strings("no_mod"))
            return

        currently_hidden = self.get("hide", [])
        hidden, shown = [], []
        for module in filter(lambda module: self.lookup(module), modules):
            module = self.lookup(module)
            module_origin = module.__origin__
            module = module.__class__.__name__

            if self.config["hide_core_modules"] and module_origin == "<core>":
                continue

            if module in currently_hidden:
                currently_hidden.remove(module)
                shown += [module]
            else:
                currently_hidden += [module]
                hidden += [module]

        self.set("hide", currently_hidden)

        await utils.answer(
            message,
            self.strings("hidden_shown").format(
                len(hidden),
                len(shown),
                "\n".join([f"👁‍🗨 <i>{m}</i>" for m in hidden]),
                "\n".join([f"👁 <i>{m}</i>" for m in shown]),
            ),
        )

    def find_aliases(self, command: str) -> list:
        """Find aliases for command"""
        aliases = []
        _command = self.allmodules.commands[command]
        if getattr(_command, "alias", None) and not (
            aliases := getattr(_command, "aliases", None)
        ):
            aliases = [_command.alias]
        if getattr(_command, "aliases", None):
            aliases = _command.aliases

        return aliases or []

    @staticmethod
    def _mod_name(module: typing.Any) -> str:
        try:
            return module.strings["name"]
        except (KeyError, AttributeError, TypeError):
            return getattr(module, "name", None) or module.__class__.__name__

    @staticmethod
    def _is_core(module: typing.Any) -> bool:
        return getattr(module, "__origin__", "").startswith("<core")

    @staticmethod
    def _summary(module: typing.Any, limit: int = SUMMARY) -> str:
        doc = (inspect.getdoc(module) or "").strip().split("\n")[0]
        return doc if len(doc) <= limit else doc[: limit - 1] + "…"

    def _logo(self, k: Screen) -> str:
        if k.premium:
            return re.sub(
                r"<emoji document_id=(\d+)>",
                r'<tg-emoji emoji-id="\1">',
                utils.get_platform_emoji(),
            )

        return "<b>Legacy</b>"

    def _find(self, name: str) -> typing.Optional[typing.Any]:
        return next(
            (
                module
                for module in self.allmodules.modules
                if module.__class__.__name__ == name or self._mod_name(module) == name
            ),
            None,
        )

    def _owners(self) -> list:
        return [self._client.tg_id, *self._client.dispatcher.security._owner]

    async def _allowed_inline(self, message: Message, module: typing.Any) -> list:
        results = await asyncio.gather(
            *(
                self.inline.check_inline_security(
                    func=func,
                    user=message.sender_id if not message.out else self._client.tg_id,
                )
                for func in module.inline_handlers.values()
            )
        )
        return [
            name
            for name, passed in zip(module.inline_handlers.keys(), results)
            if passed is True
        ]

    async def _catalog(
        self,
        message: Message,
        force: bool,
    ) -> typing.Tuple[typing.List[dict], bool]:
        """
        Modules to list in help, with the commands the caller is allowed to use
        :return: Entries and whether some modules were left out for lack of rights
        """
        hidden = self.get("hide", [])
        entries, restricted = [], False
        for module in self.allmodules.modules:
            if not hasattr(module, "commands"):
                logger.debug("Module %s is not inited yet", module.__class__.__name__)
                continue

            if module.__class__.__name__ in hidden and not force:
                continue

            entry = {
                "module": module,
                "name": self._mod_name(module),
                "core": self._is_core(module),
                "hidden": module.__class__.__name__ in hidden,
                "empty": False,
            }
            if not module.commands and not getattr(module, "inline_handlers", None):
                entries.append({**entry, "empty": True, "count": 0})
                continue

            commands = [
                name
                for name, func in module.commands.items()
                if force or await self.allmodules.check_security(message, func)
            ]
            inline = (
                list(module.inline_handlers)
                if force
                else await self._allowed_inline(message, module)
            )
            if commands or inline:
                entries.append({**entry, "count": len(commands) + len(inline)})
            elif module.commands or module.inline_handlers:
                restricted = True

        entries.sort(key=lambda entry: (entry["empty"], entry["name"].casefold()))
        return entries, restricted

    def _entry(self, k: Screen, entry: dict, message: Message, back: tuple) -> str:
        line = f"{k.icon('core' if entry['core'] else 'module')} " + k.tap(
            entry["name"], self._card_cb, message, entry["name"], back
        )
        line += " " + (
            k.badge(self.strings("no_commands_badge"))
            if entry["empty"]
            else k.badge(entry["count"], "primary")
        )

        if summary := self._summary(entry["module"]):
            line += f" <i>{escape(summary)}</i>"

        return line

    async def _home_screen(
        self,
        message: Message,
        force: bool = False,
        page: int = 0,
    ) -> Screen:
        k = self.inline.screen()
        entries, restricted = await self._catalog(message, force)

        external = [entry for entry in entries if not entry["core"]]
        core = [entry for entry in entries if entry["core"]]
        # Built-in modules stay on every page, only external ones are paged
        external_page, page, pages = k.page(external, page, PAGE_SIZE)
        shown = external_page + core
        state = (message, force)
        back = (self._home_cb, state, {"page": page})

        if banner := utils.normalize_banner_url(self.config["help_banner_url"]):
            k.add(k.image(str(banner)))

        hidden = sum(
            module.__class__.__name__ in self.get("hide", [])
            for module in self.allmodules.modules
        )
        head = (
            f"{self._logo(k)} "
            + k.badge(
                plural(len(self.allmodules.modules), self.strings("modules_count")),
                "primary",
            )
            + " "
            + k.badge(
                self.strings("prefix_badge").format(
                    self.get_prefix(message.sender_id)
                )
            )
        )
        if hidden and not force:
            head += " " + k.tap(
                self.strings("hidden_badge").format(hidden),
                self._hidden_cb,
                message,
                back,
                style=None,
                icon="hide",
            )

        k.add(head)
        if restricted:
            k.add(f"<i>{escape(self.strings('restricted'))}</i>")

        external_shown = [entry for entry in shown if not entry["core"]]
        for items, total, icon, title, opened in (
            (
                [entry for entry in shown if entry["core"]],
                len(core),
                "core",
                "builtin_section",
                not external_shown,
            ),
            (external_shown, len(external), "module", "external_section", False),
        ):
            if items:
                k.add(
                    k.details(
                        f"{k.icon(icon)} <b>{escape(self.strings(title))}</b> · {total}",
                        "\n".join(
                            self._entry(k, entry, message, back) for entry in items
                        ),
                        open=opened,
                    )
                )

        if not entries:
            k.add(f"<i>{escape(self.strings('nothing'))}</i>")

        if not getattr(self.lookup("Loader"), "fully_loaded", True):
            k.add(f"{k.icon('info')} <i>{_emojify(self.strings('partial_load'))}</i>")

        k.keyboard(
            k.pager(self._home_cb, page, pages, *state),
            [k.close()],
        )
        return k

    async def _hidden_screen(self, message: Message, back: tuple) -> Screen:
        k = self.inline.screen()
        entries, _ = await self._catalog(message, True)
        entries = [entry for entry in entries if entry["hidden"]]
        here = (self._hidden_cb, (message, back), {})

        k.add(
            f"{k.icon('hide')} <b>{escape(self.strings('hidden_title'))}</b> "
            + k.badge(len(entries), "primary")
        )
        rows = []
        if entries:
            hint = self.strings("hidden_hint").format(
                self.get_prefix(message.sender_id)
            )
            k.add(f"<i>{escape(hint)}</i>")
            k.add(
                "\n".join(
                    self._entry(k, entry, message, here)
                    + " "
                    + k.tap(
                        self.strings("unhide_short"),
                        self._unhide_cb,
                        message,
                        entry["module"].__class__.__name__,
                        back,
                        style=None,
                        icon="eye",
                    )
                    for entry in entries
                )
            )
            rows.append(
                k.button(
                    self.strings("unhide_all"),
                    self._unhide_cb,
                    message,
                    None,
                    back,
                    style="success",
                    icon="eye",
                )
            )
        else:
            k.add(f"<i>{escape(self.strings('hidden_none'))}</i>")

        callback, args, kwargs = back
        k.keyboard(rows, [k.back(callback, *args, kwargs=kwargs), k.close()])
        return k

    def _parse_doc(self, func: typing.Any) -> typing.Tuple[str, str]:
        """:return: Usage (`[args]`) and description of a command"""
        doc = (inspect.getdoc(func) or "").strip()
        if match := re.match(r"^((?:[\[<].*?[\]>]\s*)+)(?:[-|—:]\s*)?(.*)$", doc, re.S):
            return match[1].strip(), match[2].strip()

        return "", doc

    async def _card_screen(
        self,
        message: Message,
        module: typing.Any,
        back: tuple,
        *,
        closest: typing.Optional[str] = None,
    ) -> Screen:
        k = self.inline.screen()
        name = self._mod_name(module)
        prefix = self.get_prefix(message.sender_id)
        core = self._is_core(module)

        head = f"{k.icon('core' if core else 'module')} <b>{escape(name)}</b>"
        if version_ := getattr(module, "__version__", None):
            head += " " + k.badge(
                "v"
                + (
                    ".".join(map(str, version_))
                    if isinstance(version_, tuple)
                    else str(version_)
                )
            )

        head += " " + k.badge(
            self.strings("builtin_badge" if core else "external_badge"),
            None if core else "success",
        )
        k.add(head)
        if description := inspect.getdoc(module):
            k.add(k.quote(escape(description)))

        commands = []
        for command, func in module.commands.items():
            if not await self.allmodules.check_security(message, func):
                continue

            usage, description = self._parse_doc(func)
            aliases = (
                ", ".join(
                    f"<code>{escape(prefix + alias)}</code>"
                    for alias in self.find_aliases(command)
                )
                if command in self.allmodules.commands
                else ""
            )
            commands.append(
                f"<code>{escape(prefix + command)}</code>"
                + (f" <i>{escape(usage)}</i>" if usage else "")
                + f" — {escape(description) if description else '<i>' + escape(self.strings('undoc')) + '</i>'}"
                + (f" ({aliases})" if aliases else "")
                + " "
                + k.copy("", prefix + command)
            )

        title = f"{k.icon('command')} <b>{escape(self.strings('commands'))}</b> · {len(commands)}"
        k.add(
            k.details(
                title,
                "\n".join(commands) or f"<i>{escape(self.strings('no_commands'))}</i>",
                open=len(commands) <= OPEN_LIMIT,
            )
        )

        bot = escape(self.inline.bot_username or "bot")
        handlers = [
            f"{k.icon('bot')} <code>@{bot} {escape(command)}</code>"
            f" — {escape(inspect.getdoc(func) or self.strings('undoc'))}"
            for command, func in getattr(module, "inline_handlers", {}).items()
        ] + [
            f"{k.icon('guest')} <code>@{bot} {escape(command)}</code>"
            f" — {escape(inspect.getdoc(func) or self.strings('undoc'))}"
            for command, func in getattr(module, "guest_handlers", {}).items()
        ]
        if handlers:
            k.add(
                k.details(
                    f"{k.icon('bot')} <b>{escape(self.strings('inline'))}</b> · {len(handlers)}",
                    "\n".join(handlers),
                )
            )

        if closest:
            k.notice = f"{k.icon('info')} <i>{_emojify(self.strings('not_exact'))}</i>"

        hidden = module.__class__.__name__ in self.get("hide", [])
        config = self.lookup("LegacyConfig")
        rows = []
        if (
            getattr(module, "config", None)
            and config
            and hasattr(config, "module_screen")
            and (message.out or message.sender_id in self._owners())
        ):
            rows.append(
                k.button(
                    self.strings("settings_btn"),
                    self._settings_cb,
                    message,
                    name,
                    back,
                    icon="settings",
                )
            )

        rows.append(
            k.button(
                self.strings("unhide_btn" if hidden else "hide_btn"),
                self._hide_cb,
                message,
                name,
                back,
                icon="eye" if hidden else "hide",
            )
        )
        callback, args, kwargs = back
        k.keyboard(rows, [k.back(callback, *args, kwargs=kwargs), k.close()])
        return k

    async def _home_cb(
        self,
        call: InlineCall,
        message: Message,
        force: bool = False,
        page: int = 0,
    ):
        await self.inline.show(call, await self._home_screen(message, force, page))

    async def _card_cb(
        self,
        call: InlineCall,
        message: Message,
        name: str,
        back: typing.Optional[tuple] = None,
    ):
        back = back or (self._home_cb, (message,), {})
        if not (module := self._find(name)):
            screen = await self._home_screen(message)
            await self.inline.show(
                call, screen.warn(self.strings("missing").format(name))
            )
            return

        await self.inline.show(call, await self._card_screen(message, module, back))

    async def _settings_cb(
        self, call: InlineCall, message: Message, name: str, back: tuple
    ):
        config = self.lookup("LegacyConfig")
        module = self._find(name)
        if not config or not module:
            return

        await self.inline.show(
            call,
            config.module_screen(
                self._mod_name(module), self._card_cb, message, name, back
            ),
        )

    async def _hide_cb(
        self, call: InlineCall, message: Message, name: str, back: tuple
    ):
        if not (module := self._find(name)):
            return

        hidden = self.get("hide", [])
        key = module.__class__.__name__
        if key in hidden:
            hidden.remove(key)
            toast = self.strings("shown_done")
        else:
            hidden.append(key)
            toast = self.strings("hidden_done")

        self.set("hide", hidden)
        screen = await self._card_screen(message, module, back)
        screen.toast = toast
        await self.inline.show(call, screen)

    async def _hidden_cb(self, call: InlineCall, message: Message, back: tuple):
        await self.inline.show(call, await self._hidden_screen(message, back))

    async def _unhide_cb(
        self,
        call: InlineCall,
        message: Message,
        name: typing.Optional[str],
        back: tuple,
    ):
        """Returns the module `name` or all hidden ones to help"""
        hidden = self.get("hide", [])
        self.set("hide", [key for key in hidden if name is not None and key != name])
        screen = await self._hidden_screen(message, back)
        screen.toast = self.strings("shown_done" if name else "shown_all_done")
        await self.inline.show(call, screen)

    async def _send(self, message: Message, screen: Screen):
        if not self.inline.init_complete:
            await utils.answer(message, screen.plain()[0])
            return

        await self.inline.form("", message, rich_html=screen)

    def _resolve(self, message: Message, query: str) -> typing.Tuple[typing.Any, bool]:
        """:return: Module to show and whether it is an exact match"""
        if module := self.lookup(query):
            return module, True

        if method := self.allmodules.dispatch(
            query.lower().strip(self.get_prefix(message.sender_id))
        )[1]:
            return method.__self__, True

        closest = max(
            self.allmodules.modules,
            key=lambda module: difflib.SequenceMatcher(
                None, query.lower(), self._mod_name(module).lower()
            ).ratio(),
            default=None,
        )
        return closest, False

    @loader.command()
    async def help(self, message: Message):
        args = utils.get_args_raw(message)
        force = False
        only_hidden = False
        if "-f" in args:
            args = args.replace(" -f", "").replace("-f", "")
            force = True
        if "-h" in args:
            args = args.replace(" -h", "").replace("-h", "")
            only_hidden = True

        args = args.strip()
        if not args:
            if only_hidden:
                await self._send(
                    message,
                    await self._hidden_screen(
                        message, (self._home_cb, (message, force), {})
                    ),
                )
                return

            await self._send(message, await self._home_screen(message, force))
            return

        module, exact = self._resolve(message, args)
        if isinstance(module, loader.Library):
            await utils.answer(
                message, self.strings("lib_help").format(self._mod_name(module))
            )
            return

        if module is None:
            await utils.answer(
                message, self.strings("missing").format(utils.escape_html(args))
            )
            return

        await self._send(
            message,
            await self._card_screen(
                message,
                module,
                (self._home_cb, (message, force), {}),
                closest=None if exact else self._mod_name(module),
            ),
        )

    @loader.command()
    async def support(self, message):
        await utils.answer(
            message,
            self.strings["support"].format(
                (
                    utils.get_platform_emoji()
                    if self._client.legacy_me.premium and CUSTOM_EMOJIS
                    else "🌙"
                )
            ),
        )
