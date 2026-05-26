# Playtomic iOS Shortcuts

Auto-generated iOS Shortcuts for the Playtomic padel-booking app:

1. **Playtomic Login** — asks once for your Playtomic email + password, exchanges them
   for an access + refresh token pair, and saves the JSON to
   `iCloud Drive › Shortcuts › playtomic-tokens.json`.
2. **Padel Door Code** — reads the tokens file, refreshes the access token (and
   stores the rotated tokens back), fetches `/v1/matches?user_id=me`, finds today's
   match, shows the door code in a notification, and copies it to the clipboard.

Trigger #2 with a Personal Automation (`Arrive at PADALL Haverhill` etc.) for fully
hands-free use.

## Why this pipeline exists

iOS 15+ requires every `.shortcut` file to be Apple-signed before it can be
imported. The signing tool only exists on macOS. This repo builds the unsigned
plists from Python (`build.py`), then a **macOS GitHub Actions runner** signs
them with `shortcuts sign --mode anyone` and commits the signed copies to
[`signed/`](signed/).

See `signed/INSTALL.md` (created by CI on the first push) for tap-to-install links.

## Repository layout

```
.
├── build_shortcut.py   # generic plist builder library (UUID refs, attachments, etc.)
├── build.py            # produces playtomic-login.shortcut & padel-code.shortcut
├── .github/workflows/
│   └── sign.yml        # macOS runner: sign + commit back to signed/
└── signed/             # CI-produced, signed .shortcut files (committed automatically)
    ├── playtomic-login.shortcut
    ├── padel-code.shortcut
    └── INSTALL.md      # tap-to-install URLs
```

## One-time iPhone prep

1. Open the **Shortcuts** app once (so the toggle ungrays).
2. **Settings → Shortcuts → Allow Untrusted Shortcuts** → toggle ON (enters passcode).

## Install on iPhone

1. Push this repo (CI runs in ~2 min).
2. On your **iPhone**, open `signed/INSTALL.md` on github.com — tap each install link.
3. Run **Playtomic Login** once, type your credentials. You should see a `Logged in ✓` notification.
4. Run **Padel Door Code** to verify. (If you have a booking today, the code pops up.)
5. Set up the location automation:
   - Shortcuts app → **Automation** tab → `+` → **Create Personal Automation**
   - **Arrive** → choose `PADALL Haverhill` (or pin location 52.087226, 0.447905, radius 150 m)
   - **Run Shortcut** → pick `Padel Door Code`
   - Toggle **Ask Before Running** OFF → Done.

## Local dev

Build the unsigned files locally for inspection:

```bash
python3 build.py
# Produces playtomic-login.shortcut and padel-code.shortcut as binary plists.
# Convert to XML to read them:
plutil -convert xml1 -o - playtomic-login.shortcut | less
```

Signing requires macOS:

```bash
shortcuts sign --mode anyone -i playtomic-login.shortcut -o signed/playtomic-login.shortcut
shortcuts sign --mode anyone -i padel-code.shortcut       -o signed/padel-code.shortcut
```

## Tweaking

* **Different club / sport:** the matches endpoint already filters to *your*
  matches; no change needed. To support multiple users, edit the login shortcut to
  prompt for the iCloud filename suffix.
* **"Next match in N hours" instead of "today":** in `build.py`, swap the
  `if_contains(..., compare=named_var_attachment("today"))` block for a date-math
  comparison using `time_between_dates`. The `build_shortcut.py` library has the
  helper. The current "contains today's yyyy-MM-dd" check picks any match starting
  today; if you book two on the same day you'll get whichever the API returns last.
* **Send to a different sink** (Slack/Discord/ntfy): replace the `show_notification`
  + `copy_to_clipboard` actions in `make_padel_code` with another `http_request` to
  your webhook URL.

## Caveats

* Plist schema is community-reverse-engineered. If iOS rejects an import with
  "Shortcut Can't Be Opened", the most likely culprits are documented in
  `/tmp/playtomic/shortcut-research.md` §8 — usually a missing parameter envelope
  or a `WFSerializationType` mismatch. The fix is to compare the generated XML
  against a known-good shortcut exported from the Shortcuts app.
* The Playtomic API responses are not officially documented; field names could
  change without notice. The script relies on `merchant_access_code.code` being a
  string and `start_date` being an ISO-8601 timestamp.
