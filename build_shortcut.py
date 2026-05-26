#!/usr/bin/env python3
"""
build_shortcut.py — Programmatically construct a .shortcut plist using stdlib `plistlib`.

This produces an UNSIGNED .shortcut file. To make it importable on iOS 15+/18+/26 you
MUST sign it on a Mac afterwards:

    shortcuts sign --mode anyone -i my.shortcut -o my-signed.shortcut

(Use --mode people for a shortcut you'll only AirDrop to specific contacts.)

The resulting .shortcut file can then be:
  • Dropped into iCloud Drive and tapped on iPhone, OR
  • Hosted at https://yoursite/foo.shortcut and opened with
    shortcuts://import-shortcut?url=https%3A%2F%2Fyoursite%2Ffoo.shortcut&name=Foo

This file demonstrates ALL the action shapes you asked about:
  Ask for Input (text / secure text), Set/Get Variable, Dictionary, URL+Get Contents
  of URL with method/headers/JSON body, Save File, Get File, Get Dictionary from Input,
  Get Dictionary Value, Text, Date, Format Date, Get Time Between Dates, Number,
  If/Otherwise/End If, Repeat with Each, Show Notification, Copy to Clipboard.

Author: research scratchpad — see /tmp/playtomic/shortcut-research.md for full citations.
"""

import plistlib
import uuid
from typing import Any

# U+FFFC — the placeholder ALL inter-action variable refs must use inside `string`.
OBJ_REPL = "\uFFFC"


def new_uuid() -> str:
    """All UUIDs in a shortcut must be uppercase."""
    return str(uuid.uuid4()).upper()


# ─── helpers for building parameter values ───────────────────────────────────

def text_value(s: str, attachments: dict | None = None) -> dict:
    """Wrap a (possibly variable-containing) string as a WFTextTokenString value."""
    return {
        "Value": {
            "string": s,
            "attachmentsByRange": attachments or {},
        },
        "WFSerializationType": "WFTextTokenString",
    }


def var_ref(source_uuid: str, output_name: str = "Output") -> dict:
    """A pure single-variable parameter (no surrounding text)."""
    return {
        "Value": {
            "OutputName": output_name,
            "OutputUUID": source_uuid,
            "Type": "ActionOutput",
        },
        "WFSerializationType": "WFTextTokenAttachment",
    }


def named_var_ref(var_name: str) -> dict:
    """Reference to a *named* variable created by Set Variable / Ask for Input."""
    return {
        "Value": {
            "Type": "Variable",
            "VariableName": var_name,
        },
        "WFSerializationType": "WFTextTokenAttachment",
    }


def number_value(n: float) -> dict:
    return {
        "Value": {
            "string": str(n),
            "attachmentsByRange": {},
        },
        "WFSerializationType": "WFTextTokenString",
    }


def attachment(uuid_str: str, output_name: str = "Output") -> dict:
    return {
        "OutputName": output_name,
        "OutputUUID": uuid_str,
        "Type": "ActionOutput",
    }


# ─── action factories ────────────────────────────────────────────────────────

def ask_for_input(prompt: str, input_type: str = "Text",
                  default: str = "", uuid_str: str | None = None) -> dict:
    """
    is.workflow.actions.ask
      WFInputType: "Text" | "Number" | "URL" | "Date" | "Time" | "Date and Time"
      WFAskActionPrompt: prompt string
      WFAskActionDefaultAnswer: default text
      WFAskActionAllowsMultilineText (bool)
    For SECURE text, set WFInputType = "Text" AND WFAskActionUseSecureInput = True.
    """
    params: dict[str, Any] = {
        "UUID": uuid_str or new_uuid(),
        "WFInputType": input_type,
        "WFAskActionPrompt": text_value(prompt),
        "WFAskActionDefaultAnswer": text_value(default),
    }
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.ask",
        "WFWorkflowActionParameters": params,
    }


def ask_for_secure_input(prompt: str, uuid_str: str | None = None) -> dict:
    a = ask_for_input(prompt, input_type="Text", uuid_str=uuid_str)
    a["WFWorkflowActionParameters"]["WFAskActionUseSecureInput"] = True
    return a


def set_variable(name: str, source_uuid: str, source_name: str = "Output") -> dict:
    """is.workflow.actions.setvariable — gives the previous action's output a name."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.setvariable",
        "WFWorkflowActionParameters": {
            "WFVariableName": name,
            "WFInput": var_ref(source_uuid, source_name),
        },
    }


def get_variable(name: str) -> dict:
    """is.workflow.actions.getvariable"""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.getvariable",
        "WFWorkflowActionParameters": {
            "WFVariable": named_var_ref(name),
        },
    }


def dictionary(entries: list[tuple[str, str]], uuid_str: str | None = None) -> dict:
    """
    is.workflow.actions.dictionary — literal dict constructor.
    entries: list of (key, string_value) tuples.
    """
    items = [
        {
            "WFItemType": 0,                       # 0 = string, 1 = number, 2 = array, 3 = dict, 4 = bool
            "WFKey": text_value(k),
            "WFValue": text_value(v),
        }
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


def get_contents_of_url(url: str, method: str = "POST",
                        headers: dict[str, str] | None = None,
                        json_body_dict_uuid: str | None = None,
                        uuid_str: str | None = None) -> dict:
    """
    is.workflow.actions.downloadurl
      WFHTTPMethod, WFURL, WFHTTPHeaders, WFHTTPBodyType ("JSON" | "Form" | "File"),
      WFJSONValues (a dictionary-shaped param, typically wired to a Dictionary action).
    """
    params: dict[str, Any] = {
        "UUID": uuid_str or new_uuid(),
        "WFURL": text_value(url),
        "WFHTTPMethod": method,
    }
    if headers:
        params["WFHTTPHeaders"] = {
            "Value": {
                "WFDictionaryFieldValueItems": [
                    {"WFItemType": 0, "WFKey": text_value(k), "WFValue": text_value(v)}
                    for k, v in headers.items()
                ]
            },
            "WFSerializationType": "WFDictionaryFieldValue",
        }
    if json_body_dict_uuid and method in ("POST", "PUT", "PATCH"):
        params["WFHTTPBodyType"] = "JSON"
        params["WFJSONValues"] = var_ref(json_body_dict_uuid, "Dictionary")
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
        "WFWorkflowActionParameters": params,
    }


def text(s: str, uuid_str: str | None = None) -> dict:
    """is.workflow.actions.gettext — literal Text action."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFTextActionText": s,   # plain string OR a text_value(...) dict if it contains var refs
        },
    }


def number(n: float, uuid_str: str | None = None) -> dict:
    """is.workflow.actions.number"""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.number",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFNumberActionNumber": n,
        },
    }


def date_from_text(date_str: str, uuid_str: str | None = None) -> dict:
    """is.workflow.actions.date — parses a string to a Date."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.date",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFDateActionDate": text_value(date_str),
            "WFDateActionMode": "Specified Date",
        },
    }


def format_date(source_uuid: str, fmt: str = "yyyy-MM-dd HH:mm:ss",
                uuid_str: str | None = None) -> dict:
    """
    is.workflow.actions.format.date
      WFDateFormatStyle: "Short" | "Medium" | "Long" | "Full" | "Custom" | "RFC 2822" | "ISO 8601"
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.format.date",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFInput": var_ref(source_uuid, "Date"),
            "WFDateFormatStyle": "Custom",
            "WFDateFormat": text_value(fmt),
        },
    }


def time_between_dates(first_uuid: str, second_uuid: str,
                       unit: str = "Seconds", uuid_str: str | None = None) -> dict:
    """
    is.workflow.actions.gettimebetweendates
      WFTimeUntilUnit: "Seconds" | "Minutes" | "Hours" | "Days" | "Weeks" | "Months" | "Years"
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.gettimebetweendates",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFInput": var_ref(first_uuid, "Date"),
            "WFAnotherDate": var_ref(second_uuid, "Date"),
            "WFTimeUntilUnit": unit,
        },
    }


def get_dictionary_from_input(source_uuid: str, uuid_str: str | None = None) -> dict:
    """is.workflow.actions.detect.dictionary — parse JSON/dict input into a Dictionary."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.detect.dictionary",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFInput": var_ref(source_uuid, "Contents of URL"),
        },
    }


def get_dictionary_value(dict_uuid: str, key: str,
                         get_type: str = "Value",
                         uuid_str: str | None = None) -> dict:
    """
    is.workflow.actions.getvalueforkey
      WFGetDictionaryValueType: "Value" | "All Keys" | "All Values" | "Dictionary"
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFInput": var_ref(dict_uuid, "Dictionary"),
            "WFDictionaryKey": text_value(key),
            "WFGetDictionaryValueType": get_type,
        },
    }


def save_file_to_icloud(source_uuid: str, path: str = "/Shortcuts/", overwrite: bool = True,
                        uuid_str: str | None = None) -> dict:
    """
    is.workflow.actions.documentpicker.save
      Saves to iCloud Drive at a specific path (turn OFF Ask Where to Save).
      WFFileServiceID = "iCloud Drive"
      WFFileDestinationPath = "/Shortcuts/myfile.json"
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.documentpicker.save",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFInput": var_ref(source_uuid, "File"),
            "WFAskWhereToSave": False,
            "WFFileServiceID": "iCloud Drive",
            "WFFileDestinationPath": path,
            "WFOverwriteIfExists": overwrite,
        },
    }


def get_file_from_icloud(path: str, uuid_str: str | None = None) -> dict:
    """
    is.workflow.actions.documentpicker.open
      WFFileServiceID = "iCloud Drive"
      WFFilePath = "/Shortcuts/myfile.json"
      WFShowFilePicker = False  (so it grabs the path directly, no UI)
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.documentpicker.open",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFShowFilePicker": False,
            "WFFileServiceID": "iCloud Drive",
            "WFFilePath": path,
        },
    }


def show_notification(title: str, body_uuid: str | None = None,
                      body_text: str = "", uuid_str: str | None = None) -> dict:
    """is.workflow.actions.notification — title + (optional) body from a previous action."""
    if body_uuid:
        body_param = text_value(
            OBJ_REPL,
            attachments={"{0, 1}": attachment(body_uuid)},
        )
    else:
        body_param = text_value(body_text)
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFNotificationActionTitle": text_value(title),
            "WFNotificationActionBody": body_param,
        },
    }


def copy_to_clipboard(source_uuid: str, uuid_str: str | None = None) -> dict:
    """is.workflow.actions.copy"""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.copy",
        "WFWorkflowActionParameters": {
            "UUID": uuid_str or new_uuid(),
            "WFInput": var_ref(source_uuid),
        },
    }


# ─── control flow: If / Otherwise / End If ───────────────────────────────────
# All three actions share the SAME WFWorkflowActionIdentifier
# (is.workflow.actions.conditional) and the SAME GroupingIdentifier UUID;
# they're distinguished by WFControlFlowMode (0=if/start, 1=else, 2=endif).

def if_block(condition_source_uuid: str, op: int = 4, compare_to: str = "",
             group_uuid: str | None = None) -> list[dict]:
    """
    Returns [if_start, else, end_if] — caller injects body actions between them.
    op values for WFCondition:
      0 = Is, 1 = Is Not, 2 = Has Any Value, 3 = Does Not Have Any Value,
      4 = Contains (string), 5 = Does Not Contain, 100 = Equals (number),
      101 = Is Greater Than, 102 = Is Less Than, etc.
    """
    g = group_uuid or new_uuid()
    if_start = {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "GroupingIdentifier": g,
            "WFControlFlowMode": 0,
            "WFInput": var_ref(condition_source_uuid),
            "WFCondition": op,
            "WFConditionalActionString": text_value(compare_to),
        },
    }
    otherwise = {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "GroupingIdentifier": g,
            "WFControlFlowMode": 1,
        },
    }
    end_if = {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "GroupingIdentifier": g,
            "WFControlFlowMode": 2,
            "UUID": new_uuid(),       # the End If's UUID is the "If Result" magic variable
        },
    }
    return [if_start, otherwise, end_if]


def repeat_each(list_source_uuid: str, group_uuid: str | None = None) -> tuple[dict, dict, str]:
    """
    Returns (start, end, end_uuid). The end_uuid is also how you reference "Repeat Item"
    inside the loop (Repeat Item / Repeat Index are outputs of the *End* action).
    """
    g = group_uuid or new_uuid()
    end_uuid = new_uuid()
    start = {
        "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
        "WFWorkflowActionParameters": {
            "GroupingIdentifier": g,
            "WFControlFlowMode": 0,
            "WFInput": var_ref(list_source_uuid),
        },
    }
    end = {
        "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
        "WFWorkflowActionParameters": {
            "GroupingIdentifier": g,
            "WFControlFlowMode": 2,
            "UUID": end_uuid,
        },
    }
    return start, end, end_uuid


# ─── envelope (root plist) ───────────────────────────────────────────────────

def build_shortcut(actions: list[dict], name: str = "Generated Shortcut") -> dict:
    return {
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "2700.0.4",     # iOS 26.x; works on iOS 18+ as MinClientVersion stays low
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowName": name,
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59511,
            "WFWorkflowIconStartColor": 4282601983,   # red — see sebj reference for color list
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": [
            "WFAppStoreAppContentItem", "WFArticleContentItem", "WFContactContentItem",
            "WFDateContentItem", "WFEmailAddressContentItem", "WFGenericFileContentItem",
            "WFImageContentItem", "WFiTunesProductContentItem", "WFLocationContentItem",
            "WFDCMapsLinkContentItem", "WFAVAssetContentItem", "WFPDFContentItem",
            "WFPhoneNumberContentItem", "WFRichTextContentItem", "WFSafariWebPageContentItem",
            "WFStringContentItem", "WFURLContentItem",
        ],
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowTypes": [],
    }


# ─── demo: "Ask name, show notification" ─────────────────────────────────────

def demo_minimal() -> dict:
    ask_uuid = new_uuid()
    actions = [
        ask_for_input("What's your name?", default="World", uuid_str=ask_uuid),
        show_notification(title="Hello", body_uuid=ask_uuid),
    ]
    return build_shortcut(actions, name="Hello, Name")


if __name__ == "__main__":
    sc = demo_minimal()
    with open("hello-name.shortcut", "wb") as f:
        # binary plist; Shortcuts also accepts XML plists with the .shortcut extension
        plistlib.dump(sc, f, fmt=plistlib.FMT_BINARY)
    print("Wrote hello-name.shortcut")
    print("Now sign on a Mac:  shortcuts sign --mode anyone -i hello-name.shortcut -o hello-name-signed.shortcut")
