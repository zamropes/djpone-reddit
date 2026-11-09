"""Reddit (and 4chan) commands for the djpone IRC bot.

Reddit access goes through the official Data API (oauth.reddit.com) using
application-only OAuth (client_credentials) for an app registered under a
dedicated bot account. Access is read-only: the only Reddit endpoint used is
GET /r/{subreddit}/hot.

Requests are made only when someone in IRC types a command. Listings are
cached in memory for a few minutes, and the bot follows Reddit's
X-Ratelimit-* headers and backs off on HTTP 429.

Configuration (environment variables):
    REDDIT_CLIENT_ID      app id from https://www.reddit.com/prefs/apps
    REDDIT_CLIENT_SECRET  app secret
    REDDIT_USERNAME       the bot account (used in the User-Agent)
"""

import asyncio
import html
import logging
import os
import random
import re
import time

import aiohttp

from .. import httpclient
from ..dispatch import Context, command
from .media import do_image

logger = logging.getLogger("djpone.handlers.reddit_4chan")

CLEAN_TAGS_RE = re.compile("<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});")
SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"
USER_AGENT = f"python:djpone-irc:v1.0 (by /u/{os.environ.get('REDDIT_USERNAME', 'unknown')})"

LISTING_LIMIT = 50
CACHE_TTL = 300  # seconds


class RedditError(Exception):
    """Something the IRC channel should be told about, as a short message."""


class RedditClient:
    def __init__(self):
        self._token = None
        self._token_expires = 0.0
        self._token_lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, list]] = {}
        # Rate-limit state from the X-Ratelimit-* headers of the last response.
        self._remaining: float | None = None
        self._reset_at = 0.0

    async def _get_token(self) -> str:
        async with self._token_lock:
            if self._token and time.monotonic() < self._token_expires - 60:
                return self._token

            client_id = os.environ.get("REDDIT_CLIENT_ID")
            secret = os.environ.get("REDDIT_CLIENT_SECRET")
            if not client_id or not secret:
                raise RedditError("Reddit API credentials are not configured.")

            async with httpclient.session().post(
                TOKEN_URL,
                auth=aiohttp.BasicAuth(client_id, secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": USER_AGENT},
            ) as resp:
                if resp.status != 200:
                    logger.error("Reddit token request failed: HTTP %s", resp.status)
                    raise RedditError("Couldn't log in to Reddit right now.")
                data = await resp.json()

            self._token = data["access_token"]
            self._token_expires = time.monotonic() + data.get("expires_in", 3600)
            return self._token

    def _update_ratelimit(self, headers):
        try:
            self._remaining = float(headers["X-Ratelimit-Remaining"])
            self._reset_at = time.monotonic() + float(headers["X-Ratelimit-Reset"])
        except (KeyError, ValueError):
            pass

    async def _get(self, path: str, params: dict) -> dict:
        if self._remaining is not None and self._remaining < 1 and time.monotonic() < self._reset_at:
            wait = int(self._reset_at - time.monotonic()) + 1
            raise RedditError(f"Reddit rate limit reached, try again in {wait}s.")

        token = await self._get_token()
        async with httpclient.session().get(
            API_BASE + path,
            params=params,
            headers={"Authorization": f"bearer {token}", "User-Agent": USER_AGENT},
            allow_redirects=False,
        ) as resp:
            self._update_ratelimit(resp.headers)

            if resp.status == 200:
                return await resp.json()
            if resp.status == 401:
                self._token = None  # expired or revoked; fetch a new one next time
                raise RedditError("Reddit login expired, try again.")
            if resp.status == 429:
                retry = int(resp.headers.get("Retry-After", "60"))
                self._remaining, self._reset_at = 0, time.monotonic() + retry
                raise RedditError(f"Reddit rate limit reached, try again in {retry}s.")
            if resp.status in (301, 302, 404):
                # Reddit redirects nonexistent subreddits to a search page.
                raise RedditError("That subreddit doesn't exist.")
            if resp.status == 403:
                raise RedditError("That subreddit is private, quarantined, or banned.")

            logger.warning("Reddit returned HTTP %s for %s", resp.status, path)
            raise RedditError("Reddit didn't answer, try again later.")

    async def hot_posts(self, subreddit: str) -> list[dict]:
        if not SUBREDDIT_RE.match(subreddit):
            raise RedditError("That's not a valid subreddit name.")

        key = subreddit.lower()
        cached = self._cache.get(key)
        if cached and time.monotonic() < cached[0]:
            return cached[1]

        data = await self._get(f"/r/{subreddit}/hot", {"limit": LISTING_LIMIT, "raw_json": 1})
        posts = [
            child["data"]
            for child in data.get("data", {}).get("children", [])
            if child.get("kind") == "t3" and not child["data"].get("stickied")
        ]
        self._cache[key] = (time.monotonic() + CACHE_TTL, posts)

        # Drop expired entries so the cache can't grow without bound.
        now = time.monotonic()
        for k in [k for k, (exp, _) in self._cache.items() if exp < now]:
            del self._cache[k]

        return posts


reddit = RedditClient()


def format_post(post: dict) -> str:
    permalink = "https://www.reddit.com" + post["permalink"]
    title = post["title"]
    domain = post["domain"]

    if post.get("is_self"):
        selftext = post.get("selftext", "").replace("\r", "").replace("\n", " ")
        if len(selftext) > 120:
            selftext = selftext[:120] + "..."
        tail = f" - {selftext}" if selftext else ""
        return f"{title} ({domain}) - {permalink}{tail}"

    return f"{title} ({domain}) - {post['url']} - {permalink}"


async def _send_random_post(bot, channel, subreddit: str):
    subreddit = subreddit.strip().removeprefix("/").removeprefix("r/").strip("/")
    try:
        posts = await reddit.hot_posts(subreddit)
    except RedditError as e:
        await bot.send(channel, str(e))
        return
    except Exception:
        logger.exception("Reddit fetch failed for %r", subreddit)
        await bot.send(channel, "Reddit lookup failed.")
        return

    if not posts:
        await bot.send(channel, "That subreddit has no posts.")
        return

    await bot.send(channel, format_post(random.choice(posts)))


@command("$hey")
async def hey_command(ctx: Context):
    await _send_random_post(ctx.bot, ctx.channel, ctx.args)


@command("$sup")
async def sup_command(ctx: Context):
    board = ctx.args.strip("/")
    try:
        data = await httpclient.get_json(f"https://a.4cdn.org/{board}/1.json")
        thread = random.choice(data["threads"])
        post0 = thread["posts"][0]

        title = f"{html.unescape(post0['sub'])} | " if "sub" in post0 else ""
        if "com" in post0:
            cleaned = re.sub(CLEAN_TAGS_RE, "", post0["com"][:250].replace("<br>", " / "))
            text = f"{html.unescape(cleaned)} | "
        else:
            text = ""
        link = f"https://boards.4chan.org/{board}/thread/{post0['no']}"

        try:
            filename = f"{post0['tim']}{post0['ext']}"
            image_url = f"https://i.4cdn.org/{board}/{filename}"
            img_link, _ = await do_image("dj-p0n3", image_url, "")
        except Exception:
            img_link = "No image -"

        await ctx.bot.send(ctx.channel, f"{img_link} {title}{text}{link}")
    except Exception:
        logger.info("$sup 4chan lookup failed for board=%r, falling back to reddit", board)
        await _send_random_post(ctx.bot, ctx.channel, board)
