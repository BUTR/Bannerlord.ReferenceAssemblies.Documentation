#!/usr/bin/env python3
"""Generate the per-version DocFX inputs: the data side from the packages, the design side from that data.

The module set is not stable across game versions. Multiplayer only appears at
1.2, DedicatedCustomServerHelper disappears after 1.1, FastMode exists only for
1.3 and 1.4, and NavalDLC / Server / ModdingKit are published for far fewer
builds than Core. A config checked in for one version is wrong for the rest, so
all three files are generated per build from what is on disk.

Which file is fed to DocFX for each assembly:

  One copy per assembly.   Every package ships the same assembly under
                           ref/netstandard2.0 and ref/net472 (the packager offers
                           every netstandard assembly under net472 as well), and
                           the Server package adds ref/net6.0. The public surface
                           is identical between those copies, so netstandard2.0 is
                           used and the other folders only supply what it lacks.

  One section per assembly. Where two client packages ship the same assembly
                           (CustomBattle and Multiplayer both carry
                           TaleWorlds.MountAndBlade.Multiplayer) the first section
                           in PRIMARY order owns it. Documenting it twice would put
                           the same type UIDs in two places.

  Server / ModdingKit      repackage the client assemblies, rebuilt for the
                           dedicated server and the editor. Most copies are
                           identical and are skipped; that decision comes from
                           game/api-surface.json, written by the PackageDownloader.
                           A copy whose public surface differs (console cheats,
                           editor scene tooling, server-side lobby state) goes into
                           the Server / ModdingKit section together with the
                           assemblies no client package ships. After metadata,
                           build/apply-api-delta.py removes from those sections
                           every type and member the client sections already
                           document, so they end up holding only what the server
                           or editor build adds. The client pages never show a
                           member the client build does not have. api-delta.json
                           tells that script which sections are which.

  Executables count too.   Core ships a few managed .exe files (the launcher, the
                           code generators), net472 only. DocFX reads them like
                           any assembly. Ones with no public API at all (the code
                           generators) are dropped, which the surface hash tells.

  Excluded everywhere:     platform integration (Steam, Epic, GOG, BattlEye),
                           generated GauntletUI code and test assemblies.

Version ids carry the line of the game as a prefix: "v1.5.2" is the release
build, "e1.5.2" the early access build of the same number. The two are different
games that share numbers, so nothing may ever identify a build by the bare
number alone. A bare "1.5.2" is accepted on input and means the release build.
Early access ships in the *.EarlyAccess packages, so the prefix decides which
package family is read.

Two spellings exist for historical reasons and are derived from the id in one
place each (canonical_id, site_id): the canonical id keeps both prefixes
("v1.5.2", "e1.5.2") and names the metadata release and the workflow matrix;
the site id drops the v ("1.5.2", "e1.5.2") because the docs host, the version
picker and the page titles predate the prefix and use it as the release build's
name. On the site a release build lives under /v/1.5.2/ and an early access
build under /e/1.5.2/.

docfx-globals.json carries the site metadata that cannot be checked in as a
constant: the copyright range ends at the year the build runs. A published
version keeps the year it was generated, because the render fingerprint does
not include the date; only a forced rebuild moves it forward.

Two subcommands, matching the two halves of the pipeline:

  plan <game-dir> <docs-dir> --version <x.y.z|ex.y.z>
        Needs the downloaded packages. Writes docfx-meta.json, api-delta.json,
        api/toc.yml and version.json. version.json records what the render step
        needs to know about the version (edition, package build, sections and
        their assembly counts) so that the landing page can be produced later
        from the archived metadata alone. Everything this writes is data about
        the game and goes into the metadata archive.

  render <docs-dir> [--site <origin>]
        Needs only the extracted archive. Reads version.json and api/toc.yml
        and writes index.md (except {{DELTA}}, see apply-api-delta.py
        --fill-from) and docfx-globals.json. Everything this writes is design
        and is regenerated on every render.
"""

import argparse
import datetime
import json
import os
import shutil
import sys

PREFIX = "bannerlord.referenceassemblies"

# The repository's first commit, and so the first year of the documentation.
FIRST_YEAR = 2020

# Package suffix -> (api/<dest>, TOC title). Order is both the TOC order and the
# claim order: the first section listing an assembly documents it. Multiplayer
# precedes CustomBattle so that TaleWorlds.MountAndBlade.Multiplayer lands in the
# Multiplayer section whenever that package exists (1.2+), and falls back to
# CustomBattle for the older versions that only shipped it there.
PRIMARY = [
    ("core",                        "core",                        "Core API"),
    ("native",                      "native",                      "Native API"),
    ("sandbox",                     "sandbox",                     "SandBox API"),
    ("storymode",                   "storymode",                   "StoryMode API"),
    ("multiplayer",                 "multiplayer",                 "Multiplayer API"),
    ("custombattle",                "custombattle",                "CustomBattle API"),
    ("birthanddeath",               "birthanddeath",               "BirthAndDeath API"),
    ("navaldlc",                    "navaldlc",                    "NavalDLC API"),
    ("fastmode",                    "fastmode",                    "FastMode API"),
    ("dedicatedcustomserverhelper", "dedicatedcustomserverhelper", "DedicatedCustomServerHelper API"),
]

# Packages that repackage the client assemblies for another application.
DERIVED = [
    ("server.core",     "server",     "Server API"),
    ("moddingkit.core", "moddingkit", "ModdingKit API"),
]

# Target framework folders in order of preference. Anything not listed is still
# used, after these, for assemblies that exist nowhere else (Server ships six
# net6.0-only assemblies).
TFM_PREFERENCE = ["netstandard2.0", "net472"]

EXCLUDED_MARKERS = (".AutoGenerated", ".BattlEye", ".Steam", ".Epic", ".GOG", ".Test")

SURFACE_FILE = "api-surface.json"

# Written by `plan`, read by `render`: what render needs to know about the version.
VERSION_FILE = "version.json"

ASSEMBLY_EXTENSIONS = (".dll", ".exe")

# sha256 of the empty string: the hash ApiSurface gives an assembly with no public types.
EMPTY_SURFACE = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def excluded(name):
    return any(m in name for m in EXCLUDED_MARKERS)


def parse_version_id(vid):
    """'v1.5.2' or '1.5.2' -> ('1.5.2', False); 'e1.5.2' -> ('1.5.2', True)."""
    if vid.startswith("e"):
        number, early_access = vid[1:], True
    elif vid.startswith("v"):
        number, early_access = vid[1:], False
    else:
        number, early_access = vid, False
    if not number or not number[0].isdigit():
        sys.exit("error: version id %r must be vX.Y.Z, eX.Y.Z or X.Y.Z" % vid)
    return number, early_access


def canonical_id(vid):
    """The prefixed id: 'v1.5.2' for release, 'e1.5.2' for early access."""
    number, early_access = parse_version_id(vid)
    return ("e" if early_access else "v") + number


def site_id(vid):
    """The id the docs host and the pages use: '1.5.2' for release, 'e1.5.2' for early access."""
    number, early_access = parse_version_id(vid)
    return ("e" if early_access else "") + number


def version_path(vid):
    """The site path a version id is published under: v/1.5.2 or e/1.5.2."""
    number, early_access = parse_version_id(vid)
    return ("e/" if early_access else "v/") + number


def package_dir(game, suffix, early_access=False):
    """game/<package>/<build>/ for the single build the downloader left, or None."""
    pkg = os.path.join(game, PREFIX + "." + suffix + (".earlyaccess" if early_access else ""))
    if not os.path.isdir(pkg):
        return None
    builds = [d for d in os.listdir(pkg) if os.path.isdir(os.path.join(pkg, d))]
    if not builds:
        return None
    if len(builds) > 1:
        sys.exit("error: %s holds %d builds (%s); expected exactly one"
                 % (pkg, len(builds), ", ".join(sorted(builds))))
    return os.path.join(pkg, builds[0])


def tfm_order(tfm):
    if tfm in TFM_PREFERENCE:
        return (0, TFM_PREFERENCE.index(tfm), tfm)
    return (1, 0, tfm)


def assemblies(build_dir):
    """Assembly name -> path of the preferred copy, one per name.

    Prefers ref/netstandard2.0, then ref/net472, then any other ref/<tfm> folder
    in name order. Excluded assemblies are dropped here so that every caller sees
    the same set.
    """
    ref = os.path.join(build_dir, "ref")
    if not os.path.isdir(ref):
        return {}
    found = {}
    for tfm in sorted(os.listdir(ref), key=tfm_order):
        folder = os.path.join(ref, tfm)
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            if f.endswith(ASSEMBLY_EXTENSIONS):
                found.setdefault(f[:-4], os.path.join(folder, f))
    return {n: p for n, p in found.items() if not excluded(n)}


def load_surfaces(game):
    """Relative dll path -> public surface hash, or None when the downloader did not write it."""
    path = os.path.join(game, SURFACE_FILE)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {os.path.normpath(k): v for k, v in data.items()}


def surface_of(surfaces, game, path):
    return surfaces.get(os.path.normpath(os.path.relpath(path, game)))


def docfx_src(docs, game):
    """The `src` a metadata item needs so that its `files` can be game-relative.

    DocFX's glob matcher does not resolve `..` segments inside `files`, so the
    step out of docs/ has to happen in `src` (as the old hand-written config did)
    and every file pattern is then relative to the game directory.
    """
    return os.path.relpath(game, docs).replace(os.sep, "/")


def game_path(game, path):
    return os.path.relpath(path, game).replace(os.sep, "/")


def write_globals(docs, game_version):
    """Site metadata that cannot be a checked-in constant.

    The copyright range ends at the current year rather than at a hard-coded one,
    which had gone stale, and rather than at the word "present", which names no
    period at all. BUTR's copyright covers this site: its template, its prose and
    the arrangement of the generated pages. The documented API belongs to
    TaleWorlds, hence the disclaimer.

    _appTitle carries the version because it is the suffix of every page title.
    Without it every version produces identical titles, and a reader comparing two
    versions in two tabs cannot tell them apart. It keeps "Unofficial" as well,
    because a search result for a game type should not read as TaleWorlds' own
    documentation.
    """
    year = datetime.datetime.now(datetime.timezone.utc).year
    span = str(FIRST_YEAR) if year <= FIRST_YEAR else "%d-%d" % (FIRST_YEAR, year)
    footer = ('&copy; %s <a href="https://github.com/BUTR">BUTR</a> '
              "(Bannerlord's Unofficial Tools &amp; Resources). "
              "Not affiliated with TaleWorlds Entertainment." % span)
    path = os.path.join(docs, "docfx-globals.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"_appTitle": "Unofficial Bannerlord API " + game_version,
                   "_appFooter": footer}, fh, indent=2)
        fh.write("\n")
    return span


def write_index(docs, sections, pkg_version, vid, site):
    """Fill the landing page, except {{DELTA}}: what the Server and ModdingKit
    builds add is summarised by build/apply-api-delta.py, which fills that token
    from api-delta-summary.json (`--fill-from`).

    {{GAME_VERSION}} is the site id (1.5.2 or e1.5.2), the name readers know a
    build by; {{VERSION_PATH}} is v/1.5.2 or e/1.5.2."""
    _, early_access = parse_version_id(vid)
    game_version = site_id(vid)
    template = os.path.join(docs, "index.template.md")
    if not os.path.isfile(template):
        sys.exit("error: %s is missing; the landing page cannot be generated" % template)
    with open(template, encoding="utf-8") as fh:
        body = fh.read()
    if "{{DELTA}}" not in body:
        sys.exit("error: %s has no {{DELTA}} token for apply-api-delta.py to fill" % template)

    rows = ["| Section | Assemblies |", "|---|---|"]
    for s in sections:
        rows.append("| %s | %d |" % (s["title"], s["own"]))

    if early_access:
        edition = ("This is the **early access** build, documented separately from the release "
                   "build of the same number.")
    else:
        edition = "This is the release build."

    for token, value in (("{{GAME_VERSION}}", game_version),
                         ("{{PACKAGE_VERSION}}", pkg_version),
                         ("{{EDITION}}", edition),
                         ("{{VERSION_PATH}}", version_path(vid)),
                         ("{{SECTIONS}}", "\n".join(rows)),
                         ("{{SITE}}", site.rstrip("/"))):
        body = body.replace(token, value)

    with open(os.path.join(docs, "index.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


def load_version(docs):
    path = os.path.join(docs, VERSION_FILE)
    if not os.path.isfile(path):
        sys.exit("error: %s is missing; was the metadata archive extracted into %s?" % (path, docs))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def surviving_sections(docs, sections):
    """The sections still listed in api/toc.yml.

    apply-api-delta.py removes a derived section that adds nothing over the
    client build, and the landing page must not list a section that has no
    pages. api/toc.yml is in the archive after that pass, so it is the record
    of what survived.
    """
    toc = os.path.join(docs, "api", "toc.yml")
    if not os.path.isfile(toc):
        sys.exit("error: %s is missing; was the metadata archive extracted into %s?" % (toc, docs))
    dests = set()
    with open(toc, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("href: "):
                dests.add(line[len("href: "):].strip().rstrip("/"))
    return [s for s in sections if s["dest"] in dests]


def cmd_render(args):
    docs = args.docs
    info = load_version(docs)
    vid = info.get("id")
    if not vid:
        sys.exit("error: %s has no id; the archive predates the v/e version ids and must be re-extracted" % VERSION_FILE)
    sections = surviving_sections(docs, info["sections"])
    if not sections:
        sys.exit("error: none of the sections in %s appear in api/toc.yml" % VERSION_FILE)
    write_index(docs, sections, info["package_version"], vid, args.site)
    span = write_globals(docs, site_id(vid))
    print("game version %s (%s, package %s), copyright %s, %d sections on the landing page"
          % (vid, info["edition"], info["package_version"], span, len(sections)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="from the downloaded packages, write the data side: "
                                       "docfx-meta.json, api-delta.json, api/toc.yml, version.json")
    plan.add_argument("game", help="directory the PackageDownloader extracted the packages into")
    plan.add_argument("docs", help="the DocFX project directory (holds docfx-build.json)")
    plan.add_argument("--version", required=True, metavar="X.Y.Z",
                      help="game version being built, x.y.z for release or ex.y.z for early access; "
                           "it names the /v/<version>/ tree the site publishes")
    plan.set_defaults(func=cmd_plan)

    render = sub.add_parser("render", help="from the extracted archive, write the design side: "
                                           "index.md and docfx-globals.json")
    render.add_argument("docs", help="the DocFX project directory the archive was extracted into")
    render.add_argument("--site", default="https://bannerlordapi.butr.link",
                        help="site origin used in the xref instructions on the landing page")
    render.set_defaults(func=cmd_render)

    args = ap.parse_args()
    args.func(args)


def cmd_plan(args):
    game, docs = args.game, args.docs
    number, early_access = parse_version_id(args.version)

    core = package_dir(game, "core", early_access)
    if core is None:
        sys.exit("error: %s.core%s was not downloaded under %s; nothing can be built without it"
                 % (PREFIX, ".earlyaccess" if early_access else "", game))
    pkg_version = os.path.basename(core)
    if ".".join(pkg_version.split("-")[0].split(".")[:3]) != number:
        sys.exit("error: --version %s does not match the downloaded core package %s"
                 % (args.version, pkg_version))

    surfaces = load_surfaces(game)
    if surfaces is None:
        print("warning: %s not found; Server and ModdingKit copies of shared assemblies will not be merged"
              % os.path.join(game, SURFACE_FILE), file=sys.stderr)
        surfaces = {}

    sections = []       # {"dest", "title", "files": [paths], "own": count of assemblies it documents}
    owner = {}          # assembly name -> (dest, path)

    for suffix, dest, title in PRIMARY:
        build_dir = package_dir(game, suffix, early_access)
        if build_dir is None:
            continue
        files = []
        for name, path in sorted(assemblies(build_dir).items()):
            if name in owner:
                continue      # another client package already documents it
            if surface_of(surfaces, game, path) == EMPTY_SURFACE:
                continue      # nothing public in it (the code generator executables)
            owner[name] = (dest, path)
            files.append(path)
        if files:             # metapackage, or everything in it is excluded
            sections.append({"dest": dest, "title": title, "files": files, "own": len(files)})

    primary_sections = list(sections)
    derived_sections = []
    shared = {}           # derived dest -> [assembly names whose differing copy is documented there]

    for suffix, dest, title in DERIVED:
        build_dir = package_dir(game, suffix, early_access)
        if build_dir is None:
            continue
        own, differing = [], []
        for name, path in sorted(assemblies(build_dir).items()):
            if surface_of(surfaces, game, path) == EMPTY_SURFACE:
                continue
            if name not in owner:
                own.append(path)
                continue
            _, owner_path = owner[name]
            a, b = surface_of(surfaces, game, owner_path), surface_of(surfaces, game, path)
            if a is None or b is None or a == b:
                # Same public surface as the client build, or no data to tell: nothing
                # to add, and extracting a large assembly twice blindly is not worth it.
                continue
            differing.append(path)
            shared.setdefault(dest, []).append(name)
        if own or differing:
            section = {"dest": dest, "title": title, "files": own + differing, "own": len(own)}
            sections.append(section)
            derived_sections.append(section)

    if not sections:
        sys.exit("error: no documentable assemblies found under " + game)

    meta = [{"src": [{"src": docfx_src(docs, game), "files": [game_path(game, p) for p in s["files"]]}],
             "dest": "api/" + s["dest"]}
            for s in sections]
    with open(os.path.join(docs, "docfx-meta.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"metadata": meta}, fh, indent=2)
        fh.write("\n")

    # Read by build/apply-api-delta.py after metadata: which sections document the
    # client build and which the derived builds whose repeats it has to remove.
    with open(os.path.join(docs, "api-delta.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"primary": [{"dest": s["dest"], "title": s["title"]} for s in primary_sections],
                   "derived": [{"dest": s["dest"], "title": s["title"], "shared": shared.get(s["dest"], [])}
                               for s in derived_sections]}, fh, indent=2)
        fh.write("\n")

    api = os.path.join(docs, "api")
    os.makedirs(api, exist_ok=True)
    # Output of a previous run would otherwise leak into this one: `docfx metadata`
    # writes into an existing section folder without removing the files a
    # previous version left there, and the build glob then picks them up. Only
    # ever happens locally; CI starts clean.
    for d in os.listdir(api):
        if os.path.isdir(os.path.join(api, d)):
            shutil.rmtree(os.path.join(api, d))
            print("removed previous api/%s" % d)
    with open(os.path.join(api, "toc.yml"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join("- name: %s\n  href: %s/\n" % (s["title"], s["dest"]) for s in sections))

    # What `render` needs later, without the packages: which build this is, in
    # every spelling the pipeline uses, which sections exist and how many
    # assemblies each documents.
    with open(os.path.join(docs, VERSION_FILE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"id": canonical_id(args.version),
                   "site_id": site_id(args.version),
                   "game": number,
                   "edition": "early-access" if early_access else "release",
                   "package_version": pkg_version,
                   "sections": [{"dest": s["dest"], "title": s["title"], "own": s["own"]} for s in sections]},
                  fh, indent=2)
        fh.write("\n")

    print("game version %s (%s, package %s), %d sections:"
          % (canonical_id(args.version), "early access" if early_access else "release", pkg_version, len(sections)))
    for s in sections:
        extra = len(s["files"]) - s["own"]
        note = "  (+%d client assemblies whose copy differs; reduced to the additions after metadata)" % extra if extra else ""
        print("  %-34s api/%-12s %3d assemblies%s" % (s["title"], s["dest"], s["own"], note))
    for dest, names in sorted(shared.items()):
        print("  %s differs from the client build in: %s" % (dest, ", ".join(names)))


if __name__ == "__main__":
    main()
