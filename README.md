# djpone – Reddit module

djpone is a personal, non-commercial IRC bot that has run for years in a small private IRC channel of about a dozen regular users. This repo contains the part of the bot that reads from Reddit. The rest of the bot (IRC connection, database, other commands) is left out because it has nothing to do with Reddit.

## What it does on Reddit

The bot only reads from Reddit. It never posts, comments, votes, sends messages, edits profiles or moderates.

It uses the official Data API (`oauth.reddit.com`) with application-only OAuth, for an app registered under a dedicated bot account. **The only endpoint it calls is `GET /r/{subreddit}/hot`.**

| IRC command | Reddit request | What the bot says in chat |
|---|---|---|
| `$hey <subreddit>` | `GET /r/{subreddit}/hot?limit=50` | one random post: title, domain, link, and reddit.com permalink |
| `$sup <board>` | a 4chan board; if that board doesn't exist, the same request as `$hey` | as above |

Example:

```
<user>   $hey aww
<djpone> Sleepy pup (i.redd.it) - https://i.redd.it/x.jpg - https://www.reddit.com/r/aww/comments/abc/sleepy_pup/
```

Every reply includes the reddit.com permalink, so people click through to Reddit to read, vote and comment.

## Volume, rate limits and data handling

- Requests happen only when a person in IRC types a command, at most a few dozen a day. There are no background jobs, crawling or bulk collection.
- Each subreddit's listing is cached in memory for 5 minutes, so repeated commands don't hit the API again.
- The bot follows the `X-Ratelimit-*` headers and backs off on HTTP 429 (`Retry-After`) without retrying.
- It sends a descriptive User-Agent: `python:djpone-irc:v1.0 (by /u/zamropes)`.
- Nothing is stored beyond that short in-memory cache. No data is used for AI/ML training, sold, shared, or collected into datasets.

## Configuration

Set these environment variables:

```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=zamropes   # the dedicated bot account
```

## Files

- `async_bot/handlers/reddit_4chan.py`: Reddit API client and the `$hey` / `$sup` commands
- `async_bot/httpclient.py`: the shared HTTP session
- `async_bot/dispatch.py`: command registration (how `$hey` etc. get routed)
