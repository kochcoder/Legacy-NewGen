# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import atexit
import collections
import contextlib
import copy
import inspect
import os
import tempfile
import threading
import ujson
import logging
import time
import weakref

import typing

from legacytl.errors.rpcerrorlist import ChannelsTooMuchError
from legacytl.tl.types import Message, User, ForumTopic

from . import main, utils
from .pointers import (
    BaseSerializingMiddlewareDict,
    BaseSerializingMiddlewareList,
    NamedTupleMiddlewareDict,
    NamedTupleMiddlewareList,
    PointerDict,
    PointerList,
)
from .tl_cache import CustomTelegramClient
from .types import JSONSerializable

__all__ = [
    "Database",
    "PointerList",
    "PointerDict",
    "NamedTupleMiddlewareDict",
    "NamedTupleMiddlewareList",
    "BaseSerializingMiddlewareDict",
    "BaseSerializingMiddlewareList",
]

logger = logging.getLogger(__name__)

# Owners in this set can only be written by the modules, explicitly allowed
# in `_DB_ALLOWED_WRITERS`. Both are empty by default, so this protection is
# opt-in for core code
_DB_PROTECTED_OWNERS = set()
_DB_ALLOWED_WRITERS = set()
# Writes are coalesced: a burst of `set()` calls ends up in a single fsync
SAVE_DELAY = 0.5
# Databases (being dicts) aren't hashable, so instances are tracked by id()
_INSTANCES: "weakref.WeakValueDictionary[int, Database]" = (
    weakref.WeakValueDictionary()
)


def _register_protected_owner(owner: str, *allowed_writers: str) -> None:
    """Registers a db owner, which can only be written by allowed modules"""
    _DB_PROTECTED_OWNERS.add(owner)
    _DB_ALLOWED_WRITERS.update(allowed_writers)


def flush_all():
    """Synchronously writes pending changes of every database"""
    for db in list(_INSTANCES.values()):
        try:
            db.flush()
        except Exception:
            logger.exception("Failed to flush database")


atexit.register(flush_all)


class NoAssetsChannel(Exception):
    """Raised when trying to read/store asset with no asset channel present"""


class Database(dict):
    def __init__(self, client: CustomTelegramClient):
        super().__init__()
        self._client: CustomTelegramClient = client
        self._next_revision_call: int = 0
        self._revisions: typing.List[dict] = []
        self._assets_topic: typing.Optional[ForumTopic] = None
        self._me: User = None
        self._saving_task: asyncio.Future = None
        self._dirty: bool = False
        self._write_lock = threading.Lock()
        self._generation: int = 0
        self._written_generation: int = 0
        self._last_saved: typing.Optional[bytes] = None
        _INSTANCES[id(self)] = self

    def __repr__(self):
        return object.__repr__(self)

    async def init(self):
        """Asynchronous initialization unit"""
        self._db_file = main.BASE_PATH / f"config-{self._client.tg_id}.json"
        self.read()

        # Channel/topic resolution involves network and flood-protection
        # sleeps — it must not block module loading. Consumers either use
        # `utils.wait_for_content_channel` (polls the db) or assets, which
        # are only touched long after boot
        self._content_channel_task = asyncio.ensure_future(self._init_channel())

    async def _init_channel(self):
        """Background content channel + assets topic resolution"""
        try:
            self._content_channel, _ = await utils.asset_channel(
                client=self._client,
                title='legacy-userbot',
                description='🌙 Content related to legacy will be here',
                silent=True,
                avatar=f"{main.AVATAR_PATH}",
                forum=True,
                hide_general=True,
                _folder='legacy',
                _cached_id=self.get("legacy.forums", "channel_id"),
            )

            self.set("legacy.forums", "channel_id", self._content_channel.id)

            await utils.fw_protect()

            self._assets_topic = await utils.asset_forum_topic(
                client=self._client,
                db=self,
                peer=self._content_channel.id,
                title="Assets",
                description="🌆 Your Legacy assets will be stored here",
                icon_emoji_id=5805550320985578625,
            )
        except Exception:
            self._assets_topic = None
            logger.error(
                "Can't find and/or create assets topic\n"
                "This may cause several consequences, such as:\n"
                "- Non working assets feature (e.g. notes)\n\n"
            )

    def read(self):
        """Read database and stores it in self"""
        try:
            self._update_from_read(ujson.loads(self._db_file.read_text()))
        except ValueError:
            # Keep the broken file, otherwise the next save would overwrite
            # whatever could still be recovered from it
            backup = self._db_file.with_name(
                f"{self._db_file.name}.corrupt-{int(time.time())}"
            )
            try:
                os.replace(self._db_file, backup)
            except OSError:
                logger.exception("Can't move corrupted database aside")
                backup = None

            logger.error(
                "Database %s is corrupted! Starting with an empty one, the"
                " broken file was saved to %s",
                self._db_file,
                backup or "<nowhere>",
            )
        except FileNotFoundError:
            logger.debug("Database file not found, creating new one...")

    def _update_from_read(self, items: dict) -> None:
        """Update DB from persisted storage without write-protection checks"""
        super().update(items)

    def process_db_autofix(self, db: dict) -> bool:
        if not utils.is_serializable(db):
            return False

        for key, value in db.copy().items():
            if not isinstance(key, (str, int)):
                logger.warning(
                    "DbAutoFix: Dropped key %s, because it is not string or int",
                    key,
                )
                continue

            if not isinstance(value, dict):
                # If value is not a dict (module values), drop it,
                # otherwise it may cause problems
                del db[key]
                logger.warning(
                    "DbAutoFix: Dropped key %s, because it is non-dict, but %s",
                    key,
                    type(value),
                )
                continue

            for subkey in value:
                if not isinstance(subkey, (str, int)):
                    del db[key][subkey]
                    logger.warning(
                        (
                            "DbAutoFix: Dropped subkey %s of db key %s, because it is"
                            " not string or int"
                        ),
                        subkey,
                        key,
                    )
                    continue

        return True

    def _prepare_save(self) -> typing.Optional[bytes]:
        """Serializes the database, `None` if nothing changed since last save"""
        if not self.process_db_autofix(self):
            try:
                rev = self._revisions.pop()
                while not self.process_db_autofix(rev):
                    rev = self._revisions.pop()
            except IndexError:
                raise RuntimeError(
                    "Can't find revision to restore broken database from "
                    "database is most likely broken and will lead to problems, "
                    "so its save is forbidden."
                )

            self.clear()
            self._update_from_read(rev)

            raise RuntimeError(
                "Rewriting database to the last revision because new one destructed it"
            )

        data = ujson.dumps(dict(self), indent=4).encode()

        # Autosave runs every few seconds — writing an unchanged database
        # would be a pointless fsync, and on an SD card a costly one
        if data == self._last_saved:
            return None

        if self._next_revision_call < time.time():
            # Deep copy, so later in-place changes don't leak into the revision
            self._revisions += [copy.deepcopy(dict(self))]
            self._next_revision_call = time.time() + 3

        while len(self._revisions) > 15:
            self._revisions.pop(0)

        return data

    def _write(self, data: bytes, generation: int) -> bool:
        """Atomically writes `data` to disk. Safe to call from a thread"""
        with self._write_lock:
            # A newer state is already on disk
            if generation < self._written_generation:
                return True

            try:
                fd, tmp_path = tempfile.mkstemp(
                    dir=self._db_file.parent,
                    suffix=".tmp",
                )
                try:
                    try:
                        os.write(fd, data)
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                    os.replace(tmp_path, self._db_file)
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp_path)
                    raise
            except Exception:
                logger.exception("Database save failed!")
                return False

            self._written_generation = generation
            self._last_saved = data
            return True

    def save(self) -> bool:
        """Save database immediately"""
        self._dirty = False
        data = self._prepare_save()
        if data is None:
            return True

        self._generation += 1
        return self._write(data, self._generation)

    def flush(self) -> bool:
        """Write pending changes, if any"""
        if not hasattr(self, "_db_file"):
            return True

        # A background write may still be in flight, redo it synchronously
        if not self._dirty and self._written_generation >= self._generation:
            return True

        return self.save()

    def _schedule_save(self) -> bool:
        self._dirty = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return self.save()

        if self._saving_task is None or self._saving_task.done():
            self._saving_task = loop.create_task(self._delayed_save())

        return True

    async def _delayed_save(self):
        try:
            while self._dirty:
                await asyncio.sleep(SAVE_DELAY)
                if not self._dirty:
                    break

                self._dirty = False
                try:
                    data = self._prepare_save()
                except Exception:
                    logger.exception("Database save failed!")
                    continue

                if data is None:
                    continue

                self._generation += 1
                await asyncio.to_thread(self._write, data, self._generation)
        except asyncio.CancelledError:
            self.flush()
            raise

    async def store_asset(self, message: Message) -> int:
        """
        Save assets
        returns asset_id as integer
        """
        if not self._assets_topic:
            raise NoAssetsChannel("Tried to save asset to non-existing asset topic")

        return (
            (await self._client.send_message(self._content_channel.id, message, reply_to=self._assets_topic.id)).id
            if isinstance(message, Message)
            else (
                await self._client.send_message(
                    self._content_channel.id,
                    file=message,
                    force_document=True,
                    message_thread_id=self._assets_topic.id
                )
            ).id
        )

    async def fetch_asset(self, asset_id: int) -> typing.Optional[Message]:
        """Fetch previously saved asset by its asset_id"""
        if not self._assets_topic:
            raise NoAssetsChannel(
                "Tried to fetch asset from non-existing asset topic"
            )

        asset = await self._client.get_messages(self._content_channel.id, ids=[asset_id])

        return asset[0] if asset else None

    def get(
        self,
        owner: str,
        key: str,
        default: typing.Optional[JSONSerializable] = None,
    ) -> JSONSerializable:
        """Get database key"""
        try:
            return self[owner][key]
        except KeyError:
            return default

    def set(self, owner: str, key: str, value: JSONSerializable) -> bool:
        """Set database key"""
        if not utils.is_serializable(owner):
            raise RuntimeError(
                "Attempted to write object to "
                f"{owner=} ({type(owner)=}) of database. It is not "
                "JSON-serializable key which will cause errors"
            )

        if not utils.is_serializable(key):
            raise RuntimeError(
                "Attempted to write object to "
                f"{key=} ({type(key)=}) of database. It is not "
                "JSON-serializable key which will cause errors"
            )

        if not utils.is_serializable(value):
            raise RuntimeError(
                "Attempted to write object of "
                f"{key=} ({type(value)=}) to database. It is not "
                "JSON-serializable value which will cause errors"
            )

        super().setdefault(owner, {})[key] = value
        return self._schedule_save()

    def pointer(
        self,
        owner: str,
        key: str,
        default: typing.Optional[JSONSerializable] = None,
        item_type: typing.Optional[typing.Any] = None,
    ) -> typing.Union[JSONSerializable, PointerList, PointerDict]:
        """Get a pointer to database key"""
        value = self.get(owner, key, default)
        if isinstance(value, collections.abc.Hashable) and not isinstance(
            value, (list, dict)
        ):
            return value
        mapping = {
            list: PointerList,
            dict: PointerDict,
        }

        pointer_constructor = next(
            (pointer for type_, pointer in mapping.items() if isinstance(value, type_)),
            None,
        )

        if (current_value := self.get(owner, key, None)) and type(
            current_value
        ) is not type(default):
            raise ValueError(
                f"Can't switch the type of pointer in database (current: {type(current_value)}, requested: {type(default)})"
            )

        if pointer_constructor is None:
            raise ValueError(
                f"Pointer for type {type(value).__name__} is not implemented"
            )

        if item_type is not None:
            if isinstance(value, list):
                for item in self.get(owner, key, default):
                    if not isinstance(item, dict):
                        raise ValueError(
                            "Item type can only be specified for dedicated keys and"
                            " can't be mixed with other ones"
                        )

                return NamedTupleMiddlewareList(
                    pointer_constructor(self, owner, key, default),
                    item_type,
                )
            if isinstance(value, dict):
                for item in self.get(owner, key, default).values():
                    if not isinstance(item, dict):
                        raise ValueError(
                            "Item type can only be specified for dedicated keys and"
                            " can't be mixed with other ones"
                        )

                return NamedTupleMiddlewareDict(
                    pointer_constructor(self, owner, key, default),
                    item_type,
                )

        return pointer_constructor(self, owner, key, default)

    def __setitem__(self, owner: str, value: JSONSerializable) -> None:
        if owner in _DB_PROTECTED_OWNERS:
            caller = self._get_write_caller()
            if caller not in _DB_ALLOWED_WRITERS:
                self._reject_write(owner, "<dict>", caller)

        if not utils.is_serializable(owner):
            raise RuntimeError(
                "Attempted to write object to "
                f"{owner=} ({type(owner)=}) of database. It is not "
                "JSON-serializable key which will cause errors"
            )

        if not utils.is_serializable(value):
            raise RuntimeError(
                "Attempted to write object to "
                f"{value=} ({type(value)=}) of database. It is not "
                "JSON-serializable value which will cause errors"
            )

        super().__setitem__(owner, value)
        self._schedule_save()

    def update(self, *args, **kwargs) -> None:
        items = dict(*args, **kwargs)
        for owner in items.keys():
            if owner in _DB_PROTECTED_OWNERS:
                caller = self._get_write_caller()
                if caller not in _DB_ALLOWED_WRITERS:
                    self._reject_write(owner, "<dict>", caller)

        super().update(items)
        self._schedule_save()

    @staticmethod
    def _get_write_caller() -> typing.Optional[str]:
        # Walked by hand: inspect.stack() reads the source of every frame,
        # which costs some 350 times more than the name we're after
        frame = inspect.currentframe()
        while frame:
            mod = frame.f_globals.get("__name__", None)
            if mod and mod != __name__ and mod != f"{__package__}.pointers":
                return mod

            frame = frame.f_back

        return None

    @staticmethod
    def _reject_write(owner: str, key: str, caller: typing.Optional[str]):
        logger.warning(
            "Blocked db write to protected owner=%s key=%s from %s",
            owner,
            key,
            caller or "<unknown>",
        )
