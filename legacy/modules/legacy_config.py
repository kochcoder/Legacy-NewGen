# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import ast
import contextlib
import typing

from legacytl.tl.types import Message

from .. import loader, translations, utils
from ..inline.screens import COPY_LIMIT, Screen, escape, plural
from ..inline.types import InlineCall

PREVIEW = 32
LONG_VALUE = 64
SERIES_ITEMS = 30
HIDDEN = "••••••"

TEXT_KINDS = {"Boolean", "Choice", "MultiChoice", "Integer", "Float"}

# `origin` tells a screen where its «Back» leads:
# None — home, ("help", callback, args) — a help card


@loader.tds
class LegacyConfigMod(loader.Module):
    """Interactive configurator for Legacy Userbot"""

    strings = {"name": "LegacyConfig"}

    strings_en = {
        "title": "Legacy Config",
        "modules_count": "{} module|{} modules",
        "changed_count": "✎ {} changed",
        "empty": "Nothing to configure",
        "mod_missing": "🚫 Module <b>{}</b> not found",
        "param_missing": "🚫 Module <b>{}</b> has no parameter <b>{}</b>",
        "module_settings": "Settings",
        "no_params": "No configurable parameters",
        "about": "About parameters",
        "reset_all_btn": "↺ Reset all",
        "reset_confirm": "Reset all parameters of {} to defaults?",
        "reset_yes_btn": "Yes, reset",
        "cancel_btn": "Cancel",
        "reset_done": "↺ All parameters reset to defaults",
        "current": "Current",
        "default": "Default",
        "type": "Type",
        "any_type": "any",
        "long_hint": "The value is too long — tap the quote to expand it",
        "on": "On",
        "off": "Off",
        "on_short": "on",
        "off_short": "off",
        "items_count": "{} item|{} items",
        "show_btn": "Show",
        "hide_btn": "Hide",
        "add_btn": "Add",
        "add_prompt": "Enter an item to add",
        "remove_btn": "Remove",
        "remove_prompt": "Enter item(s) to remove",
        "edit_btn": "✎ Edit",
        "edit_prompt": "Enter new value for {}",
        "copy_btn": "Copy",
        "saved": "✅ Saved",
        "not_in_list": "Nothing from the passed value is in the target list",
        "more_items": "… and {} more",
        "owner_only": "🚫 Only the owner can change settings here",
    }

    strings_ru = {
        "title": "Конфиг Legacy",
        "modules_count": "{} модуль|{} модуля|{} модулей",
        "changed_count": "✎ изменено: {}",
        "empty": "Нечего настраивать",
        "mod_missing": "🚫 Модуль <b>{}</b> не найден",
        "param_missing": "🚫 У модуля <b>{}</b> нет параметра <b>{}</b>",
        "module_settings": "Настройки",
        "no_params": "Нет настраиваемых параметров",
        "about": "О параметрах",
        "reset_all_btn": "↺ Сбросить всё",
        "reset_confirm": "Сбросить все параметры {} к значениям по умолчанию?",
        "reset_yes_btn": "Да, сбросить",
        "cancel_btn": "Отмена",
        "reset_done": "↺ Все параметры сброшены",
        "current": "Текущее",
        "default": "Стандартное",
        "type": "Тип",
        "any_type": "любой",
        "long_hint": "Значение слишком длинное — нажми на цитату, чтобы развернуть",
        "on": "Вкл",
        "off": "Выкл",
        "on_short": "вкл",
        "off_short": "выкл",
        "items_count": "{} элемент|{} элемента|{} элементов",
        "show_btn": "Показать",
        "hide_btn": "Скрыть",
        "add_btn": "Добавить",
        "add_prompt": "Введи элемент для добавления",
        "remove_btn": "Удалить",
        "remove_prompt": "Введи элемент(ы) для удаления",
        "edit_btn": "✎ Изменить",
        "edit_prompt": "Введи новое значение для {}",
        "copy_btn": "Копировать",
        "saved": "✅ Сохранено",
        "not_in_list": "Ничего из переданного значения нет в списке",
        "more_items": "… и ещё {}",
        "owner_only": "🚫 Только владелец может менять настройки здесь",
    }

    @staticmethod
    def prep_value(value: typing.Any, _cut: bool = False) -> typing.Any:
        if isinstance(value, str):
            val = (
                f"{utils.escape_html(str(value)[:24])}..."
                if _cut and len(str(value)) > 24
                else utils.escape_html(str(value).strip())
            )
            return f"</b><code>{val}</code><b>"

        if isinstance(value, list) and value:
            val = [
                (
                    f"<code>{utils.escape_html(str(item)[:16]).strip()}...</code>"
                    if _cut and len(str(item)) > 16
                    else f"<code>{utils.escape_html(str(item)).strip()}</code>"
                )
                for item in value
            ]
            return "</b><code>[</code>" + ", ".join(val) + "<code>]</code><b>"
        return f"</b><code>{utils.escape_html(f'{str(value)[:24]}...') if len(str(value)) > 24 else utils.escape_html(str(value))}</code><b>"

    def hide_value(self, value: typing.Any) -> str:
        if isinstance(value, list) and value:
            return self.prep_value(["*" * len(str(i)) for i in value], True)

        return self.prep_value("*" * len(str(value)), True)

    def _get_value(self, mod: str, option: str) -> str:
        return (
            self.prep_value(self.lookup(mod).config[option], True)
            if (
                not self.lookup(mod).config._config[option].validator
                or self.lookup(mod).config._config[option].validator.internal_id
                != "Hidden"
            )
            else self.hide_value(self.lookup(mod).config[option])
        )

    @staticmethod
    def _name(mod: typing.Any) -> str:
        return mod.name if isinstance(mod, loader.Library) else mod.strings("name")

    @staticmethod
    def _kind(mod: typing.Any) -> str:
        if isinstance(mod, loader.Library):
            return "library"

        return "core" if mod.__origin__.startswith("<core") else "external"

    def _lookup(self, name: str) -> typing.Optional[typing.Any]:
        mod = self.lookup(name) if name else None
        return mod if mod and getattr(mod, "config", None) is not None else None

    def _configurable(self) -> typing.Dict[str, list]:
        groups = {"core": [], "external": [], "library": []}
        for mod in self.allmodules.modules:
            if getattr(mod, "config", None) and callable(getattr(mod, "strings", None)):
                groups[self._kind(mod)].append(mod)

        for lib in self.allmodules.libraries:
            if getattr(lib, "config", None):
                groups["library"].append(lib)

        for mods in groups.values():
            mods.sort(key=lambda mod: self._name(mod).casefold())

        return groups

    @staticmethod
    def _is_changed(config: typing.Any, param: str) -> bool:
        try:
            return config[param] != config.getdef(param)
        except Exception:
            return False

    def _changed(self, mod: typing.Any) -> int:
        return sum(self._is_changed(mod.config, param) for param in mod.config)

    @staticmethod
    def _validator(
        mod: typing.Any, param: str
    ) -> typing.Tuple[typing.Any, typing.Any, bool]:
        """:return: Validator, validator it wraps (if hidden) and if it is hidden"""
        validator = mod.config._config[param].validator
        hidden = getattr(validator, "internal_id", None) == "Hidden"
        inner = (
            getattr(validator.validate, "keywords", {}).get("validator", validator)
            if hidden
            else validator
        )
        return validator, inner, hidden

    @staticmethod
    def _keywords(validator: typing.Any) -> dict:
        return getattr(getattr(validator, "validate", None), "keywords", None) or {}

    def _doc(self, mod: typing.Any, param: str) -> str:
        try:
            doc = mod.config.getdoc(param)
        except Exception:
            return ""

        return utils.escape_html(str(doc)) if doc else ""

    def _typehint(self, validator: typing.Any) -> str:
        try:
            doc = next(
                (
                    validator.doc[lang]
                    for lang in self._db.get(translations.__name__, "lang", "en").split(
                        " "
                    )
                    if lang in validator.doc
                ),
                validator.doc["en"],
            )
        except Exception:
            return ""

        return self.strings("typehint").format(
            doc,
            eng_art="n" if str(doc).lower().startswith(tuple("euioay")) else "",
        )

    def _range(self, validator: typing.Any) -> str:
        keywords = self._keywords(validator)
        low, high = keywords.get("minimum"), keywords.get("maximum")
        match low is not None, high is not None:
            case True, True:
                return f"{low:g}…{high:g}"
            case True, False:
                return f"≥ {low:g}"
            case False, True:
                return f"≤ {high:g}"

        return ""

    def _format(
        self,
        k: Screen,
        value: typing.Any,
        kind: typing.Optional[str],
        *,
        hidden: bool = False,
        limit: int = PREVIEW,
    ) -> str:
        if hidden:
            return f"<code>{HIDDEN}</code>"

        if kind == "Boolean" or isinstance(value, bool):
            return (
                f"{k.fallback('on')} {escape(self.strings('on_short'))}"
                if value
                else f"{k.fallback('off')} {escape(self.strings('off_short'))}"
            )

        if isinstance(value, list):
            return escape(plural(len(value), self.strings("items_count")))

        if value is None or value == "":
            return f"<i>{escape(self.strings('empty'))}</i>"

        text = str(value)
        text = text if len(text) <= limit else text[: limit - 1] + "…"
        return f"<code>{escape(text)}</code>"

    def _preview(self, k: Screen, mod: typing.Any, param: str) -> str:
        _, inner, hidden = self._validator(mod, param)
        return self._format(
            k, mod.config[param], getattr(inner, "internal_id", None), hidden=hidden
        )

    @staticmethod
    def _copy_text(value: typing.Any) -> str:
        if isinstance(value, list):
            return ", ".join(map(str, value))

        return "" if value is None else str(value)

    def _is_owner(self, call: typing.Any) -> bool:
        user = getattr(getattr(call, "from_user", None), "id", None)
        return user is None or user in [
            self._tg_id,
            *self._client.dispatcher.security._owner,
        ]

    async def _denied(self, call: typing.Any, origin: typing.Any) -> bool:
        """Settings opened from help are for the owner only, whoever may see the help"""
        if origin and origin[0] == "help" and not self._is_owner(call):
            with contextlib.suppress(Exception):
                await call.answer(self.strings("owner_only"), show_alert=True)
            return True

        return False

    def _back(self, k: Screen, origin: typing.Any) -> dict:
        if origin and origin[0] == "help":
            return k.back(origin[1], *origin[2])

        return k.back(self._home_cb)

    def _entry(self, k: Screen, mod: typing.Any, origin: typing.Any = None) -> str:
        name = self._name(mod)
        changed = self._changed(mod)
        return (
            f"{k.tap(name, self._module_cb, name, origin)} {k.badge(len(mod.config))}"
            + (f" {k.icon('edit')}{changed}" if changed else "")
        )

    def _home_screen(self) -> Screen:
        k = self.inline.screen()
        groups = self._configurable()
        total = sum(map(len, groups.values()))
        changed = sum(self._changed(mod) for mods in groups.values() for mod in mods)

        head = (
            f"{k.icon('settings')} <b>{escape(self.strings('title'))}</b> "
            + k.badge(plural(total, self.strings("modules_count")), "primary")
        )
        if changed:
            head += " " + k.badge(self.strings("changed_count").format(changed))

        k.add(head)
        for kind, icon, title in (
            ("core", "core", "builtin"),
            ("external", "external", "external"),
            ("library", "library", "libraries"),
        ):
            if mods := groups[kind]:
                k.add(
                    k.details(
                        f"{k.icon(icon)} <b>{escape(self.strings(title))}</b> · {len(mods)}",
                        "\n".join(self._entry(k, mod) for mod in mods),
                    )
                )

        if not total:
            k.add(f"<i>{escape(self.strings('empty'))}</i>")

        k.keyboard([k.close()])
        return k

    def _module_screen(self, name: str, origin: typing.Any = None) -> Screen:
        mod = self._lookup(name)
        if not mod:
            return self._home_screen().warn(self.strings("mod_missing").format(name))

        k = self.inline.screen()
        name = self._name(mod)
        changed = self._changed(mod)
        icon = "module" if self._kind(mod) == "external" else self._kind(mod)
        head = (
            f"{k.icon(icon)} <b>{escape(name)}</b> ›"
            f" {escape(self.strings('module_settings'))}"
        )
        if changed:
            head += " " + k.badge(self.strings("changed_count").format(changed))

        lines, docs = [], []
        for param in mod.config:
            lines.append(
                k.tap(param, self._param_cb, name, param, origin)
                + (f" {k.icon('edit')}" if self._is_changed(mod.config, param) else "")
                + f" {self._preview(k, mod, param)}"
            )
            if doc := self._doc(mod, param):
                docs.append(f"• <b>{escape(param)}</b> — {doc}")

        k.add(head, "\n".join(lines) or f"<i>{escape(self.strings('no_params'))}</i>")
        if docs:
            k.add(
                k.details(
                    f"{k.icon('info')} {escape(self.strings('about'))}", "\n".join(docs)
                )
            )

        if changed:
            k.keyboard(
                [
                    k.button(
                        self.strings("reset_all_btn"),
                        self._confirm_reset_cb,
                        name,
                        origin,
                        icon="reset",
                    )
                ]
            )

        k.keyboard([self._back(k, origin), k.close()])
        return k

    def _confirm_screen(self, name: str, origin: typing.Any = None) -> Screen:
        k = self.inline.screen()
        k.add(
            f"{k.icon('warning')} "
            + self.strings("reset_confirm").format(f"<b>{escape(name)}</b>")
        )
        k.keyboard(
            [
                k.button(
                    self.strings("reset_yes_btn"),
                    self._reset_all_cb,
                    name,
                    origin,
                    style="danger",
                    icon="reset",
                ),
                k.button(self.strings("cancel_btn"), self._module_cb, name, origin),
            ]
        )
        return k

    def _param_screen(
        self,
        name: str,
        param: str,
        origin: typing.Any = None,
        *,
        show: bool = False,
    ) -> Screen:
        mod = self._lookup(name)
        if not mod:
            return self._home_screen().warn(self.strings("mod_missing").format(name))

        name = self._name(mod)
        param = next(
            (key for key in mod.config if key.casefold() == str(param).casefold()),
            param,
        )
        if param not in mod.config:
            return self._module_screen(name, origin).warn(
                self.strings("param_missing").format(name, param)
            )

        k = self.inline.screen()
        config = mod.config
        value, default = config[param], config.getdef(param)
        validator, inner, hidden = self._validator(mod, param)
        kind = getattr(inner, "internal_id", None)
        masked = hidden and not show
        changed = self._is_changed(config, param)
        args = (name, param, origin)
        icon = "module" if self._kind(mod) == "external" else self._kind(mod)
        long_value = (
            kind not in TEXT_KINDS | {"Series"}
            and isinstance(value, str)
            and (len(value) > LONG_VALUE or "\n" in value)
        )

        k.add(
            f"{k.icon(icon)} {k.tap(name, self._module_cb, name, origin)} ›"
            f" <b>{escape(param)}</b>" + (f" {k.icon('edit')}" if changed else "")
        )
        if doc := self._doc(mod, param):
            k.add(k.quote(doc))

        facts = []
        if not long_value or masked:
            facts.append(
                [
                    escape(self.strings("current")),
                    self._format(k, value, kind, hidden=masked, limit=48),
                ]
            )

        facts.append(
            [
                escape(self.strings("default")),
                self._format(k, default, kind, hidden=hidden and not show, limit=48),
            ]
        )
        facts.append(
            [
                escape(self.strings("type")),
                f"<code>{escape(kind or self.strings('any_type'))}</code>"
                + (f" · {escape(self._range(inner))}" if self._range(inner) else ""),
            ]
        )
        k.add(k.table(facts))

        if long_value and not masked:
            k.add(
                f"<b>{escape(self.strings('current'))}</b>",
                k.quote(escape(value), expandable=True),
                f"{k.icon('info')} <i>{escape(self.strings('long_hint'))}</i>",
            )

        if kind not in TEXT_KINDS and (hint := self._typehint(validator)):
            k.add(f"<i>{escape(hint)}</i>")

        if hidden:
            k.add(
                k.row(
                    k.tap(
                        self.strings("hide_btn" if show else "show_btn"),
                        self._param_cb,
                        *args,
                        style=None,
                        icon="hide" if show else "eye",
                        kwargs={"show": not show},
                    )
                )
            )

        if not masked:
            self._controls(k, kind, inner, value, default, args)

        if kind not in TEXT_KINDS:
            k.reply(self._value_reply, *args)

        if kind == "Series":
            k.keyboard(
                [
                    k.input(
                        self.strings("add_btn"),
                        self._add_input,
                        self.strings("add_prompt"),
                        *args,
                        icon="add",
                    )
                ]
                + (
                    [
                        k.input(
                            self.strings("remove_btn"),
                            self._remove_input,
                            self.strings("remove_prompt"),
                            *args,
                            icon="remove",
                        )
                    ]
                    if isinstance(value, list) and len(value) > SERIES_ITEMS
                    else []
                )
            )

        actions = []
        if kind != "Boolean":
            actions.append(
                k.input(
                    self.strings("edit_btn"),
                    self._value_input,
                    self.strings("edit_prompt").format(param),
                    *args,
                    icon="edit",
                )
            )

        text = self._copy_text(value)
        if (
            not hidden
            and kind not in {"Boolean", "Choice"}
            and 0 < len(text) <= COPY_LIMIT
        ):
            actions.append(k.copy_button(self.strings("copy_btn"), text))

        if changed:
            actions.append(
                k.button(
                    self.strings("set_default_btn"),
                    self._reset_param_cb,
                    *args,
                    icon="reset",
                )
            )

        k.keyboard(actions, k.footer(self._module_cb, name, origin))
        return k

    def _controls(
        self,
        k: Screen,
        kind: typing.Optional[str],
        validator: typing.Any,
        value: typing.Any,
        default: typing.Any,
        args: tuple,
    ):
        match kind:
            case "Boolean":
                k.add(
                    k.row(
                        k.tap(
                            f"{'●' if value else '○'} {self.strings('on')}",
                            self._set_cb,
                            *args,
                            style="success" if value else None,
                            kwargs={"value": True},
                        ),
                        k.tap(
                            f"{'○' if value else '●'} {self.strings('off')}",
                            self._set_cb,
                            *args,
                            style=None if value else "danger",
                            kwargs={"value": False},
                        ),
                    )
                )
            case "Choice" | "MultiChoice":
                options = list(self._keywords(validator).get("possible_values", []))
                chosen = (
                    (lambda option: option in (value or []))
                    if kind == "MultiChoice"
                    else (lambda option: option == value)
                )
                mark = (
                    (lambda option: "✓ " if chosen(option) else "")
                    if kind == "MultiChoice"
                    else (lambda option: "● " if chosen(option) else "○ ")
                )
                buttons = [
                    k.tap(
                        mark(option) + utils.remove_html(str(option))[:24],
                        self._toggle_cb if kind == "MultiChoice" else self._set_cb,
                        *args,
                        style="success" if chosen(option) else None,
                        kwargs={"value": option},
                    )
                    for option in options
                ]
                width = 3 if len(buttons) > 4 or len(buttons) == 3 else 2
                k.add("".join(k.row(*chunk) for chunk in utils.chunks(buttons, width)))
            case "Integer" | "Float":
                keywords = self._keywords(validator)
                low, high = keywords.get("minimum"), keywords.get("maximum")
                integer = kind == "Integer"
                current = next(
                    (
                        number
                        for number in (value, default, 0)
                        if isinstance(number, (int, float))
                        and not isinstance(number, bool)
                    )
                )
                buttons = []
                steps = (10, 1) if integer else (1, 0.1)
                for step in (*(-size for size in steps), *reversed(steps)):
                    target = current + step if integer else float(f"{current + step:.6f}")
                    label = ("+" if step > 0 else "−") + format(abs(step), "g")
                    out_of_range = (low is not None and target < low) or (
                        high is not None and target > high
                    )
                    if out_of_range:
                        buttons.append(k.badge(label))
                    else:
                        buttons.append(
                            k.tap(
                                label,
                                self._step_cb,
                                *args,
                                style=None,
                                kwargs={"step": step},
                            )
                        )

                buttons.insert(2, k.badge(f"{current:g}", "primary"))
                k.add(k.row(*buttons, align="center"))
            case "Series":
                items = value if isinstance(value, list) else []
                k.add(
                    "\n".join(
                        k.tap(
                            "",
                            self._remove_item_cb,
                            *args,
                            style=None,
                            icon="remove",
                            kwargs={"index": index, "item": item},
                            text=f"✕ {item}",
                        )
                        + f" <code>{escape(item)}</code>"
                        for index, item in enumerate(items[:SERIES_ITEMS])
                    )
                    or f"<i>{escape(self.strings('empty'))}</i>"
                )
                if len(items) > SERIES_ITEMS:
                    k.add(
                        f"<i>{escape(self.strings('more_items').format(len(items) - SERIES_ITEMS))}</i>"
                    )

    def module_screen(self, name: str, back: typing.Callable, *args) -> Screen:
        """Settings of a module, which lead back to `back(call, *args)`"""
        return self._module_screen(name, ("help", back, args))

    async def _home_cb(self, call: InlineCall):
        await self.inline.show(call, self._home_screen())

    async def _module_cb(self, call: InlineCall, name: str, origin: typing.Any = None):
        if await self._denied(call, origin):
            return

        await self.inline.show(call, self._module_screen(name, origin))

    async def _param_cb(
        self,
        call: InlineCall,
        name: str,
        param: str,
        origin: typing.Any = None,
        show: bool = False,
    ):
        if await self._denied(call, origin):
            return

        await self.inline.show(call, self._param_screen(name, param, origin, show=show))

    async def _confirm_reset_cb(
        self, call: InlineCall, name: str, origin: typing.Any = None
    ):
        if await self._denied(call, origin):
            return

        await self.inline.show(call, self._confirm_screen(name, origin))

    async def _reset_all_cb(
        self, call: InlineCall, name: str, origin: typing.Any = None
    ):
        if await self._denied(call, origin):
            return

        if mod := self._lookup(name):
            for param in mod.config:
                try:
                    mod.config[param] = mod.config.getdef(param)
                except loader.validators.ValidationError:
                    mod.config.set_no_raise(param, mod.config.getdef(param))

        screen = self._module_screen(name, origin)
        screen.toast = self.strings("reset_done")
        await self.inline.show(call, screen)

    async def _store(
        self,
        call: typing.Any,
        name: str,
        param: str,
        origin: typing.Any,
        apply: typing.Callable[[typing.Any], typing.Any],
        *,
        typed: bool = False,
    ):
        """
        Applies a change and shows the parameter again
        :param typed: Value was typed by user, there is no callback to toast to
        """
        if await self._denied(call, origin):
            return

        mod = self._lookup(name)
        if not mod or param not in mod.config:
            await self.inline.show(call, self._param_screen(name, param, origin))
            return

        try:
            apply(mod.config)
        except loader.validators.ValidationError as e:
            screen = self._param_screen(name, param, origin)
            screen.warn(str(e.args[0] if e.args else e))
        else:
            screen = self._param_screen(name, param, origin)
            if typed:
                screen.notice = escape(self.strings("saved"))
            else:
                screen.toast = self.strings("saved")

        await self.inline.show(call, screen)

    async def _set_cb(
        self,
        call: InlineCall,
        name: str,
        param: str,
        origin: typing.Any = None,
        value: typing.Any = None,
    ):
        def apply(config):
            config[param] = value

        await self._store(call, name, param, origin, apply)

    async def _toggle_cb(
        self,
        call: InlineCall,
        name: str,
        param: str,
        origin: typing.Any = None,
        value: typing.Any = None,
    ):
        def apply(config):
            current = list(config[param] or [])
            config[param] = (
                [item for item in current if item != value]
                if value in current
                else current + [value]
            )

        await self._store(call, name, param, origin, apply)

    async def _step_cb(
        self,
        call: InlineCall,
        name: str,
        param: str,
        origin: typing.Any = None,
        step: float = 0,
    ):
        def apply(config):
            current = config[param]
            if not isinstance(current, (int, float)) or isinstance(current, bool):
                current = config.getdef(param) or 0

            target = current + step
            config[param] = (
                int(target) if isinstance(step, int) else round(float(target), 6)
            )

        await self._store(call, name, param, origin, apply)

    async def _remove_item_cb(
        self,
        call: InlineCall,
        name: str,
        param: str,
        origin: typing.Any = None,
        index: int = 0,
        item: typing.Any = None,
    ):
        def apply(config):
            items = list(config[param] or [])
            if not 0 <= index < len(items) or items[index] != item:
                if item not in items:
                    raise loader.validators.ValidationError(self.strings("not_in_list"))

                items.remove(item)
            else:
                items.pop(index)

            config[param] = items

        await self._store(call, name, param, origin, apply)

    async def _reset_param_cb(
        self, call: InlineCall, name: str, param: str, origin: typing.Any = None
    ):
        def apply(config):
            config[param] = config.getdef(param)

        await self._store(call, name, param, origin, apply)

    @staticmethod
    def _items(query: str) -> list:
        with contextlib.suppress(Exception):
            query = ast.literal_eval(query)

        if isinstance(query, (set, tuple)):
            query = list(query)

        return query if isinstance(query, list) else [query]

    async def _value_input(
        self,
        call: InlineCall,
        query: str,
        name: str,
        param: str,
        origin: typing.Any = None,
    ):
        def apply(config):
            config[param] = query

        await self._store(call, name, param, origin, apply, typed=True)

    _value_reply = _value_input

    async def _add_input(
        self,
        call: InlineCall,
        query: str,
        name: str,
        param: str,
        origin: typing.Any = None,
    ):
        def apply(config):
            config[param] = list(config[param] or []) + self._items(query)

        await self._store(call, name, param, origin, apply, typed=True)

    async def _remove_input(
        self,
        call: InlineCall,
        query: str,
        name: str,
        param: str,
        origin: typing.Any = None,
    ):
        def apply(config):
            removed = set(map(str, self._items(query)))
            items = list(config[param] or [])
            left = [item for item in items if str(item) not in removed]
            if len(left) == len(items):
                raise loader.validators.ValidationError(self.strings("not_in_list"))

            config[param] = left

        await self._store(call, name, param, origin, apply, typed=True)

    @loader.command(alias="cfg")
    async def configcmd(self, message: Message):
        args = utils.get_args(message)
        screen = None
        if args:
            if mod := self._lookup(args[0]):
                screen = (
                    self._param_screen(self._name(mod), args[1])
                    if len(args) > 1
                    else self._module_screen(self._name(mod))
                )
            else:
                screen = self._home_screen().warn(
                    self.strings("mod_missing").format(args[0])
                )

        await self.inline.form("", message, rich_html=screen or self._home_screen())

    @loader.command(alias="fcfg")
    async def fconfig(self, message: Message):
        args = utils.get_args_raw(message).split(maxsplit=2)  # type: ignore

        if len(args) < 3:
            await utils.answer(message, self.strings["args"])  # type: ignore
            return

        mod, option, value = args

        if not (instance := self.lookup(mod)):
            await utils.answer(message, self.strings["no_mod"])  # type: ignore
            return

        if option not in instance.config:
            await utils.answer(message, self.strings["no_option"])  # type: ignore
            return

        instance.config[option] = value
        await utils.answer(
            message,  # type: ignore
            self.strings[
                (
                    "option_saved"
                    if isinstance(instance, loader.Module)
                    else "option_saved_lib"
                )
            ].format(
                utils.escape_html(option),
                utils.escape_html(mod),
                self._get_value(mod, option),
            ),
        )
