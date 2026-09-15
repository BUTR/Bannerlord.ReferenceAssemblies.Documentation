---
title: API reference for game version {{GAME_VERSION}}
---

# Unofficial Bannerlord API Documentation

API reference for Mount &amp; Blade II: Bannerlord, generated from the
[Bannerlord.ReferenceAssemblies](https://github.com/BUTR/Bannerlord.ReferenceAssemblies)
NuGet packages. This is a community project by
[BUTR](https://github.com/BUTR) and is not official TaleWorlds documentation.

## Which game version this is

This copy documents game version **{{GAME_VERSION}}**, built from reference
assembly package `{{PACKAGE_VERSION}}`. {{EDITION}}

Each game version is published separately and keeps its URLs after newer
versions ship. The paths follow the game's own naming: release builds live under
`/v/<version>/` (`/v/1.5.2/`), early access builds under `/e/<version>/`
(`/e/1.5.2/`). What the game contains changes between versions, so the list
below describes {{GAME_VERSION}} rather than a fixed set: modules appear, and
others are dropped. [Compare versions](compare.md) lists what changed in the
public API between any two of them.

## What is documented

{{SECTIONS}}

The client sections document the game as a player runs it. Every assembly is
documented once, in the section of the first client package that ships it.

The dedicated server and the Modding Kit are separate builds of the game. Their
sections hold only what those builds add: assemblies no client package ships,
and the extra types and members in assemblies the client also has. Such a type
appears as a partial page listing the added members and linking to the full
type in its client section. Members the client has but a derived build lacks
are not marked. What the derived builds add in {{GAME_VERSION}}:

{{DELTA}}

Platform integration assemblies (Steam, Epic, GOG, BattlEye), generated
GauntletUI code, and test assemblies are left out.

## Linking to this from your own documentation

Add this version's xrefmap to your `docfx.json`:

    "xref": [ "{{SITE}}/{{VERSION_PATH}}/xrefmap.yml" ]

Game types can then be referenced by UID:

    [`MBSubModuleBase`](xref:TaleWorlds.MountAndBlade.MBSubModuleBase)

The map carries an absolute `baseUrl`, so those links keep resolving to
{{GAME_VERSION}} once later versions are published. Pin the version your mod
targets instead of following the newest one.
