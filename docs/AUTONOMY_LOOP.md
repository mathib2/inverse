# The crew works on itself: Tinker, the Live tab, and your phone

From 25 October the crew has a ninth member, **Tinker**, whose standing job is the crew's own code and knowledge, around the clock,
with nobody asking. It runs in a sandbox copy of the repository (`~/inverse-lab` on the workstation), never in the live checkout,
and a change reaches the live system only through five gates: the test suite, the agent's probe, Sentinel's review, Vera's vote
and a veto window announced on your phone (the last section).

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
5. **Engineer.** The item names the file and the region (`PLACES` in `scripts/tinker.py`: Vera's rules in `critic.py`, Atlas's
   guard in `lead.py`, Scout's column rules in `experts.py`, and so on); the task shows those sixty lines, and Tinker makes one
   `edit_file` change there (an exact replacement), then `run_tests`. It cannot create files or write notes: the first three
   cycles, given `write_file` and a whole repository to search, produced `research.txt`, `code.txt` and `production-guide.md`
   instead of code. "No safe change: why" is an accepted answer and becomes a lesson.
6. **Verify by code, not by the model.** The whole test suite must pass; then the probe of the agent the item concerns runs, and the
   change is kept only if the agent's mark did not drop. Anything else is reverted and recorded as a lesson.
7. **Ask the council, then wait for your veto.** A surviving change is committed on a branch `auto/<date>-<item>`, pushed, and
   put to the council as described under "Approving" below; the chat and your phone get the compare link.

Everything is in the chat (`state/chat.jsonl`, the **Live** tab) and in `state/tinker.json` (`inverse-tinker status`). Start,
stop and read it with `~/.local/bin/inverse-tinker start|stop|status|log|once`. The interval is `TINKER_INTERVAL` (default 30
minutes); a cycle is bounded to 30 model calls and 25 minutes.

## What it will and will not do

A 4B model is a weak engineer. Expect most cycles to end in "tests failed; reverted" or "no change made", a few in a real small
fix, and the research notes to be the most useful output early on. That is why the gate is code: the tests, the probe, and your
merge. Tinker cannot change the live checkout, the model server, the data platform, `.env`, or anything outside the sandbox; it
cannot push to the base branch except through the council's merge described below, and it cannot skip the tests or the probe.
Those limits are what make "no limits" on its research and its attempts safe.

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
| **SMS, one a day** | `TEXTBELT_TO` = your number with the country code; no account (Textbelt's public key allows one free text a day per number). **Not for US numbers**: Textbelt answers "free SMS are disabled for this country"; the channel stays for other countries | a real text message for what needs a person: an approval, a merge |
| **SMS, unlimited** | your carrier's email gateway in `NOTIFY_SMS_TO` (Verizon `number@vtext.com`, AT&T `number@txt.att.net`, T-Mobile `number@tmomail.net`) and an SMTP account in `SMTP_HOST/PORT/USER/PASS` | a real text message, up to 160 characters |

Phone **calls** are not free to place by software: every voice API (Twilio and the like) bills per call after a trial. The ntfy
priority-5 alert is the free equivalent: it overrides silent mode on Android and repeats until acknowledged. If you want real calls,
a Twilio trial account with your number verified works for the trial credit; the hook is one function in `notify.py`.

Test any channel from the workstation: `PYTHONPATH=core .venv/bin/python scripts/notify.py "hello from the crew" --urgent`.

## Approving: the council, then you

With `TINKER_AUTOMERGE=council` (the default) a change that passed the tests and the probe goes to the council before it is merged:
Sentinel reviews the changed files for weaknesses on the branch, and Vera votes on the diff with the test and probe results in front
of her. A high-severity finding or a "no" leaves the change as a branch for you. A "yes" starts a veto window (`TINKER_VETO_MINUTES`,
default 30): your phone gets the alert with the compare link, and in the Live tab you can write `veto auto/...` to stop it or
`approve auto/...` to merge at once. When the window closes with no veto, Tinker waits for a quiet machine, merges the branch into
the base branch with a merge commit, pushes, and runs `deploy-live`; the page and Warden restart on the new code and you get a second
alert saying so. With `TINKER_AUTOMERGE=human` nothing is merged by the crew: every change waits for you.

So yes, the crew upgrades its own code on its own, on the council's say-so, with four gates in front of the live system: the test
suite, the agent's probe, Sentinel's review and Vera's vote, and one behind them: your veto. A branch you do not want is simply left
alone; Tinker moves on to the next item and comes back to that one last.
