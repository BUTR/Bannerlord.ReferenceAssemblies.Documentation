#!/usr/bin/env python3
"""Reduce the Server and ModdingKit sections to what those builds add.

Runs after `docfx metadata` and before `docfx build`.

The dedicated server and the Modding Kit are separate builds of the game. Their
packages ship most client assemblies again, rebuilt, and a few of those copies
expose members the client build does not (console cheats, editor scene tooling,
server-side lobby state). The generator feeds such a copy to DocFX as part of the
Server or ModdingKit section, so after metadata that section holds the whole
assembly a second time: every type the client already documents, plus the few
additions.

This script removes the repeat. For every type in a derived section:

  * a type the client sections also define loses every member they also define.
    If nothing is left the page is deleted; otherwise it stays as a partial page
    showing only the added members, with a note pointing at the full type;
  * a type the client sections do not define is kept as it is;
  * namespaces are trimmed to the types that survive, and dropped when empty.

Two pages may not share a uid, or cross references land on whichever page DocFX
saw last. DocFX has no option to prefix uids, so a partial type and its
namespace are renamed to "<section>:<uid>" here. Display names are untouched,
and the uids of the added members are not changed because nothing else defines
them, so `<xref:...>` to an added member keeps working. References to the
stripped members and to the type itself are left alone and resolve to the
client's pages, which is where a reader should land.

What the derived builds add is recorded in <docs-dir>/api-delta-summary.json,
which goes into the metadata archive. The landing page's {{DELTA}} paragraph is
rendered from that file later, at render time, so that the page can be
regenerated without the packages:

Usage:  apply-api-delta.py <docs-dir>
        Reads <docs-dir>/api-delta.json, written by generate-docfx-config.py plan.
        Trims the derived sections in place and writes api-delta-summary.json.

        apply-api-delta.py <docs-dir> --fill-from <api-delta-summary.json>
        Fills {{DELTA}} in <docs-dir>/index.md from the summary. Touches nothing
        under api/.
"""

import json
import os
import re
import shutil
import sys

import yaml

try:
    Loader, Dumper = yaml.CSafeLoader, yaml.CSafeDumper
except AttributeError:            # PyYAML built without libyaml
    Loader, Dumper = yaml.SafeLoader, yaml.SafeDumper

# DocFX writes operator names as bare scalars, and a bare "=" is the YAML 1.1
# "value" key indicator, which PyYAML refuses to construct. It is a string here.
Loader.add_constructor("tag:yaml.org,2002:value", lambda loader, node: loader.construct_scalar(node))

MIME = "### YamlMime:ManagedReference\n"
TOC_MIME = "### YamlMime:TableOfContent\n"
UID_LINE = re.compile(r"^- uid: (.+?)\s*$")

# Lists on a type item that describe the whole type rather than the members shown.
# On a partial page they would repeat the client's page, so they go.
WHOLE_TYPE_LISTS = ("inheritedMembers", "derivedClasses", "extensionMethods")


def yml_files(folder):
    for f in sorted(os.listdir(folder)):
        if f.endswith(".yml") and f != "toc.yml":
            yield os.path.join(folder, f)


def scan_primary(api, dests):
    """uid -> section dest for every item the client sections define.

    Line-based on purpose: the client sections are tens of thousands of files
    and only the item uids are needed. Items precede `references:` in every
    ManagedReference file.
    """
    uids = {}
    for dest in dests:
        folder = os.path.join(api, dest)
        if not os.path.isdir(folder):
            continue
        for path in yml_files(folder):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("references:"):
                        break
                    m = UID_LINE.match(line)
                    if m:
                        uids[m.group(1).strip("'\"")] = dest
    return uids


def load(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("### YamlMime:"):
        sys.exit("error: %s is not a DocFX YAML file" % path)
    mime, body = text.split("\n", 1)
    return mime + "\n", yaml.load(body, Loader=Loader)


def save(path, mime, data):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mime)
        yaml.dump(data, fh, Dumper=Dumper, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, width=1 << 20)


def prefixed(dest, uid):
    return "%s:%s" % (dest, uid)


def trim_section(api, dest, title, primary, titles):
    """Strip one derived section in place. Returns per-assembly counts."""
    folder = os.path.join(api, dest)
    renamed = {}            # old uid -> new uid, for partial types and their namespaces
    removed = set()         # type uids whose pages were deleted
    stats = {}              # assembly -> {"types": n, "partial": n, "members": n}
    namespaces = []         # (path, mime, data) handled after the types

    def bump(assembly, key, n=1):
        stats.setdefault(assembly, {"types": 0, "partial": 0, "members": 0})[key] += n

    for path in list(yml_files(folder)):
        mime, data = load(path)
        items = data.get("items") or []
        if not items:
            continue
        head = items[0]
        if head.get("type") == "Namespace":
            namespaces.append((path, mime, data))
            continue
        uid = head["uid"]
        assembly = (head.get("assemblies") or ["?"])[0]
        if uid not in primary:
            bump(assembly, "types")
            continue                                # only this build has the type

        kept = [m for m in items[1:] if m["uid"] not in primary]
        if not kept:
            os.remove(path)
            removed.add(uid)
            continue

        new_uid = prefixed(dest, uid)
        renamed[uid] = new_uid
        owner = titles.get(primary[uid], primary[uid])
        head["uid"] = new_uid
        head["children"] = [m["uid"] for m in kept]
        for key in WHOLE_TYPE_LISTS:
            head.pop(key, None)
        build = title[:-4] if title.endswith(" API") else title
        note = ("Only the members the %s build adds to <xref:%s> are listed here. "
                "The type itself is documented in the %s." % (build, uid, owner))
        head["summary"] = (head.get("summary", "").rstrip() + "\n\n" + note).lstrip()
        for m in kept:
            m["parent"] = new_uid
        data["items"] = [head] + kept
        save(path, mime, data)
        bump(assembly, "partial")
        bump(assembly, "members", len(kept))

    # Namespaces: keep what survived, point at the renamed partial pages.
    for path, mime, data in namespaces:
        head = data["items"][0]
        children = [c for c in head.get("children", []) if c not in removed]
        if not children:
            os.remove(path)
            removed.add(head["uid"])
            continue
        head["children"] = [renamed.get(c, c) for c in children]
        if head["uid"] in primary:
            renamed[head["uid"]] = prefixed(dest, head["uid"])
            head["uid"] = renamed[head["uid"]]
        for ref in data.get("references") or []:
            if ref.get("uid") in renamed:
                ref["uid"] = renamed[ref["uid"]]
        save(path, mime, data)

    # Every surviving type hangs off a namespace, and nested types off a type,
    # that may have been renamed above.
    if renamed:
        for path in yml_files(folder):
            mime, data = load(path)
            head = data["items"][0]
            if head.get("parent") in renamed:
                head["parent"] = renamed[head["parent"]]
                save(path, mime, data)

    toc_path = os.path.join(folder, "toc.yml")
    mime, toc = load(toc_path)

    def trim(entries):
        out = []
        for e in entries:
            if e.get("uid") in removed:
                continue
            if "items" in e:
                e["items"] = trim(e["items"])
                if not e["items"] and e.get("type") == "Namespace":
                    continue
            if e.get("uid") in renamed:
                e["uid"] = renamed[e["uid"]]
            out.append(e)
        return out

    toc["items"] = trim(toc.get("items") or [])
    save(toc_path, mime, toc)

    # Written by metadata for its own incremental use; the build never reads it,
    # and after this pass it names uids that no longer exist.
    manifest = os.path.join(folder, ".manifest")
    if os.path.exists(manifest):
        os.remove(manifest)

    return stats, bool(toc["items"])


def delta_table(results, titles):
    rows = ["| Section | Assembly | Types only this build has | Members added to shared types |",
            "|---|---|---|---|"]
    for dest, stats in results:
        for assembly, s in sorted(stats.items()):
            members = ("%d (on %d %s)" % (s["members"], s["partial"], "type" if s["partial"] == 1 else "types")) if s["partial"] else "0"
            rows.append("| %s | %s | %d | %s |" % (titles[dest], assembly, s["types"], members))
    return "\n".join(rows)


SUMMARY_FILE = "api-delta-summary.json"


def delta_text(summary):
    """The {{DELTA}} paragraph of the landing page, from api-delta-summary.json."""
    results = [(r["dest"], r["stats"]) for r in summary["results"]]
    if any(stats for _, stats in results):
        return delta_table(results, summary["titles"])
    if summary["derived"]:
        return ("Nothing for this version: the Server and ModdingKit builds expose the same public "
                "surface as the client build.")
    return "This version has no Server or ModdingKit package."


def fill_index(docs, summary):
    index = os.path.join(docs, "index.md")
    if not os.path.isfile(index):
        sys.exit("error: %s is missing; run generate-docfx-config.py render first" % index)
    with open(index, encoding="utf-8") as fh:
        body = fh.read()
    if "{{DELTA}}" not in body:
        sys.exit("error: %s has no {{DELTA}} token; was it generated by generate-docfx-config.py render?" % index)
    with open(index, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body.replace("{{DELTA}}", delta_text(summary)))


def trim(docs):
    plan_path = os.path.join(docs, "api-delta.json")
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)
    api = os.path.join(docs, "api")
    titles = {s["dest"]: s["title"] for s in plan["primary"] + plan["derived"]}

    primary = scan_primary(api, [s["dest"] for s in plan["primary"]])
    print("client sections define %d uids" % len(primary))

    results = []
    dropped = []
    for s in plan["derived"]:
        folder = os.path.join(api, s["dest"])
        if not os.path.isdir(folder):
            continue
        stats, nonempty = trim_section(api, s["dest"], s["title"], primary, titles)
        results.append((s["dest"], stats))
        for assembly, c in sorted(stats.items()):
            print("  %-12s %-45s %3d own types, %3d members added on %d shared types"
                  % (s["dest"], assembly, c["types"], c["members"], c["partial"]))
        if not nonempty:
            # Everything in it was already documented by the client sections.
            shutil.rmtree(folder)
            dropped.append(s["dest"])
            print("  %-12s adds nothing over the client build; section removed" % s["dest"])

    if dropped:
        toc_path = os.path.join(api, "toc.yml")
        with open(toc_path, encoding="utf-8") as fh:
            toc = yaml.load(fh, Loader=Loader) or []
        toc = [e for e in toc if e.get("href", "").rstrip("/") not in dropped]
        with open(toc_path, "w", encoding="utf-8", newline="\n") as fh:
            yaml.dump(toc, fh, Dumper=Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False)

    summary = {"titles": titles,
               "derived": [s["dest"] for s in plan["derived"]],
               "dropped": dropped,
               "results": [{"dest": dest, "stats": stats} for dest, stats in results]}
    path = os.path.join(docs, SUMMARY_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("summary written to %s" % path)


def main():
    argv = sys.argv[1:]
    if len(argv) == 3 and argv[1] == "--fill-from":
        with open(argv[2], encoding="utf-8") as fh:
            summary = json.load(fh)
        fill_index(argv[0], summary)
    elif len(argv) == 1:
        trim(argv[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
