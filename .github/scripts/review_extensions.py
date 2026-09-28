#!/usr/bin/env python3
"""Automated reviewer for Aether extension registry pull requests.

Reads the PR's index.json and changed .aex packages and checks them against
the same rules the launcher enforces at install time (plus registry policy).
Never executes extension code - manifest.json is only parsed as data.

Usage:
    review_extensions.py --root <repo checkout at PR head>
        --base-index <index.json from base branch>
        --changed <space-separated list of changed repo-relative paths>
        --pr-author <github login> --repo-owner <github login>
        --out <markdown report path>

Exit code 0 = pass, 1 = fail. Always writes the markdown report.
"""

import argparse
import json
import os
import re
import sys
import zipfile

# Permissions the launcher actually honors (pkg/extensions in Aether core).
# extension:confirmation / instance:* are event names, not permissions.
ALLOWED_PERMISSIONS = {
    "ui:sidebar",
    "ui:dialogs",
    "instances:list",
    "instances:patch",  # legacy, still accepted by the launcher
    "mods:list",
    "mods:install",
    "mods:delete",
    "mods:toggle",
    "modpacks:install",
    "resourcepacks:install",
    "shaderpacks:install",
    "screenshots:read",
    "screenshots:write",
    "network:http",
    "fs:download",
    "launcher:modloader",
    "skin:export",
    "discord:presence",
}

# Permissions that deserve an explicit heads-up in the review (not failures).
SENSITIVE_PERMISSIONS = {
    "mods:delete",
    "mods:toggle",
    "fs:download",
    "network:http",
    "instances:patch",
    "launcher:modloader",
}

ALLOWED_TRUST = {"official", "verified", "community"}

ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_CSS_BYTES = 256 * 1024

INDEX_URL_PREFIX = (
    "https://raw.githubusercontent.com/Aether-Launcher/Aether-Extensions/main/"
)


def ver_tuple(v):
    """Parse '1.2.3' (leading v tolerated) into a comparable tuple."""
    m = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(v or "").strip())
    if not m:
        return None
    return tuple(int(g or 0) for g in m.groups())


class Review:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.infos = []
        self.checked_packages = 0

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def passed(self):
        return not self.errors

    def report(self):
        lines = ["<!-- aether-extension-review -->", "## Extension Review"]
        if self.passed():
            lines.append("")
            lines.append("**PASS** — all automated checks passed. Safe to auto-merge.")
        else:
            lines.append("")
            lines.append("**FAIL** — %d blocking issue(s). Auto-merge skipped." % len(self.errors))
        if self.errors:
            lines.append("")
            lines.append("### Blocking")
            lines += ["- " + e for e in self.errors]
        if self.warnings:
            lines.append("")
            lines.append("### Warnings (non-blocking)")
            lines += ["- " + w for w in self.warnings]
        if self.infos:
            lines.append("")
            lines.append("### Notes")
            lines += ["- " + i for i in self.infos]
        lines.append("")
        lines.append("_Checked %d package(s). Reviewer never executes extension code._" % self.checked_packages)
        return "\n".join(lines) + "\n"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_index(review, head_entries, base_by_id, pr_author, repo_owner):
    if not isinstance(head_entries, list):
        review.error("index.json must be a JSON array")
        return {}
    seen = set()
    head_by_id = {}
    is_owner = pr_author == repo_owner
    for i, e in enumerate(head_entries):
        where = "index.json[%d]" % i
        if not isinstance(e, dict):
            review.error("%s: entry must be an object" % where)
            continue
        for field in ("id", "name", "version", "author", "description", "url"):
            if not e.get(field):
                review.error("%s: missing required field %r" % (where, field))
        eid = e.get("id", "")
        if eid in seen:
            review.error("%s: duplicate id %r" % (where, eid))
        seen.add(eid)
        head_by_id[eid] = e

        if eid and not ID_RE.match(eid):
            review.error("%s: id %r must match ^[a-zA-Z0-9._-]+$" % (where, eid))

        trust = str(e.get("trust", "")).lower()
        if trust not in ALLOWED_TRUST:
            review.error("%s: trust %r must be one of official/verified/community" % (where, e.get("trust")))
            continue

        url = e.get("url", "")
        if url and not url.startswith(INDEX_URL_PREFIX):
            review.error("%s: url must start with %s" % (where, INDEX_URL_PREFIX))

        base = base_by_id.get(eid)
        if base is None:
            # New entry: only the repo owner may claim official/verified.
            if trust in ("official", "verified") and not is_owner:
                review.error(
                    "%s: new entry %r claims trust %r, but only %r may do that — use \"community\""
                    % (where, eid, trust, repo_owner)
                )
            else:
                review.info("%s: new entry %r (%s)" % (where, eid, trust))
        else:
            # Existing entry: version must not go backwards.
            old_v, new_v = ver_tuple(base.get("version")), ver_tuple(e.get("version"))
            if old_v is not None and new_v is not None and new_v < old_v:
                review.error(
                    "%s: version downgrade for %r (%s -> %s)" % (where, eid, base.get("version"), e.get("version"))
                )
            # Trust escalation by non-owners is blocked.
            old_trust = str(base.get("trust", "")).lower()
            if trust != old_trust and trust in ("official", "verified") and not is_owner:
                review.error(
                    "%s: trust escalation for %r (%s -> %s) requires a maintainer"
                    % (where, eid, old_trust, trust)
                )
    return head_by_id


def find_manifest(zf):
    """Locate manifest.json, tolerating a single root folder wrapper."""
    cands = [n for n in zf.namelist() if n.replace("\\", "/").rstrip("/").endswith("manifest.json")]
    if not cands:
        return None
    # Prefer the shallowest match.
    cands.sort(key=lambda n: n.count("/"))
    return cands[0]


def check_package(review, root, relpath, head_by_id):
    review.checked_packages += 1
    where = relpath
    path = os.path.join(root, relpath)
    if not os.path.isfile(path):
        review.error("%s: file referenced by PR does not exist in checkout" % where)
        return
    is_sample = os.path.basename(relpath).startswith("com.example.")
    if is_sample:
        review.info("%s: sample package, registry cross-checks skipped" % where)

    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        review.error("%s: not a valid zip archive" % where)
        return
    with zf:
        # ZipSlip simulation: reject absolute paths and .. escapes.
        total = 0
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                review.error("%s: unsafe zip entry %r (path traversal)" % (where, info.filename))
                return
            total += info.file_size
            if info.file_size > MAX_FILE_BYTES and not info.is_dir():
                review.error(
                    "%s: file %r exceeds 20 MiB (%d bytes)" % (where, info.filename, info.file_size)
                )
                return
        if total > MAX_TOTAL_BYTES:
            review.error("%s: archive contents exceed 50 MiB (%d bytes)" % (where, total))
            return

        mname = find_manifest(zf)
        if mname is None:
            review.error("%s: manifest.json not found in archive" % where)
            return
        try:
            manifest = json.loads(zf.read(mname).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            review.error("%s: manifest.json is not valid JSON/UTF-8: %s" % (where, exc))
            return
        if not isinstance(manifest, dict):
            review.error("%s: manifest.json must be an object" % where)
            return

        mid = manifest.get("id", "")
        mver = manifest.get("version", "")
        if not mid or not ID_RE.match(str(mid)):
            review.error("%s: manifest id %r is missing or invalid" % (where, mid))
            return
        if not manifest.get("name"):
            review.error("%s: manifest is missing 'name'" % where)
        if not mver:
            review.error("%s: manifest is missing 'version'" % where)
        main = manifest.get("main", "")
        if not main:
            review.error("%s: manifest is missing 'main'" % where)
        else:
            root_prefix = mname.rpartition("/")[0]
            main_path = (root_prefix + "/" + main).lstrip("/") if root_prefix else main
            if main_path not in zf.namelist():
                review.error("%s: main script %r not found in archive" % (where, main))

        # Filename must be <id>-<version>.aex and match the manifest.
        # The id part is a warning only: the registry has precedent for
        # differing names (e.g. discord-presence-1.0.1.aex ships manifest id
        # aether.discord-presence), and the launcher keys off manifest id.
        base = os.path.basename(relpath)
        m = re.match(r"^(.+)-([0-9][0-9A-Za-z.\-]*)\.aex$", base)
        if not m:
            review.error("%s: filename must look like <id>-<version>.aex" % where)
        else:
            if m.group(1) != str(mid):
                review.warn(
                    "%s: filename id %r does not match manifest id %r" % (where, m.group(1), mid)
                )
            if m.group(2) != str(mver):
                review.error(
                    "%s: filename version %r does not match manifest version %r" % (where, m.group(2), mver)
                )

        # Permissions: must all be known; flag sensitive ones.
        perms = manifest.get("permissions", [])
        if not isinstance(perms, list):
            review.error("%s: manifest 'permissions' must be an array" % where)
            perms = []
        unknown = [p for p in perms if p not in ALLOWED_PERMISSIONS]
        if unknown:
            review.error("%s: unknown permission(s): %s" % (where, ", ".join(map(str, unknown))))
        sensitive = sorted(set(map(str, perms)) & SENSITIVE_PERMISSIONS)
        if sensitive:
            review.warn("%s: requests sensitive permission(s): %s" % (where, ", ".join(sensitive)))
        if "network:http" in perms and not manifest.get("hosts"):
            review.warn("%s: declares network:http but no 'hosts' allow-list" % where)

        # Cross-check against index.json (skipped for com.example.* samples).
        if not is_sample:
            entry = head_by_id.get(str(mid))
            if entry is None:
                review.error(
                    "%s: manifest id %r has no matching entry in index.json" % (where, mid)
                )
            else:
                if str(entry.get("version", "")) != str(mver):
                    review.error(
                        "%s: manifest version %r does not match index.json version %r"
                        % (where, mver, entry.get("version"))
                    )
                # The index URL for this entry must point at this exact file.
                want_url = INDEX_URL_PREFIX + base
                if entry.get("url") != want_url:
                    review.error(
                        "%s: index.json url should be %r" % (where, want_url)
                    )

        # Icon field inside the package, if declared, must exist.
        icon = manifest.get("icon")
        if icon:
            root_prefix = mname.rpartition("/")[0]
            icon_path = (root_prefix + "/" + icon).lstrip("/") if root_prefix else icon
            if icon_path not in zf.namelist():
                review.warn("%s: manifest icon %r not found in archive" % (where, icon))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="repo checkout at PR head")
    ap.add_argument("--base-index", required=True, help="index.json from base branch")
    ap.add_argument("--changed", default="", help="space-separated changed paths")
    ap.add_argument("--pr-author", default="", help="PR author login")
    ap.add_argument("--repo-owner", default="", help="repo owner login")
    ap.add_argument("--out", required=True, help="markdown report output path")
    args = ap.parse_args()

    review = Review()

    try:
        head_entries = load_json(os.path.join(args.root, "index.json"))
    except (OSError, json.JSONDecodeError) as exc:
        review.error("index.json: cannot load: %s" % exc)
        head_entries = []
    try:
        base_entries = load_json(args.base_index)
    except (OSError, json.JSONDecodeError):
        base_entries = []
    base_by_id = {e["id"]: e for e in base_entries if isinstance(e, dict) and e.get("id")}

    head_by_id = check_index(review, head_entries, base_by_id, args.pr_author, args.repo_owner)

    # Stale packages: versioned .aex files in the repo that no index entry
    # points at. Old versions should be removed when a release bumps the
    # index, otherwise the registry accumulates dead weight. Samples and
    # unlisted one-offs are exempt.
    referenced = set()
    for e in head_by_id.values():
        url = e.get("url", "")
        if url.startswith(INDEX_URL_PREFIX):
            referenced.add(url[len(INDEX_URL_PREFIX):])
    for fname in sorted(os.listdir(args.root)):
        if not fname.endswith(".aex"):
            continue
        if fname in referenced or fname.startswith("com.example."):
            continue
        if re.match(r"^.+-[0-9][0-9A-Za-z.\-]*\.aex$", fname):
            review.warn(
                "%s: not referenced by any index.json url — delete it if superseded" % fname
            )

    # Registry iconUrl targets must exist in the repo.
    for eid, e in head_by_id.items():
        icon_url = e.get("iconUrl", "")
        if icon_url and icon_url.startswith(INDEX_URL_PREFIX + "icons/"):
            icon_file = icon_url[len(INDEX_URL_PREFIX):]
            if not os.path.isfile(os.path.join(args.root, icon_file.replace("/", os.sep))):
                review.error("index.json entry %r: iconUrl target %r missing from repo" % (eid, icon_file))

    changed = [c for c in args.changed.split() if c]
    packages = sorted({c for c in changed if c.lower().endswith(".aex")})
    for rel in packages:
        check_package(review, args.root, rel, head_by_id)

    if not packages:
        review.info("No .aex packages changed in this PR.")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(review.report())

    print(review.report())
    return 0 if review.passed() else 1


if __name__ == "__main__":
    sys.exit(main())
