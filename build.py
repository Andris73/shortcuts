#!/usr/bin/env python3
"""
build.py — generate the Playtomic iOS Shortcuts as unsigned .shortcut files.

Produces two files in the current directory:

  * playtomic-login.shortcut  — asks for email + password, exchanges for tokens,
                                writes /Shortcuts/playtomic-tokens.json to iCloud.
  * padel-code.shortcut       — reads the tokens file, refreshes the access_token
                                (and saves the rotated tokens back), fetches your
                                matches, picks today's, shows the door code in a
                                notification and copies it to the clipboard.

Both must be Apple-signed before iOS 15+ will accept them:
    shortcuts sign --mode anyone -i playtomic-login.shortcut -o signed/playtomic-login.shortcut
    shortcuts sign --mode anyone -i padel-code.shortcut       -o signed/padel-code.shortcut
"""
from __future__ import annotations

import plistlib
import re
from pathlib import Path

from build_shortcut import (
    OBJ_REPL, new_uuid,
    text_value, attachment, var_ref,
    ask_for_input, ask_for_secure_input,
    set_variable, get_variable,
    get_dictionary_from_input, get_dictionary_value,
    save_file_to_icloud, get_file_from_icloud,
    show_notification, copy_to_clipboard,
    repeat_each,
    build_shortcut,
)

# ─── extension helpers (variable refs in values, header values, templates) ──

def named_var_attachment(name: str) -> dict:
    """Bare attachment dict for a named variable (created by Set Variable / Ask)."""
    return {"Type": "Variable", "VariableName": name}


def text_template(template: str, var_attachments: dict[str, dict]) -> dict:
    """`${name}` placeholders → OBJ_REPL + attachmentsByRange."""
    pieces: list[str] = []
    attachments: dict[str, dict] = {}
    last = 0
    for m in re.finditer(r"\$\{([^}]+)\}", template):
        pieces.append(template[last:m.start()])
        pos = sum(len(s) for s in pieces)
        pieces.append(OBJ_REPL)
        name = m.group(1)
        if name not in var_attachments:
            raise KeyError(f"text_template: missing attachment for ${{{name}}}")
        attachments[f"{{{pos}, 1}}"] = var_attachments[name]
        last = m.end()
    pieces.append(template[last:])
    return text_value("".join(pieces), attachments)


def text_action(template: str, vars: dict[str, dict] | None = None,
                uuid_str: str | None = None) -> dict:
    """Text action with optional `${name}` variable embeddings."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFTextActionText": text_template(template, vars or {}),
        },
    }


def _wrap_value(v) -> dict:
    """Accepts str | attachment-dict | (template, vars) tuple. Returns WFTextTokenString."""
    if isinstance(v, str):
        return text_value(v)
    if isinstance(v, tuple):
        return text_template(v[0], v[1])
    return text_value(OBJ_REPL, attachments={"{0, 1}": v})


def dictionary(entries: list[tuple[str, object]], uuid_str: str | None = None) -> dict:
    items = [
        {"WFItemType": 0, "WFKey": text_value(k), "WFValue": _wrap_value(v)}
        for k, v in entries
    ]
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.dictionary",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFItems": {
                "Value": {"WFDictionaryFieldValueItems": items},
                "WFSerializationType": "WFDictionaryFieldValue",
            },
        },
    }


def http_request(url, method: str = "GET",
                 headers: dict[str, object] | None = None,
                 body_dict_uuid: str | None = None,
                 uuid_str: str | None = None) -> dict:
    params: dict = {
        "UUID": uuid_str or new_uuid(),
        "WFHTTPMethod": method,
        "WFURL": _wrap_value(url),
    }
    if headers:
        items = [
            {"WFItemType": 0, "WFKey": text_value(k), "WFValue": _wrap_value(v)}
            for k, v in headers.items()
        ]
        params["WFHTTPHeaders"] = {
            "Value": {"WFDictionaryFieldValueItems": items},
            "WFSerializationType": "WFDictionaryFieldValue",
        }
    if body_dict_uuid and method in ("POST", "PUT", "PATCH"):
        params["WFHTTPBodyType"] = "JSON"
        params["WFJSONValues"] = var_ref(body_dict_uuid, "Dictionary")
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
        "WFWorkflowActionParameters": params,
    }


def current_date(uuid_str: str | None = None) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.date",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFDateActionMode": "Current Date",
        },
    }


def format_date(source_uuid: str, fmt: str = "yyyy-MM-dd",
                uuid_str: str | None = None) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.format.date",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFInput": var_ref(source_uuid, "Date"),
            "WFDateFormatStyle": "Custom",
            "WFDateFormat": text_value(fmt),
        },
    }


def if_contains(input_attachment, compare,
                group_uuid: str | None = None) -> tuple[dict, dict]:
    """If (no Otherwise) — 'input contains compare'. Returns (if_start, end_if)."""
    g = group_uuid or new_uuid()
    wf_input = _wrap_value(input_attachment)
    if_start = {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "GroupingIdentifier": g,
            "WFControlFlowMode": 0,
            "WFInput": wf_input,
            "WFCondition": 4,                       # 4 = Contains
            "WFConditionalActionString": _wrap_value(compare),
        },
    }
    end_if = {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "GroupingIdentifier": g,
            "WFControlFlowMode": 2,
            "UUID": new_uuid(),
        },
    }
    return if_start, end_if


# ─── constants ───────────────────────────────────────────────────────────────

TOKENS_PATH = "/Shortcuts/playtomic-tokens.json"

HEADERS_BASE = {
    "Accept": "application/json",
    "User-Agent": "iOS 18.3.1",
    "X-Requested-With": "com.playtomic.app 6.13.0",
}
HEADERS_JSON = {**HEADERS_BASE, "Content-Type": "application/json"}


# ─── shortcut 1: Playtomic Login ─────────────────────────────────────────────

def make_login() -> dict:
    u_email = new_uuid()
    u_pwd   = new_uuid()
    u_dict  = new_uuid()
    u_post  = new_uuid()

    actions = [
        ask_for_input("Playtomic email", input_type="Text", uuid_str=u_email),
        ask_for_secure_input("Playtomic password", uuid_str=u_pwd),
        dictionary(
            [
                ("email",    attachment(u_email, "Provided Input")),
                ("password", attachment(u_pwd,   "Provided Input")),
            ],
            uuid_str=u_dict,
        ),
        http_request(
            url="https://api.playtomic.io/v3/auth/login",
            method="POST",
            headers=HEADERS_JSON,
            body_dict_uuid=u_dict,
            uuid_str=u_post,
        ),
        save_file_to_icloud(u_post, path=TOKENS_PATH, overwrite=True),
        show_notification(title="Playtomic", body_text="Logged in ✓"),
    ]
    return build_shortcut(actions, name="Playtomic Login")


# ─── shortcut 2: Padel Door Code ─────────────────────────────────────────────

def make_padel_code() -> dict:
    # Pre-allocate every UUID we'll need so the code reads top-to-bottom.
    u_file        = new_uuid()
    u_tokens      = new_uuid()
    u_rt          = new_uuid()
    u_refreshdict = new_uuid()
    u_postref     = new_uuid()
    u_newtokens   = new_uuid()
    u_at          = new_uuid()
    u_authhdr     = new_uuid()
    u_matches     = new_uuid()
    u_today       = new_uuid()
    u_today_str   = new_uuid()
    u_init_code   = new_uuid()
    u_init_court  = new_uuid()
    u_startdate   = new_uuid()
    u_codeobj     = new_uuid()
    u_code        = new_uuid()
    u_court       = new_uuid()
    u_get_code    = new_uuid()      # Get Variable "theCode" — for clipboard at the end
    u_body        = new_uuid()

    repeat_start, repeat_end, _g_rep = repeat_each(u_matches)
    repeat_item_uuid = repeat_end["WFWorkflowActionParameters"]["UUID"]

    if_start, if_end = if_contains(
        input_attachment=attachment(u_startdate, "Dictionary Value"),
        compare=named_var_attachment("today"),
    )

    actions = [
        # ── Part A: refresh access token using saved refresh_token ─────────
        get_file_from_icloud(TOKENS_PATH, uuid_str=u_file),
        get_dictionary_from_input(u_file, uuid_str=u_tokens),
        get_dictionary_value(u_tokens, "refresh_token", uuid_str=u_rt),
        dictionary(
            [
                ("grant_type",    "refresh_token"),
                ("refresh_token", attachment(u_rt, "Dictionary Value")),
            ],
            uuid_str=u_refreshdict,
        ),
        http_request(
            url="https://api.playtomic.io/v3/auth/token",
            method="POST",
            headers=HEADERS_JSON,
            body_dict_uuid=u_refreshdict,
            uuid_str=u_postref,
        ),
        # Persist the rotated tokens immediately so we never lose a fresh refresh_token
        save_file_to_icloud(u_postref, path=TOKENS_PATH, overwrite=True),
        get_dictionary_from_input(u_postref, uuid_str=u_newtokens),
        get_dictionary_value(u_newtokens, "access_token", uuid_str=u_at),

        # ── Part B: fetch matches ─────────────────────────────────────────
        text_action(
            "Bearer ${at}",
            {"at": attachment(u_at, "Dictionary Value")},
            uuid_str=u_authhdr,
        ),
        http_request(
            url="https://api.playtomic.io/v1/matches?user_id=me",
            method="GET",
            headers={
                **HEADERS_BASE,
                "Authorization": attachment(u_authhdr, "Text"),
            },
            uuid_str=u_matches,
        ),

        # ── Part C: today's date string + initialise output vars ──────────
        current_date(uuid_str=u_today),
        format_date(u_today, fmt="yyyy-MM-dd", uuid_str=u_today_str),
        set_variable("today", u_today_str, source_name="Formatted Date"),

        text_action("(no booking found)", uuid_str=u_init_code),
        set_variable("theCode", u_init_code, source_name="Text"),
        text_action("", uuid_str=u_init_court),
        set_variable("court", u_init_court, source_name="Text"),

        # ── Loop body ─────────────────────────────────────────────────────
        repeat_start,
        get_dictionary_value(repeat_item_uuid, "start_date", uuid_str=u_startdate),
        if_start,
        get_dictionary_value(repeat_item_uuid, "merchant_access_code", uuid_str=u_codeobj),
        get_dictionary_value(u_codeobj, "code", uuid_str=u_code),
        set_variable("theCode", u_code, source_name="Dictionary Value"),
        get_dictionary_value(repeat_item_uuid, "resource_name", uuid_str=u_court),
        set_variable("court", u_court, source_name="Dictionary Value"),
        if_end,
        repeat_end,

        # ── Part D: notify + copy to clipboard ────────────────────────────
        text_action(
            "🔑 Door code: ${theCode}\n🕓 ${court}",
            {
                "theCode": named_var_attachment("theCode"),
                "court":   named_var_attachment("court"),
            },
            uuid_str=u_body,
        ),
        show_notification(title="🎾 Padel @ PADALL", body_uuid=u_body),
        # Re-emit "theCode" via Get Variable so we have a UUID to feed clipboard
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getvariable",
            "WFWorkflowActionParameters": {
                "UUID": u_get_code,
                "WFVariable": {
                    "Value": {"Type": "Variable", "VariableName": "theCode"},
                    "WFSerializationType": "WFTextTokenAttachment",
                },
            },
        },
        copy_to_clipboard(u_get_code),
    ]

    return build_shortcut(actions, name="Padel Door Code")


# ─── main ────────────────────────────────────────────────────────────────────

def _save(sc: dict, path: str | Path) -> None:
    with open(path, "wb") as f:
        plistlib.dump(sc, f, fmt=plistlib.FMT_BINARY)
    print(f"wrote {path}")


if __name__ == "__main__":
    _save(make_login(),      "playtomic-login.shortcut")
    _save(make_padel_code(), "padel-code.shortcut")
