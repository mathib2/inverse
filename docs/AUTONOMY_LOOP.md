# The crew works on itself: Tinker, the Live tab, and your phone

From 25 October the crew has a ninth member, **Tinker**, whose standing job is the crew's own code and knowledge, around the clock,
with nobody asking. It runs in a sandbox copy of the repository (`~/inverse-lab` on the workstation), never in the live checkout,
and the only thing it cannot do alone is merge: that needs a person, who is told on the phone.

## What a cycle does

1. **Wait for a quiet machine.** If Warden or the crew page is running a mission, Tinker waits (`state/current.json`,
   `state/ui_mission.json` on the live checkout).
2. **Start clean.** The sandbox is reset to the base branch (`TINKER_BRANCH`, default `m4-sindyc`); a failed experiment never
   carries over.
3. **Pick the next item.** The numbered list under "What they must improve" in `docs/AGENT_REPORT.md`, plus every probe that failed
   last time (`docs/evidence/probe/`), least recently tried first. An item awaiting your approval is skipped.
4. **Research.** Tinker searches the web (`web_search`, DuckDuckGo, no account) and reads at most two pages (`fetch_url`), through
   the same injection guard that protects the crew from maintenance notes, and writes a note with two ideas and their sources. The
   note goes to the chat and to shared memory as a finding with the lowest trust (source `web`).
5. **Engineer.** With `grep`, `read_file`, `edit_file` (exact replacement), `write_file` and `run_tests`, all confined to the
   sandbox, it makes the smallest change it can for the item, in one or two files.
6. **Verify by code, not by the model.** The whole test suite must pass; then the probe of the agent the item concerns runs, and the
   change is kept only if the agent's mark did not drop. Anything else is reverted and recorded as a lesson.
7. **Ask.** A surviving change is committed on a branch `auto/<date>-<item>`, pushed, filed with the council as a code proposal (a
   task card), written to the chat as an alert, and sent to your phone with the compare link. You approve by merging; `deploy-live`
   takes it live.

Everything is in the chat (`state/chat.jsonl`, the **Live** tab) and in `state/tinker.json` (`inverse-tinker status`). Start,
stop and read it with `~/.local/bin/inverse-tinker start|stop|status|log|once`. The interval is `TINKER_INTERVAL` (default 30
minutes); a cycle is bounded to 30 model calls and 25 minutes.

## What it will and will not do

A 4B model is a weak engineer. Expect most cycles to end in "tests failed; reverted" or "no change made", a few in a real small
fix, and the research notes to be the most useful output early on. That is why the gate is code: the tests, the probe, and your
merge. Tinker cannot change the live checkout, the model server, the data platform, `.env`, or anything outside the sandbox; it
cannot push to the base branch; it cannot merge. Those limits are what make "no limits" on its research and its attempts safe.

## The Live tab

The **Live** mode of the page shows one chat for everything: the agents' messages inside missions (results, reviews, questions and
answers), Warden's log, the council's sessions and Tinker's research, changes and alerts, newest at the bottom, refreshed every
three seconds, with a filter per source. The box under it sends a goal to Warden, which starts a mission within a minute, and your
message appears in the chat as yours.

## Your phone, for free

`core/inverse_core/notify.py` sends an alert on every channel that `.env` names; none costs anything:

| channel | what you need | what you get |
|---|---|---|
| **ntfy** (recommended) | the ntfy app (Android, iPhone), subscribed to the topic in `NTFY_TOPIC`; no account | a push notification; an approval request uses priority 5, which rings and stays on screen like a call |
| **Telegram** | a bot token from @BotFather and your chat id in `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | a message from the bot |
| **SMS** | your carrier's email gateway in `NOTIFY_SMS_TO` (Verizon `number@vtext.com`, AT&T `number@txt.att.net`, T-Mobile `number@tmomail.net`) and an SMTP account in `SMTP_HOST/PORT/USER/PASS` | a real text message, up to 160 characters |

Phone **calls** are not free to place by software: every voice API (Twilio and the like) bills per call after a trial. The ntfy
priority-5 alert is the free equivalent: it overrides silent mode on Android and repeats until acknowledged. If you want real calls,
a Twilio trial account with your number verified works for the trial credit; the hook is one function in `notify.py`.

Test any channel from the workstation: `PYTHONPATH=core .venv/bin/python scripts/notify.py "hello from the crew" --urgent`.

## Approving

An alert names the item, the files and the test and probe results, with a link to the branch comparison on GitHub. Merge it there
(or `git merge auto/...` on the base branch), then run `deploy-live`; the next Tinker cycle starts from the merged code. A branch
you do not want is simply left alone; Tinker moves on to the next item and comes back to that one last.
