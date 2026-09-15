#!/usr/bin/env python3
"""Write _site/api-index.json: every documented type and member of the version just built.

compare.html (public/compare.js) fetches this file for two versions and diffs
them in the browser, so what changed between two game releases can be read off
the documentation instead of a decompiler. Each version publishes its own index
under /v/<version>/ or /e/<version>/, next to its pages; nothing has to be
recomputed when a new version ships, and two versions built years apart compare
the same way.

Runs after `docfx build`, from the same api/**.yml the build consumed, so it
sees exactly what the pages show, including the Server and ModdingKit sections
after build/apply-api-delta.py reduced them to their additions.

Format, kept small because the Core section alone holds tens of thousands of
members:

  {
    "version": "1.4.8",
    "sections": {"core": "Core API", ...},
    "types": {
      "<type uid>": {
        "k": "Class",                       kind
        "n": "TaleWorlds.Core",             namespace
        "s": "core",                        section, a key of "sections"
        "a": "TaleWorlds.Core",             assembly
        "h": "api/core/TaleWorlds.Core.Game.html",
        "d": "3f9a1c2e",                    hash of the type's own declaration
        "m": {"<member id>": "<hash of the member's declaration>", ...}
      }
    }
  }

A member id is the member's uid with the type's uid and the dot removed
("Start(System.Boolean)", "#ctor", "Name"); the full uid is recoverable, and
the page needs it for the anchor. A partial type from a derived section keeps
its "<section>:" uid prefix so it never collides with the client's copy.

The declaration hash covers DocFX's `syntax.content` with the attribute lines
removed: modifiers, return type, parameters, base type and interfaces. Those
are what a compiled mod is bound to, so a different hash for the same uid is a
binary-breaking change. An attribute that comes or goes is not, and does not
change the hash.

Usage:  write-api-index.py <docs-dir> <version-id>
"""

import hashlib
import json
import os
import re
import sys

import yaml

try:
    Loader = yaml.CSafeLoader
except AttributeError:
    Loader = yaml.SafeLoader
Loader.add_constructor("tag:yaml.org,2002:value", lambda loader, node: loader.construct_scalar(node))

SECTION_PREFIX = re.compile(r"^[a-z]+:")


def digest(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:8]


def declaration(syntax):
    """The C# declaration without its attribute lines."""
    content = (syntax or {}).get("content") or ""
    return "\n".join(l for l in content.splitlines() if l.strip() and not l.lstrip().startswith("["))


def section_titles(api):
    """dest -> title from api/toc.yml (`- name: Core API` / `  href: core/`)."""
    titles, name = {}, None
    with open(os.path.join(api, "toc.yml"), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("- name: "):
                name = line[len("- name: "):].strip()
            elif line.startswith("  href: ") and name:
                titles[line[len("  href: "):].strip().rstrip("/")] = name
    return titles


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    docs, version = sys.argv[1], sys.argv[2]
    api, site = os.path.join(docs, "api"), os.path.join(docs, "_site")
    if not os.path.isdir(site):
        sys.exit("error: %s does not exist; run this after `docfx build`" % site)

    titles = section_titles(api)
    types = {}
    for dest in sorted(titles):
        folder = os.path.join(api, dest)
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            if not f.endswith(".yml") or f == "toc.yml":
                continue
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                body = fh.read().split("\n", 1)[1]
            items = (yaml.load(body, Loader=Loader) or {}).get("items") or []
            if not items or items[0].get("type") == "Namespace":
                continue
            head = items[0]
            uid = head["uid"]
            base = SECTION_PREFIX.sub("", uid)
            members = {}
            for m in items[1:]:
                mid = m["uid"]
                if mid.startswith(base + "."):
                    mid = mid[len(base) + 1:]
                members[mid] = digest(declaration(m.get("syntax")))
            types[uid] = {
                "k": head.get("type"),
                "n": head.get("namespace"),
                "s": dest,
                "a": (head.get("assemblies") or [None])[0],
                "h": "api/%s/%s.html" % (dest, f[:-4]),
                "d": digest(declaration(head.get("syntax"))),
                "m": members,
            }

    out = os.path.join(site, "api-index.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"version": version, "sections": titles, "types": types}, fh,
                  separators=(",", ":"), ensure_ascii=False)
    members = sum(len(t["m"]) for t in types.values())
    print("api-index.json: %d types, %d members, %s" % (len(types), members, sizeof(out)))


def sizeof(path):
    n = os.path.getsize(path)
    return "%.1f MB" % (n / 1048576) if n >= 1048576 else "%d KB" % (n // 1024)


if __name__ == "__main__":
    main()
