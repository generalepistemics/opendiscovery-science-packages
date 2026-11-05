"""Credential presence reporting and recursive redaction."""

from __future__ import annotations

import itertools
import os
import platform
import re
import subprocess
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .constants import BIOHUB_API_KEY_URL, BIOHUB_QUICKSTART_URL

MACOS_KEYCHAIN_SERVICE = "com.generalepistemics.opendiscovery.biohub-esm.ESM_API_KEY"
# -U replaces this command's earlier item in place; without it a rerun fails after both prompts.
MACOS_KEYCHAIN_SETUP_COMMAND = (
    f'security add-generic-password -U -a "$USER" -s {MACOS_KEYCHAIN_SERVICE} -w'
)
KEYCHAIN_LOOKUP_TIMEOUT_SECONDS = 2.0
DISABLE_KEYCHAIN_ENV = "BIOHUB_ESM_DISABLE_KEYCHAIN"
KEYCHAIN_ITEM_NOT_FOUND_EXIT = 44
# `security` reports this search call failing only when it cannot reach the Keychain at all,
# as in the OpenDiscovery sandbox without network access; a missing item fails in SecKeychainSearchCopyNext.
KEYCHAIN_UNREACHABLE_STDERR = "SecKeychainSearchCreateFromAttributes"
KEYCHAIN_UNREACHABLE_SOURCE = "macos-keychain-unreachable"
KEYCHAIN_UNREACHABLE_MESSAGE = (
    "ESM_API_KEY is not set, and this command could not reach the macOS Keychain, usually "
    "because a command sandbox blocked it, so a key saved there cannot be read. Rerun the "
    "command outside the sandbox before asking the user for a key."
)
KEYCHAIN_UNREADABLE_SOURCE = "macos-keychain-unreadable"
KEYCHAIN_UNREADABLE_MESSAGE = (
    "A macOS Keychain item for ESM_API_KEY exists, but macOS did not release its value to the "
    "plugin, as happens with an item made in the Keychain Access app. Run "
    f"`{MACOS_KEYCHAIN_SETUP_COMMAND}` in Terminal and paste the key at both prompts; the plugin "
    "reads the item that command saves first. No restart is needed."
)
_RUNTIME_REDACTION_SECRETS: set[str] = set()
_RUNTIME_REDACTION_SECRETS_LOCK = threading.Lock()


@dataclass(frozen=True)
class CredentialResolution:
    """A credential value with a safe, non-secret representation."""

    value: str | None = field(repr=False)
    source: str

    @property
    def configured(self) -> bool:
        return self.value is not None


def register_redaction_secret(value: str | None) -> None:
    """Keep one secret redacted for the lifetime of this single-command CLI process."""

    if not isinstance(value, str) or len(value) < 4:
        return
    with _RUNTIME_REDACTION_SECRETS_LOCK:
        _RUNTIME_REDACTION_SECRETS.add(value)


def _runtime_redaction_secrets() -> tuple[str, ...]:
    with _RUNTIME_REDACTION_SECRETS_LOCK:
        return tuple(sorted(_RUNTIME_REDACTION_SECRETS, key=len, reverse=True))


def _redaction_secrets(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return registered and configured secrets without exposing their values."""

    values = os.environ if env is None else env
    secrets = set(_runtime_redaction_secrets())
    for key in ("ESM_API_KEY", "HF_TOKEN", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"):
        secret = values.get(key, "")
        if secret and len(secret) >= 4:
            secrets.add(secret)
    return tuple(sorted(secrets, key=len, reverse=True))


def _crossing_secret_start(value: str, secrets: tuple[str, ...]) -> int | None:
    """Find the earliest known-secret prefix cut by the end of ``value``."""

    earliest: int | None = None
    for secret in secrets:
        maximum_visible = min(len(value), len(secret) - 1)
        if maximum_visible <= 0:
            continue
        search_start = len(value) - maximum_visible
        needle = secret[:4]
        position = value.find(needle, search_start)
        while position >= 0:
            visible = value[position:]
            if len(visible) < len(secret) and secret.startswith(visible):
                earliest = position if earliest is None else min(earliest, position)
                break
            position = value.find(needle, position + 1)
        for length in range(min(3, maximum_visible), 0, -1):
            if value.endswith(secret[:length]):
                position = len(value) - length
                earliest = position if earliest is None else min(earliest, position)
                break
    return earliest


def _bounded_secret_bytes(secret: str, limit: int) -> tuple[bytes, bool] | None:
    """Encode only enough of one secret to cover a bounded byte preview."""

    characters = secret[: limit + 1]
    try:
        encoded = characters.encode("utf-8", errors="surrogateescape")
    except UnicodeEncodeError:
        return None
    complete = len(characters) == len(secret) and len(encoded) <= limit + 1
    return encoded[: limit + 1], complete


def _bounded_secret_byte_forms(
    secrets: tuple[str, ...],
    *,
    limit: int,
) -> tuple[tuple[tuple[bytes, bool], ...], bool]:
    """Bound secret encodings and report values that have no safe byte form."""

    forms: list[tuple[bytes, bool]] = []
    has_unencodable = False
    for secret in secrets:
        form = _bounded_secret_bytes(secret, limit)
        if form is None:
            has_unencodable = True
        else:
            forms.append(form)
    return tuple(forms), has_unencodable


def _crossing_secret_bytes_start(
    value: bytes,
    secret_forms: tuple[tuple[bytes, bool], ...],
) -> int | None:
    """Find the earliest UTF-8 secret prefix cut by a byte-preview boundary."""

    earliest: int | None = None
    for prefix, complete in secret_forms:
        maximum_visible = len(value) if not complete else min(len(value), len(prefix) - 1)
        if maximum_visible <= 0 or not prefix:
            continue
        search_start = len(value) - maximum_visible
        needle = prefix[: min(4, len(prefix))]
        position = value.find(needle, search_start)
        while position >= 0:
            visible = value[position:]
            if prefix.startswith(visible) and (not complete or len(visible) < len(prefix)):
                earliest = position if earliest is None else min(earliest, position)
                break
            position = value.find(needle, position + 1)
        for length in range(min(3, maximum_visible, len(prefix)), 0, -1):
            if value.endswith(prefix[:length]):
                position = len(value) - length
                earliest = position if earliest is None else min(earliest, position)
                break
    return earliest


def _redact_complete_secret_bytes(
    value: bytes,
    secret_forms: tuple[tuple[bytes, bool], ...],
) -> bytes:
    """Replace complete known-secret byte spans before lossy UTF-8 decoding."""

    spans: list[tuple[int, int]] = []
    for secret, complete in secret_forms:
        if not complete or not secret:
            continue
        offset = 0
        while (position := value.find(secret, offset)) >= 0:
            spans.append((position, position + len(secret)))
            offset = position + len(secret)
    if not spans:
        return value

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    chunks: list[bytes] = []
    offset = 0
    for start, end in merged:
        chunks.extend((value[offset:start], b"[REDACTED]"))
        offset = end
    chunks.append(value[offset:])
    return b"".join(chunks)


CAMEL_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
KEY_INITIAL_RE = r"[A-Za-z_\\]"
KEY_CHARACTER_RE = r"[-A-Za-z0-9_./\\]"
ASSIGNMENT_PREFIX_RE = re.compile(
    rf"""(?ix)
    (?<![A-Za-z0-9_\\-])
    (?:
      (?P<bracket_owner>{KEY_INITIAL_RE}{KEY_CHARACTER_RE}*)\s*\[\s*
      (?:
        (?P<bracket_quote>(?:\\*["']))
        (?P<bracket_quoted_key>{KEY_INITIAL_RE}(?:{KEY_CHARACTER_RE}|\s)*?)
        (?P=bracket_quote)
        |
        (?P<bracket_bare_key>{KEY_INITIAL_RE}{KEY_CHARACTER_RE}*)
        |
        (?P<bracket_index>[0-9]+)
      )\s*\]
      |
      (?P<key_quote>(?:\\*["']))
      (?P<quoted_key>{KEY_INITIAL_RE}(?:{KEY_CHARACTER_RE}|\s)*?)
      (?P=key_quote)
      |
      (?P<spaced_key>
        (?:secret\s+access\s+key|authorization\s+header|access\s+key(?:\s+id)?
        |api\s+key|private\s+key|client\s+secret|client\s+credentials?
        |secret\s+key|token\s+secret|password\s+hash)
      )
      |
      (?P<bare_key>{KEY_INITIAL_RE}{KEY_CHARACTER_RE}*)
    )
    (?P<separator>\s*(?:[=:]|%3d)\s*)
    """
)
URL_SECRET_PARAM_RE = re.compile(
    r"(?i)([?&](?:x-amz-credential|x-amz-signature|x-amz-security-token|token|credential|signature)=)[^&#\s]+"
)


def _configured(env: Mapping[str, str], key: str) -> bool:
    return bool(env.get(key, "").strip())


def _keychain_fallback_enabled(values: Mapping[str, str], system_name: str | None) -> bool:
    system = platform.system() if system_name is None else system_name
    return system == "Darwin" and values.get(DISABLE_KEYCHAIN_ENV, "").strip() != "1"


def missing_esm_api_key_message(
    source: str = "none",
    *,
    env: Mapping[str, str] | None = None,
    system_name: str | None = None,
) -> str:
    """The one message shown when managed access has no credential.

    Both the transport and the ESMC mutation commands raise this, so the
    acquisition URL and the Keychain command cannot drift between them.
    """

    if source == KEYCHAIN_UNREACHABLE_SOURCE:
        return KEYCHAIN_UNREACHABLE_MESSAGE
    if source == KEYCHAIN_UNREADABLE_SOURCE:
        return KEYCHAIN_UNREADABLE_MESSAGE
    if _keychain_fallback_enabled(os.environ if env is None else env, system_name):
        return (
            "ESM_API_KEY is missing. Get a free key at "
            f"{BIOHUB_API_KEY_URL} (existing Forge accounts sign in with the same "
            f"credentials), run `{MACOS_KEYCHAIN_SETUP_COMMAND}` in Terminal, and "
            "paste the key at both prompts. No restart is needed."
        )
    return (
        "ESM_API_KEY is missing. Get a free key at "
        f"{BIOHUB_API_KEY_URL} (existing Forge accounts sign in with the same "
        "credentials), set it as ESM_API_KEY in the environment that launches "
        "OpenDiscovery, then restart OpenDiscovery."
    )


def _macos_keychain_lookup(
    values: Mapping[str, str],
    *,
    read_value: bool,
    keychain_run: Callable[..., Any] | None,
) -> tuple[str, str | None]:
    """Look up the item the setup command saves, then any item with the service.

    Returns ``present`` (with the value when ``read_value``), ``absent``,
    ``unreachable``, or, for a value read only, ``unreadable``.
    """

    runner = subprocess.run if keychain_run is None else keychain_run
    selectors = [["-s", MACOS_KEYCHAIN_SERVICE]]
    account = values.get("USER", "").strip()
    if account:
        # The setup command's item wins over an older one saved under another account.
        selectors.insert(0, ["-a", account, "-s", MACOS_KEYCHAIN_SERVICE])
    for selector in selectors:
        try:
            completed = runner(
                ["/usr/bin/security", "find-generic-password", *selector]
                + (["-w"] if read_value else []),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE if read_value else subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                shell=False,
                timeout=KEYCHAIN_LOOKUP_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            # A value read that outlasts the timeout is waiting on a macOS approval prompt.
            return ("unreadable" if read_value else "absent"), None
        except (OSError, subprocess.SubprocessError):
            return "absent", None
        if completed.returncode == 0:
            if not read_value:
                return "present", None
            value = completed.stdout.strip()
            return ("present", value) if value else ("absent", None)
        if KEYCHAIN_UNREACHABLE_STDERR in (completed.stderr or ""):
            return "unreachable", None
        if completed.returncode != KEYCHAIN_ITEM_NOT_FOUND_EXIT:
            return ("unreadable" if read_value else "absent"), None
    return "absent", None


def resolve_esm_api_key(
    env: Mapping[str, str] | None = None,
    *,
    system_name: str | None = None,
    keychain_run: Callable[..., Any] | None = None,
) -> CredentialResolution:
    """Resolve Biohub auth without displaying, logging, or persisting the value.

    ``ESM_API_KEY`` always wins. On macOS only, an absent environment value may
    fall back to the verified generic-password service used by the OpenDiscovery host.
    Lookup failures read as a missing key, except an unreachable Keychain or an
    item macOS will not release, which would otherwise send the user to create
    a key they already saved.
    """

    values = os.environ if env is None else env
    environment_value = values.get("ESM_API_KEY", "").strip()
    if environment_value:
        return CredentialResolution(value=environment_value, source="environment")
    if not _keychain_fallback_enabled(values, system_name):
        return CredentialResolution(value=None, source="none")

    state, value = _macos_keychain_lookup(values, read_value=True, keychain_run=keychain_run)
    if state == "present":
        return CredentialResolution(value=value, source="macos-keychain")
    if state == "unreachable":
        return CredentialResolution(value=None, source=KEYCHAIN_UNREACHABLE_SOURCE)
    if state == "unreadable":
        return CredentialResolution(value=None, source=KEYCHAIN_UNREADABLE_SOURCE)
    return CredentialResolution(value=None, source="none")


SENSITIVE_KEY_SEGMENTS = {
    "authorization",
    "credential",
    "credentials",
    "password",
    "passwords",
    "secret",
    "secrets",
    "signature",
    "signatures",
}
SAFE_SECRET_METADATA = {"count", "counts", "length", "lengths"}
SAFE_TOKEN_METADATA = {
    "activation",
    "activations",
    "attention",
    "attentions",
    "count",
    "counts",
    "dropout",
    "embedding",
    "embeddings",
    "entropy",
    "entropies",
    "expires",
    "expiration",
    "expirations",
    "expiry",
    "feature",
    "features",
    "hidden",
    "ids",
    "indices",
    "indexes",
    "length",
    "lengths",
    "logit",
    "logits",
    "mask",
    "masks",
    "offset",
    "offsets",
    "position",
    "positions",
    "probabilities",
    "probability",
    "representation",
    "representations",
    "saliency",
    "score",
    "scores",
    "state",
    "states",
    "type",
    "types",
    "values",
    "vector",
    "vectors",
}
SAFE_PLURAL_TOKEN_PREFIXES = {
    "acid",
    "added",
    "amino",
    "cached",
    "completion",
    "input",
    "max",
    "min",
    "model",
    "num",
    "output",
    "overflowing",
    "prompt",
    "protein",
    "reasoning",
    "residue",
    "sae",
    "sequence",
    "special",
    "suppress",
    "total",
    "truncated",
    "vocab",
}
TOKENIZER_TOKEN_PREFIXES = {
    "bos",
    "cls",
    "eos",
    "mask",
    "pad",
    "sep",
    "unk",
}
SAFE_EXACT_SCIENTIFIC_KEYS = {"token_to_atoms"}
SAFE_COMPACT_TOKENIZER_KEYS = {
    f"{modifier}{prefix}token{suffix}"
    for modifier in ("", "forced", "tokenizer", "tokenizerforced")
    for prefix in TOKENIZER_TOKEN_PREFIXES
    for suffix in ("", "id", "ids")
} | {
    "addedtokensdecoder",
    "decoderstarttoken",
    "decoderstarttokenid",
    "decoderstarttokenids",
    "numtruncatedtokens",
    "specialtokensmask",
}
SAFE_SCIENTIFIC_TOKEN_PREFIXES = SAFE_PLURAL_TOKEN_PREFIXES | {
    "batch",
    "chain",
    "layer",
    "per",
    "position",
}
SAFE_COMPACT_SCIENTIFIC_TOKEN_PREFIXES = SAFE_SCIENTIFIC_TOKEN_PREFIXES | {
    "aminoacid",
    "perposition",
    "perresidue",
}
DYNAMIC_SCIENTIFIC_SCOPE_HEADS = {"layer", "position", "residue"}
DYNAMIC_COMPACT_SCIENTIFIC_PREFIX_RE = re.compile(r"(?:sae|per)?(?:layer|position|residue)[0-9]+")
EXPLICIT_CHAIN_SNAKE_RE = re.compile(
    r"^(?P<lead>(?:[a-z]+_)*)chain_[A-Z0-9]{1,4}_token_(?P<metadata>[a-z0-9_]+)$"
)
EXPLICIT_CHAIN_CAMEL_RE = re.compile(
    r"^(?:(?P<lead>[a-z]+)Chain|chain)[A-Z0-9]{1,4}Token(?P<metadata>[A-Z][A-Za-z0-9]*)$"
)
CREDENTIAL_TOKEN_QUALIFIERS = {
    "access",
    "api",
    "auth",
    "authentication",
    "aws",
    "bearer",
    "biohub",
    "csrf",
    "esm",
    "gcp",
    "gh",
    "github",
    "gitlab",
    "hf",
    "huggingface",
    "idp",
    "jwt",
    "modal",
    "oauth",
    "oauth2",
    "oidc",
    "okta",
    "openai",
    "pat",
    "refresh",
    "security",
    "session",
    "slack",
    "sso",
    "sts",
}
SAFE_CREDENTIAL_TOKEN_METADATA = {
    "count",
    "counts",
    "expires",
    "expiration",
    "expirations",
    "expiry",
    "length",
    "lengths",
    "type",
    "types",
}
SAFE_COMPACT_CREDENTIAL_TOKEN_METADATA = {
    "count",
    "counts",
    "expires",
    "expiresat",
    "expiration",
    "expirations",
    "expiry",
    "length",
    "lengths",
    "type",
    "types",
}
COMPACT_SECRET_SUFFIXES = {
    "accesskey",
    "accesskeyid",
    "apikey",
    "apikeys",
    "authorizationheader",
    "clientcredentials",
    "clientsecret",
    "clientsecrets",
    "credentials",
    "passwordhash",
    "privatekey",
    "secretaccesskey",
    "secretkey",
    "token",
    "tokenid",
    "tokensecret",
}


def _key_segments(key: object) -> tuple[str, ...]:
    normalized = CAMEL_CASE_BOUNDARY_RE.sub("_", str(key))
    return tuple(segment.lower() for segment in re.split(r"[^A-Za-z0-9]+", normalized) if segment)


def _decode_key_label(key: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    decoded = re.sub(r"\\+u([0-9a-fA-F]{4})", replace, key)
    return re.sub(r"\\+x([0-9a-fA-F]{2})", replace, decoded)


def _assignment_keys(match: re.Match[str]) -> tuple[str, ...]:
    bracket_owner = match.group("bracket_owner")
    if bracket_owner is not None:
        child = match.group("bracket_quoted_key") or match.group("bracket_bare_key")
        keys = [bracket_owner]
        if child is not None:
            keys.append(child)
        return tuple(_decode_key_label(key) for key in keys)
    key = match.group("quoted_key") or match.group("spaced_key") or match.group("bare_key")
    return (_decode_key_label(key),)


def _is_scientific_token_prefix(prefix: tuple[str, ...]) -> bool:
    for index, item in enumerate(prefix):
        if item in SAFE_SCIENTIFIC_TOKEN_PREFIXES:
            continue
        previous = prefix[index - 1] if index else None
        if item.isdigit() and previous in DYNAMIC_SCIENTIFIC_SCOPE_HEADS:
            continue
        if re.fullmatch(r"(?:layer|position|residue)[0-9]+", item):
            continue
        return False
    return True


def _is_compact_credential_token_prefix(prefix: str) -> bool:
    return any(prefix.endswith(qualifier) for qualifier in CREDENTIAL_TOKEN_QUALIFIERS)


def _is_compact_scientific_token_prefix(prefix: str) -> bool:
    return prefix in SAFE_COMPACT_SCIENTIFIC_TOKEN_PREFIXES or bool(
        DYNAMIC_COMPACT_SCIENTIFIC_PREFIX_RE.fullmatch(prefix)
    )


def _has_explicit_scientific_chain_scope(key: str) -> bool:
    snake = EXPLICIT_CHAIN_SNAKE_RE.fullmatch(key)
    if snake is not None:
        lead = tuple(item for item in snake.group("lead").split("_") if item)
        metadata = _key_segments(snake.group("metadata"))
        return (
            _is_scientific_token_prefix(lead)
            and bool(metadata)
            and all(item in SAFE_TOKEN_METADATA for item in metadata)
        )
    camel = EXPLICIT_CHAIN_CAMEL_RE.fullmatch(key)
    if camel is None:
        return False
    lead = camel.group("lead")
    metadata = _key_segments(camel.group("metadata"))
    return (
        (lead is None or lead in SAFE_SCIENTIFIC_TOKEN_PREFIXES)
        and bool(metadata)
        and all(item in SAFE_TOKEN_METADATA for item in metadata)
    )


def _is_secret_key(key: object) -> bool:
    """Recognize credential labels while preserving model-token metadata."""

    raw_key = str(key)
    if raw_key in SAFE_EXACT_SCIENTIFIC_KEYS:
        return False
    explicit_chain_scope = _has_explicit_scientific_chain_scope(raw_key)
    segments = _key_segments(raw_key)
    for index, segment in enumerate(segments):
        if segment not in SENSITIVE_KEY_SEGMENTS:
            continue
        tail = segments[index + 1 :]
        if segment == "secret" and tail and tail[0] in SAFE_SECRET_METADATA:
            continue
        return True

    for left, right in itertools.pairwise(segments):
        if left in {"access", "api", "private"} and right in {"key", "keys"}:
            return True

    for index, segment in enumerate(segments):
        if segment == "token":
            prefix = segments[:index]
            tail = segments[index + 1 :]
            credential_qualified = any(item in CREDENTIAL_TOKEN_QUALIFIERS for item in prefix)
            if credential_qualified:
                if tail and tail[0] in SAFE_CREDENTIAL_TOKEN_METADATA:
                    continue
                return True
            tokenizer_prefix = bool(
                prefix
                and (prefix[-1] in TOKENIZER_TOKEN_PREFIXES or prefix[-2:] == ("decoder", "start"))
            )
            if tokenizer_prefix and (not tail or tail[0] in {"id", "ids"}):
                continue
            unknown_prefix = bool(prefix) and not (
                explicit_chain_scope or _is_scientific_token_prefix(prefix)
            )
            if unknown_prefix:
                if tail and tail[0] in SAFE_CREDENTIAL_TOKEN_METADATA:
                    continue
                return True
            if not tail or tail[0] not in SAFE_TOKEN_METADATA:
                return True
        elif segment == "tokens":
            prefix = segments[index - 1] if index else None
            if prefix is not None and prefix not in SAFE_PLURAL_TOKEN_PREFIXES:
                return True

    compact = re.sub(r"[^a-z0-9]", "", str(key).lower())
    if compact in SAFE_COMPACT_TOKENIZER_KEYS:
        return False
    for metadata in sorted(SAFE_TOKEN_METADATA, key=len, reverse=True):
        marker = f"token{metadata}"
        if not compact.endswith(marker):
            continue
        prefix = compact[: -len(marker)]
        if prefix and metadata not in SAFE_COMPACT_CREDENTIAL_TOKEN_METADATA:
            if not explicit_chain_scope and _is_compact_credential_token_prefix(prefix):
                return True
            if not (explicit_chain_scope or _is_compact_scientific_token_prefix(prefix)):
                return True
        break
    if any(compact.endswith(suffix) for suffix in COMPACT_SECRET_SUFFIXES):
        return True
    return False


def _quote_wrapper(value: str, start: int) -> str | None:
    index = start
    while index < len(value) and value[index] == "\\":
        index += 1
    if index < len(value) and value[index] in {'"', "'"}:
        return value[start : index + 1]
    return None


def _quoted_value_end(value: str, start: int, wrapper: str) -> int:
    quote = wrapper[-1]
    wrapper_backslashes = len(wrapper) - 1
    search = start + len(wrapper)
    while True:
        closing = value.find(quote, search)
        if closing < 0:
            return len(value)
        backslashes = 0
        cursor = closing - 1
        while cursor >= start and value[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        wrapper_matches = (
            backslashes % 2 == 0 if wrapper_backslashes == 0 else backslashes == wrapper_backslashes
        )
        end = closing + 1
        if wrapper_matches and (end == len(value) or value[end] in " \t\r\n,;}]"):
            return end
        search = closing + 1


def _quoted_segment_end(value: str, start: int, *, stop_at_record_delimiter: bool) -> int | None:
    quote = value[start]
    escaped = False
    for index in range(start + 1, len(value)):
        character = value[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == quote:
            return index + 1
        elif stop_at_record_delimiter and character in "\r\n,;":
            return None
    return None


def _advance_quote_context(
    value: str,
    start: int,
    end: int,
    *,
    quote: str | None,
    escaped: bool,
) -> tuple[str | None, bool]:
    """Scan quote state incrementally without one pointer per input character."""

    for index in range(start, end):
        character = value[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in {'"', "'"} and (index == 0 or value[index - 1] in " \t\r\n=:[{,("):
            quote = character
    return quote, escaped


def _unquoted_value_end(
    value: str,
    start: int,
    *,
    allow_spaces: bool,
    outer_quote: str | None,
) -> int:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    index = start
    while index < len(value):
        if value.startswith("[REDACTED]", index):
            marker_end = index + len("[REDACTED]")
            if not stack and (marker_end == len(value) or value[marker_end] in " \t\r\n,;}]\"'"):
                return marker_end
            index = marker_end
            continue

        character = value[index]
        if character in {'"', "'"}:
            quoted_end = _quoted_segment_end(
                value,
                index,
                stop_at_record_delimiter=not stack,
            )
            if quoted_end is None:
                if not stack and character == outer_quote:
                    return index
                return len(value)
            index = quoted_end
            continue
        if character in pairs:
            stack.append(pairs[character])
            index += 1
            continue
        if stack and character == stack[-1]:
            stack.pop()
            index += 1
            continue
        if not stack and character in "\r\n,;}]":
            return index
        if not stack and character.isspace():
            if not allow_spaces:
                return index
            next_start = index
            while next_start < len(value) and value[next_start].isspace():
                next_start += 1
            if ASSIGNMENT_PREFIX_RE.match(value, next_start):
                return index
        index += 1
    return len(value)


def _secret_value_end_and_replacement(
    value: str,
    start: int,
    *,
    key: str,
    outer_quote: str | None,
) -> tuple[int, str]:
    if start >= len(value):
        return start, "[REDACTED]"
    wrapper = _quote_wrapper(value, start)
    if wrapper is not None:
        return (
            _quoted_value_end(value, start, wrapper),
            f"{wrapper}[REDACTED]{wrapper}",
        )
    return (
        _unquoted_value_end(
            value,
            start,
            allow_spaces="authorization" in _key_segments(key),
            outer_quote=outer_quote,
        ),
        "[REDACTED]",
    )


def _redact_secret_assignments(value: str) -> str:
    pieces: list[str] = []
    cursor = 0
    search = 0
    context_cursor = 0
    quote: str | None = None
    escaped = False
    while match := ASSIGNMENT_PREFIX_RE.search(value, search):
        quote, escaped = _advance_quote_context(
            value,
            context_cursor,
            match.start(),
            quote=quote,
            escaped=escaped,
        )
        context_cursor = match.start()
        keys = _assignment_keys(match)
        if not any(_is_secret_key(key) for key in keys):
            search = match.start() + 1
            continue
        end, replacement = _secret_value_end_and_replacement(
            value,
            match.end(),
            key=" ".join(keys),
            outer_quote=quote,
        )
        pieces.extend((value[cursor : match.end()], replacement))
        cursor = end
        search = max(end, match.end())
    pieces.append(value[cursor:])
    return "".join(pieces)


def credential_preflight(
    env: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
    system_name: str | None = None,
    keychain_run: Callable[..., Any] | None = None,
) -> dict[str, object]:
    values = os.environ if env is None else env
    root = Path.home() if home is None else home
    biohub_environment = _configured(values, "ESM_API_KEY")
    keychain_enabled = _keychain_fallback_enabled(values, system_name)
    keychain_state = (
        _macos_keychain_lookup(values, read_value=False, keychain_run=keychain_run)[0]
        if not biohub_environment and keychain_enabled
        else "absent"
    )
    modal_env = _configured(values, "MODAL_TOKEN_ID") and _configured(values, "MODAL_TOKEN_SECRET")
    modal_profile = (root / ".modal.toml").is_file()
    biohub_managed: dict[str, str]
    if biohub_environment:
        biohub_managed = {"status": "configured", "source": "environment"}
    elif keychain_state == "present":
        biohub_managed = {"status": "configured", "source": "macos-keychain"}
    elif keychain_state == "unreachable":
        biohub_managed = {
            "status": "unverified",
            "source": KEYCHAIN_UNREACHABLE_SOURCE,
            "remedy": (
                "This command could not reach the macOS Keychain, usually because a command "
                "sandbox blocked it, so a key saved there cannot be seen. Rerun preflight "
                "outside the sandbox before treating the key as missing."
            ),
        }
    else:
        biohub_managed = {"status": "missing", "source": "none"}
    if biohub_managed["status"] != "configured":
        # Reporting only "missing" leaves the caller nothing to act on, so the
        # variable to set and the page that issues a key travel with the status.
        biohub_managed["variable"] = "ESM_API_KEY"
        biohub_managed["obtain_key_url"] = BIOHUB_API_KEY_URL
        biohub_managed["quickstart_url"] = BIOHUB_QUICKSTART_URL
        if keychain_enabled:
            biohub_managed["macos_keychain_command"] = MACOS_KEYCHAIN_SETUP_COMMAND
    return {
        "biohub_managed": biohub_managed,
        "atlas": {"status": "not-required", "source": "public v1alpha1 API and anonymous S3"},
        "modal": {
            "status": "configured" if modal_env or modal_profile else "missing",
            "source": "environment" if modal_env else ("profile" if modal_profile else "none"),
        },
        "hugging_face": {
            "status": "configured" if _configured(values, "HF_TOKEN") else "optional-missing",
            "source": "HF_TOKEN (optional for public weights)",
        },
    }


def redact_text(value: str, env: Mapping[str, str] | None = None) -> str:
    result = BEARER_RE.sub("Bearer [REDACTED]", value)
    result = URL_SECRET_PARAM_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", result)
    result = _redact_secret_assignments(result)
    for secret in _redaction_secrets(env):
        result = result.replace(secret, "[REDACTED]")
    return result


def redact_truncated_text(
    value: str,
    *,
    truncated: bool,
    env: Mapping[str, str] | None = None,
) -> str:
    """Redact a bounded text prefix without leaking a cut known secret."""

    if truncated:
        crossing = _crossing_secret_start(value, _redaction_secrets(env))
        if crossing is not None:
            value = value[:crossing] + "[REDACTED]"
    return redact_text(value, env)


def redact_bounded_bytes_preview(
    value: bytes,
    *,
    limit: int,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return a redacted UTF-8 preview without copying an unbounded byte body."""

    preview = value[:limit]
    truncated = len(value) > len(preview)
    secret_forms, has_unencodable_secret = _bounded_secret_byte_forms(
        _redaction_secrets(env),
        limit=limit,
    )
    if truncated and has_unencodable_secret:
        return "[REDACTED]"
    suffix = ""
    if truncated:
        crossing = _crossing_secret_bytes_start(preview, secret_forms)
        if crossing is not None:
            preview = preview[:crossing]
            suffix = "[REDACTED]"
    preview = _redact_complete_secret_bytes(preview, secret_forms)
    return redact_text(preview.decode("utf-8", errors="replace"), env) + suffix


def redact_mapping_key(value: object, env: Mapping[str, str] | None = None) -> str:
    """Redact credential material embedded in a mapping key."""

    return redact_text(str(value), env)


def _unique_mapping_key(candidate: str, existing: Mapping[str, Any], index: int) -> str:
    if candidate not in existing:
        return candidate
    suffix = 1
    while True:
        resolved = f"{candidate} [duplicate-{index}-{suffix}]"
        if resolved not in existing:
            return resolved
        suffix += 1


def redact(value: Any, env: Mapping[str, str] | None = None) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            safe_key = _unique_mapping_key(redact_mapping_key(key, env), result, index)
            result[safe_key] = "[REDACTED]" if _is_secret_key(key) else redact(item, env)
        return result
    if isinstance(value, list):
        return [redact(item, env) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item, env) for item in value)
    if isinstance(value, str):
        return redact_text(value, env)
    return value
