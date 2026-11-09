from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List

from . import config


@dataclass
class Context:
    bot: "object"
    channel: str
    sender: str
    args: str

    @property
    def nick(self) -> str:
        """Sender nick as djpone2.py's textNick: nicks starting with "{" are
        all treated as "crank". Use this for storage/lookup, sender for replies."""
        return "crank" if self.sender.startswith("{") else self.sender


Handler = Callable[[Context], Awaitable[None]]

_handlers: Dict[str, Handler] = {}
_listeners: List[Handler] = []


def command(name: str):
    """Decorator: registers an async handler under a '$name' command (or a
    '!name' one, e.g. "!search" - djpone2.py's one non-"$" command, only
    recognized in #titties; see irc.py's dispatch gate)."""
    full_name = name if name[:1] in (config.COMMAND_PREFIX, "!") else f"{config.COMMAND_PREFIX}{name}"

    def register(fn: Handler) -> Handler:
        if full_name in _handlers:
            raise ValueError(f"Duplicate command registration: {full_name}")
        _handlers[full_name] = fn
        return fn

    return register


def listener(fn: Handler) -> Handler:
    """Decorator: registers an async handler that runs on every channel
    message (commands included). ctx.args holds the full message text."""
    _listeners.append(fn)
    return fn


def listeners() -> List[Handler]:
    return list(_listeners)


def get(name: str) -> Handler | None:
    return _handlers.get(name)


def match(message: str):
    """Finds the registered command (e.g. "$g", but also multi-word ones
    like "$first mention" or "$fun milo") that message starts with, longest
    name first so "$first mention" wins over a hypothetical bare "$first".
    Returns (handler, args) or (None, None)."""
    for name in sorted(_handlers, key=len, reverse=True):
        if message == name:
            return _handlers[name], ""
        if message.startswith(name + " "):
            return _handlers[name], message[len(name) + 1:]
    return None, None


def all_commands():
    return sorted(_handlers.keys())
