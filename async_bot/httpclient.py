import aiohttp

from . import config

_session: aiohttp.ClientSession | None = None


async def startup():
    global _session
    _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=config.HTTP_TIMEOUT_SECONDS))


async def shutdown():
    if _session is not None:
        await _session.close()


def session() -> aiohttp.ClientSession:
    if _session is None:
        raise RuntimeError("httpclient.startup() must run before any request is made")
    return _session


async def get_json(url, **kwargs):
    async with session().get(url, **kwargs) as resp:
        # content_type=None: several of the third-party APIs this bot calls
        # (e.g. labs.bible.org) serve valid JSON under a non-JSON mimetype
        # like application/x-javascript, which aiohttp otherwise rejects.
        return await resp.json(content_type=None)


async def get_text(url, **kwargs):
    async with session().get(url, **kwargs) as resp:
        return await resp.text()


async def get_bytes(url, **kwargs):
    async with session().get(url, **kwargs) as resp:
        return await resp.read()
