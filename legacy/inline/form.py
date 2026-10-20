# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ kochcoder, 2026
# This file is a part of Legacy NewGen Userbot
# 🌐 https://github.com/kochcoder/Legacy-NewGen
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import contextlib
import copy
import logging
import os
import random
import re
import time
import traceback
import typing
from collections.abc import Callable
import asyncio
from asyncio import Event
from urllib.parse import urlparse

import grapheme
from legacytl.client.buttons import ButtonMethods
from legacytl.errors.rpcerrorlist import ChatSendInlineForbiddenError
from legacytl.extensions.html import CUSTOM_EMOJIS
from legacytl.tl.types import (
    InputBotInlineMessageRichMessage,
    InputBotInlineResult,
    InputGeoPoint,
    InputRichMessageHTML,
    Message,
)

from .. import main, utils
from ..types import LegacyReplyMarkup
from .types import InlineMessage, InlineUnit

if typing.TYPE_CHECKING:
    from ..inline.core import InlineManager

logger = logging.getLogger(__name__)

VERIFICATION_EMOJIES = list(
    grapheme.graphemes(
        "👨‍🏫👩‍🏫👨‍🎤🧑‍🎤👩‍🎤👨‍🎓👩‍🎓👩‍🍳👩‍🌾👩‍⚕️🕵️‍♀️💂‍♀️👷‍♂️👮‍♂️👴🧑‍🦳👩‍🦳👱‍♀️👩‍🦰👨‍🦱👩‍⚖️🧙‍♂️🧝‍♀️🧛‍♀️"
        "🎅🧚‍♂️🙆‍♀️🙍‍♂️👩‍👦🧶🪢🪡🧵🩲👖👕👚🦺👗👙🩱👘🥻🩴🥿🧦🥾👟👞"
        "👢👡👠🪖👑💍👝👛👜💼🌂🥽🕶👓🧳🎒🐶🐱🐭🐹🐰🦊🐻🐷🐮"
        "🦁🐯🐨🐻‍❄️🐼🐽🐸🐵🙈🙉🙊🐒🦆🐥🐣🐤🐦🐧🐔🦅🦉🦇🐺🐗🐴"
        "🦄🐜🐞🐌🦋🐛🪱🐝🪰🪲🪳🦟🦗🕷🕸🐙🦕🦖🦎🐍🐢🦂🦑🦐🦞"
        "🦀🐡🐠🐟🐅🐊🦭🦈🐋🐳🐬🐆🦓🦍🦧🦣🐘🦛🐃🦬🦘🦒🐫🐪🦏"
        "🐂🐄🐎🐖🐏🐑🦙🐈🐕‍🦺🦮🐩🐕🦌🐐🐈‍⬛🪶🐓🦃🦤🦚🦜🦡🦨🦝🐇"
        "🕊🦩🦢🦫🦦🦥🐁🐀🐿🦔🌳🌲🌵🐲🐉🐾🎋🍂🍁🍄🐚🌾🪨💐🌷"
        "🥀🌺🌸🌻🌞🌜🌘🌗🌎🌙💫⭐️✨⚡️☄️💥☀️🌪🔥🌈🌤⛅️❄️⛄️🌊"
        "☂️🍏🍎🍐🍊🍋🍌🍉🥭🍑🍒🍈🫐🍓🍇🍍🥥🥝🍅🥑🥦🧔‍♂️"
    )
)


class Placeholder:
    """Placeholder"""


_CUSTOM_EMOJI = re.compile(r"<(tg-emoji|emoji)\b[^>]*>(.*?)</\1>", re.S)


def _plain_emoji(text: str) -> str:
    """`text` with custom emoji replaced by their alt and the logo by one 🌙"""
    logo = utils.get_platform_emoji().replace(
        "<emoji document_id=", "<tg-emoji emoji-id="
    ).replace("</emoji>", "</tg-emoji>")
    return _CUSTOM_EMOJI.sub(r"\2", text.replace(logo, "🌙"))


def _is_reply(message: Message) -> bool:
    """Whether the message replies to another one, not just lives in a topic"""
    reply = message.reply_to
    return bool(
        getattr(reply, "reply_to_msg_id", None)
        and (not getattr(reply, "forum_topic", False) or reply.reply_to_top_id)
    )


class Form(InlineUnit):
    async def form(
        self: "InlineManager",
        text: str,
        message: Message | int,
        reply_markup: LegacyReplyMarkup | None = None,
        *,
        force_me: bool = False,
        always_allow: list[int] | None = None,
        manual_security: bool = False,
        disable_security: bool = False,
        ttl: int | None = None,
        on_unload: Callable | None = None,
        photo: str | None = None,
        gif: str | None = None,
        file: str | None = None,
        mime_type: str | None = None,
        video: str | None = None,
        location: str | None = None,
        audio: dict | str | None = None,
        silent: bool = False,
        rich_html: typing.Any = None,
    ) -> InlineMessage | bool:
        """
        Send inline form to chat
        :param text: Content of inline form. HTML markdown supported
        :param rich_html: Rich screen (`str`) or `Screen` with in-text buttons.
                          Falls back to plain text if Telegram declines it.
                          Mutually exclusive with `text`
        :param message: Where to send inline. Can be either `Message` or `int`
        :param reply_markup: List of buttons to insert in markup. List of dicts with keys: text, callback
        :param force_me: Either this form buttons must be pressed only by owner scope or no
        :param always_allow: Users, that are allowed to press buttons in addition to previous rules
        :param ttl: Time, when the form is going to be unloaded. Unload means, that the form
                    buttons with inline queries and callback queries will become unusable, but
                    buttons with type url will still work as usual. Pay attention, that ttl can't
                    be bigger, than default one (1 day) and must be either `int` or `False`
        :param on_unload: Callback, called when form is unloaded and/or closed. You can clean up trash
                          or perform another needed action
        :param manual_security: By default, Legacy newgen will try to inherit inline buttons security from the caller (command)
                                If you want to avoid this, pass `manual_security=True`
        :param disable_security: By default, Legacy newgen will try to inherit inline buttons security from the caller (command)
                                 If you want to disable all security checks on this form in particular, pass `disable_security=True`
        :param photo: Attach a photo to the form. URL must be supplied
        :param gif: Attach a gif to the form. URL must be supplied
        :param file: Attach a file to the form. URL must be supplied
        :param mime_type: Only needed, if `file` field is not empty. Must be either 'application/pdf' or 'application/zip'
        :param video: Attach a video to the form. URL must be supplied
        :param location: Attach a map point to the form. List/tuple must be supplied (latitude, longitude)
                         Example: (55.749931, 48.742371)
                         ⚠️ If you pass this parameter, you'll need to pass empty string to `text` ⚠️
        :param audio: Attach a audio to the form. Dict or URL must be supplied
        :param silent: Whether the form must be sent silently (w/o "Opening form..." message)
        :return: If form is sent, returns :obj:`InlineMessage`, otherwise returns `False`
        """
        with contextlib.suppress(AttributeError):
            _legacy_client_id_logging_tag = copy.copy(self._client.tg_id)  # noqa: F841

        if reply_markup is None:
            reply_markup = []

        if always_allow is None:
            always_allow = []

        if not isinstance(text, str):
            logger.error(
                "Invalid type for `text`. Expected `str`, got `%s`",
                type(text),
            )
            return False

        text = self.sanitise_text(
            text.replace("<emoji document_id=", "<tg-emoji emoji-id=").replace(
                "</emoji>", "</tg-emoji>"
            )
        )

        if not isinstance(silent, bool):
            logger.error(
                "Invalid type for `silent`. Expected `bool`, got `%s`",
                type(silent),
            )
            return False

        if not isinstance(manual_security, bool):
            logger.error(
                "Invalid type for `manual_security`. Expected `bool`, got `%s`",
                type(manual_security),
            )
            return False

        if not isinstance(disable_security, bool):
            logger.error(
                "Invalid type for `disable_security`. Expected `bool`, got `%s`",
                type(disable_security),
            )
            return False

        if not isinstance(message, (Message, int)):
            logger.error(
                "Invalid type for `message`. Expected `Message` or `int`, got `%s`",
                type(message),
            )
            return False

        if not isinstance(reply_markup, (list, dict)):
            logger.error(
                "Invalid type for `reply_markup`. Expected `list` or `dict`, got `%s`",
                type(reply_markup),
            )
            return False

        if photo and (not isinstance(photo, str) or not utils.check_url(photo)):
            logger.error(
                "Invalid type for `photo`. Expected `str` with URL, got `%s`",
                type(photo),
            )
            return False

        try:
            path = urlparse(photo).path
            ext = os.path.splitext(path)[1]
        except Exception:
            ext = None

        if photo is not None and ext in {".gif", ".mp4"}:
            gif = copy.copy(photo)
            photo = None

        if gif and (not isinstance(gif, str) or not utils.check_url(gif)):
            logger.error(
                "Invalid type for `gif`. Expected `str` with URL, got `%s`",
                type(gif),
            )
            return False

        if file and (not isinstance(file, str) or not utils.check_url(file)):
            logger.error(
                "Invalid type for `file`. Expected `str` with URL, got `%s`",
                type(file),
            )
            return False

        if file and not mime_type:
            logger.error(
                "You must pass `mime_type` along with `file` field\n"
                "It may be either 'application/zip' or 'application/pdf'"
            )
            return False

        if video and (not isinstance(video, str) or not utils.check_url(video)):
            logger.error(
                "Invalid type for `video`. Expected `str` with URL, got `%s`",
                type(video),
            )
            return False

        if isinstance(audio, str):
            audio = {"url": audio}

        if audio and (
            not isinstance(audio, dict)
            or "url" not in audio
            or not utils.check_url(audio["url"])
        ):
            logger.error(
                "Invalid type for `audio`. Expected `dict` with `url` key, got `%s`",
                type(audio),
            )
            return False

        if location and (
            not isinstance(location, (list, tuple))
            or len(location) != 2
            or not all(isinstance(item, float) for item in location)
        ):
            logger.error(
                (
                    "Invalid type for `location`. Expected `list` or `tuple` with 2"
                    " `float` items, got `%s`"
                ),
                type(location),
            )
            return False

        if [
            photo is not None,
            gif is not None,
            file is not None,
            video is not None,
            audio is not None,
            location is not None,
        ].count(True) > 1:
            logger.error("You passed two or more exclusive parameters simultaneously")
            return False

        reply_markup = self._validate_markup(reply_markup) or []

        if not isinstance(force_me, bool):
            logger.error(
                "Invalid type for `force_me`. Expected `bool`, got `%s`",
                type(force_me),
            )
            return False

        if not isinstance(always_allow, list):
            logger.error(
                "Invalid type for `always_allow`. Expected `list`, got `%s`",
                type(always_allow),
            )
            return False

        if not isinstance(ttl, int) and ttl:
            logger.error("Invalid type for `ttl`. Expected `int`, got `%s`", type(ttl))
            return False

        if isinstance(message, Message) and not silent:
            try:
                status_message = await (
                    message.edit if message.out else message.respond
                )(
                    (
                        utils.get_platform_emoji()
                        if self._client.legacy_me.premium
                        else "🌙"
                    )
                    + self.translator.getkey("inline.opening_form"),
                    **({"reply_to": utils.get_topic(message)} if message.out else {}),
                )
            except Exception:
                status_message = None
        else:
            status_message = None

        unit_id = utils.rand(16)

        perms_map = None if manual_security else self._find_caller_sec_map()

        # Plain forms with keyboard buttons are upgraded to rich screens,
        # so every form renders its buttons in-text instead of a bottom
        # keyboard. Media forms can't be rich, they are left as is
        if (
            rich_html is None
            and self._rich_enabled()
            and not any([photo, gif, file, video, audio, location])
            and reply_markup
            and self._has_embeddable_buttons(reply_markup)
        ):
            screen = self.screen()

            if text:
                screen.add(*text.splitlines())

            screen.keyboard(*reply_markup)
            rich_html = screen
            text = None
            # `html()` embeds the buttons into the text and prunes the markup
            # to the leftovers (input/web_app etc.) - reset the markup, so
            # the leftovers replace it below and no button renders twice
            reply_markup = []

        screen = None
        if rich_html is not None:
            from .screens import Screen

            if any([photo, gif, file, video, audio, location]):
                logger.error("`rich_html` can't be combined with media")
                return False

            if isinstance(rich_html, Screen):
                screen = rich_html
                # html() embeds keyboard buttons into the text and prunes
                # the markup, so it must run before the markup is read
                rich_html = screen.html()
                rich_source = screen.source
                if not reply_markup:
                    reply_markup = screen.markup
            elif isinstance(rich_html, str):
                rich_source = rich_html
            else:
                logger.error(
                    "Invalid type for `rich_html`. Expected `str` or `Screen`, got `%s`",
                    type(rich_html),
                )
                return False

            if text:
                logger.error("`rich_html` is mutually exclusive with `text`")
                return False

            if not self._rich_enabled():
                # Rich rendering is off: degrade the screen to a plain form.
                # In-text taps become regular keyboard buttons with the same
                # callback data, so handlers keep working
                text, rows = self._rich_to_plain(
                    rich_source,
                    {
                        tap["_callback_data"]: tap
                        for tap in (screen.taps.values() if screen else [])
                    },
                    reply_markup if isinstance(reply_markup, list) else [],
                )
                text = text or "­"
                reply_markup = rows
                rich_html = None
                screen = None
            else:
                text = rich_html

        # Edits of rich inline messages in groups keep custom emoji only if
        # the message is a reply, tdlib/telegram-bot-api#880, #904. So the
        # form replies to the command, which is deleted right after
        anchor = bool(
            isinstance(message, Message)
            and self._client.legacy_me.premium
            and CUSTOM_EMOJIS
            and rich_html is not None
            and (message.chat_id or 0) < 0
            and not _is_reply(message)
        )

        # Inline results lose custom emoji, edits keep them: the form is sent
        # with their alt text first and gets them with the next edit
        decorate = bool(
            self._client.legacy_me.premium
            and CUSTOM_EMOJIS
            and rich_html is None
            and not any((photo, gif, file, video, location, audio))
            and _CUSTOM_EMOJI.search(text) is not None
        )

        if not reply_markup and not ttl:
            logger.debug("Patching form reply markup with empty data")
            base_reply_markup = copy.deepcopy(reply_markup) or None
            reply_markup = self._validate_markup({"text": "­", "data": "­"})
        else:
            base_reply_markup = Placeholder()

        if (
            not any(
                any("callback" in button or "input" in button for button in row)
                for row in reply_markup
            )
            and not (screen is not None and screen.taps)
            and not ttl
        ):
            logger.debug(
                "Patching form ttl to 10 minutes, because it doesn't contain any"
                " buttons"
            )
            ttl = 10 * 60

        self._units[unit_id] = {
            "type": "form",
            "text": _plain_emoji(text) if decorate else text,
            **({"plain": True} if decorate else {}),
            "buttons": reply_markup,
            "caller": message,
            "chat": None,
            "message_id": None,
            "top_msg_id": utils.get_topic(message),
            "uid": unit_id,
            "on_unload": on_unload,
            "future": Event(),
            **({"photo": photo} if photo else {}),
            **({"video": video} if video else {}),
            **({"gif": gif} if gif else {}),
            **({"location": location} if location else {}),
            **({"audio": audio} if audio else {}),
            **({"location": location} if location else {}),
            **({"perms_map": perms_map} if perms_map else {}),
            **({"message": message} if isinstance(message, Message) else {}),
            **({"force_me": force_me} if force_me else {}),
            **({"disable_security": disable_security} if disable_security else {}),
            **({"ttl": round(time.time()) + (ttl or self._markup_ttl)}),
            **({"always_allow": always_allow} if always_allow else {}),
        }

        if rich_html is not None:
            self._units[unit_id]["rich_source"] = rich_source
            self._units[unit_id]["rich_html"] = rich_html
            if screen is not None:
                self._bind_screen(unit_id, screen, fresh=True)

        async def answer(msg: str):
            nonlocal message
            if isinstance(message, Message):
                await (message.edit if message.out else message.respond)(
                    msg,
                    **({} if message.out else {"reply_to": utils.get_topic(message)}),
                )
            else:
                await self._client.send_message(message, msg)

        invoke_error = None
        invoke_tb = ""
        try:
            m = await self._invoke_unit(unit_id, message, anchor=anchor)
        except ChatSendInlineForbiddenError:
            del self._units[unit_id]
            await answer(self.translator.getkey("inline.inline403"))
            return False
        except Exception as e:
            invoke_error = e
            invoke_tb = traceback.format_exc()
            if self._rich_fallback(unit_id):
                logger.warning("Can't send rich form, sending plain text: %s", e)
                text = self._units[unit_id].get("text", text)
                reply_markup = self._units[unit_id].get("buttons", reply_markup)
                try:
                    m = await self._invoke_unit(unit_id, message, anchor=anchor)
                    invoke_error = None
                except Exception as e2:
                    invoke_error = e2
                    invoke_tb = traceback.format_exc()
        if invoke_error is not None:
            e = invoke_error
            logger.exception("Can't send form")

            del self._units[unit_id]

            if "No query results" in str(e):
                prefix = getattr(self._client, "command_prefix", ".")
                await answer(
                    "🌙 <b>No query results!</b> Make sure you have an inline bot set "
                    "up properly. Use <code>{}ch_legacy_bot</code> or "
                    "<code>{}ch_bot_token</code> to configure it.".format(
                        prefix,
                        prefix,
                    ),
                )

            else:
                await answer(
                    self.translator.getkey("inline.invoke_failed_logs").format(
                        utils.escape_html("\n".join(invoke_tb.splitlines()[1:]))
                    )
                    if self._db.get(main.__name__, "inlinelogs", True)
                    else self.translator.getkey("inline.invoke_failed")
                )

            return False

        try:
            # The future is set when the inline message is sent; without a
            # timeout a failed invoke would hang the form forever
            await asyncio.wait_for(self._units[unit_id]["future"].wait(), timeout=15)
        except asyncio.TimeoutError:
            await self._unload_unit(unit_id)
            return False

        del self._units[unit_id]["future"]

        self._units[unit_id]["chat"] = utils.get_chat_id(m)
        self._units[unit_id]["message_id"] = m.id

        if isinstance(message, Message) and message.out:
            with contextlib.suppress(Exception):
                await message.delete()

        if status_message and not message.out:
            with contextlib.suppress(Exception):
                await status_message.delete()

        inline_message_id = self._units[unit_id].get("inline_message_id")

        msg = InlineMessage(
            inline_manager=self, unit_id=unit_id, inline_message_id=inline_message_id
        )

        if not isinstance(base_reply_markup, Placeholder):
            self._units[unit_id].pop("plain", None)
            if rich_html is not None:
                # A rich screen is re-applied as rich, not as its html text
                success = await msg.edit(
                    rich_html=screen or rich_html,
                    reply_markup=base_reply_markup,
                )
            else:
                success = await msg.edit(text, reply_markup=base_reply_markup)

            if not success:
                with contextlib.suppress(Exception):
                    await msg.delete()
                await self._unload_unit(unit_id)
                return False
        elif decorate:
            asyncio.ensure_future(self._decorate(unit_id, msg, text))

        return msg

    async def _decorate(
        self: "InlineManager",
        unit_id: str,
        msg: InlineMessage,
        text: str,
    ):
        """Puts custom emoji into a form sent without them, unless it was edited since"""
        if (future := self._units.get(unit_id, {}).get("future")) is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(future.wait(), timeout=15)

        unit = self._units.get(unit_id)
        if unit is None or not unit.pop("plain", False):
            return

        unit["text"] = text
        try:
            await msg.edit(text, reply_markup=unit["buttons"])
        except Exception:
            logger.debug("Can't put custom emoji into form %s", unit_id, exc_info=True)

    async def _form_inline_handler(self: "InlineManager", inline_query):
        try:
            query = inline_query.query.split()[0]
        except IndexError:
            return

        for unit in self._units.copy().values():
            for button in utils.array_sum(unit.get("buttons", [])):
                if (
                    "_switch_query" in button
                    and "input" in button
                    and button["_switch_query"] == query
                    and inline_query.from_user.id
                    in [self._me]
                    + self._client.dispatcher.security._owner
                    + unit.get("always_allow", [])
                ):
                    await inline_query.answer(
                        [
                            await inline_query.builder.article(
                                title=button["input"],
                                description=(
                                    self.translator.getkey("inline.keep_id").format(
                                        random.choice(VERIFICATION_EMOJIES)
                                    )
                                ),
                                text=(
                                    "🔄 <b>Transferring value to"
                                    " userbot...</b>\n<i>This message will be"
                                    " deleted automatically</i>"
                                    if inline_query.from_user.id == self._me
                                    else "🔄 <b>Transferring value to userbot...</b>"
                                ),
                                parse_mode="HTML",
                                link_preview=False,
                                id=utils.rand(20),
                            )
                        ],
                        cache_time=60,
                    )
                    return

        if (
            inline_query.query not in self._units
            or self._units[inline_query.query]["type"] != "form"
        ):
            return

        form = self._units[inline_query.query]
        form_text = form.get("text")
        try:
            match True:
                case _ if form.get("rich_html") is not None:
                    # Rich screens are delivered as a rich inline result;
                    # the in-text taps are already registered as callbacks
                    markup = self.generate_markup(inline_query.query)
                    await inline_query.answer(
                        [
                            InputBotInlineResult(
                                id=utils.rand(20),
                                type="article",
                                title="Legacy newgen",
                                send_message=InputBotInlineMessageRichMessage(
                                    rich_message=InputRichMessageHTML(
                                        html=form["rich_html"],
                                    ),
                                    reply_markup=(
                                        ButtonMethods.build_reply_markup(markup)
                                        if markup
                                        else None
                                    ),
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "photo" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.photo(
                                form["photo"],
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "gif" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.document(
                                form["gif"],
                                title="Legacy newgen",
                                type="gif",
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "video" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.document(
                                form["video"],
                                title="Legacy newgen",
                                description="Legacy newgen",
                                type="video",
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                mime_type="video/mp4",
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "file" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.document(
                                form["file"],
                                title="Legacy newgen",
                                description="Legacy newgen",
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                mime_type=form["mime_type"],
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "location" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.article(
                                title="Legacy newgen",
                                geo=InputGeoPoint(
                                    lat=form["location"][0],
                                    long=form["location"][1],
                                ),
                                period=60,
                                id=utils.rand(20),
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "audio" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.document(
                                form["audio"]["url"],
                                title=form["audio"].get("title", "Legacy newgen"),
                                type="audio",
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _:
                    await inline_query.answer(
                        [
                            await inline_query.builder.article(
                                title="Legacy newgen",
                                text=form_text,
                                parse_mode="HTML",
                                link_preview=False,
                                buttons=self.generate_markup(inline_query.query),
                                id=utils.rand(20),
                            )
                        ],
                        cache_time=0,
                    )
        except Exception as e:
            if form["uid"] in self._error_events:
                self._error_events[form["uid"]].set()
                self._error_events[form["uid"]] = e
