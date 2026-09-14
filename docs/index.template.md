# Unofficial Bannerlord API Documentation

API reference for Mount &amp; Blade II: Bannerlord, generated from the
[Bannerlord.ReferenceAssemblies](https://github.com/BUTR/Bannerlord.ReferenceAssemblies)
NuGet packages. This is a community project by
[BUTR](https://github.com/BUTR) and is not official TaleWorlds documentation.

## Which game version this is

This copy documents game version **{{GAME_VERSION}}**, built from reference
assembly package `{{PACKAGE_VERSION}}`.

Each game version is published separately under `/v/<version>/` and keeps its
URLs after newer versions ship. What the game contains changes between versions,
so the list below describes {{GAME_VERSION}} rather than a fixed set: modules
appear, and some are removed again.

## What is documented

{{SECTIONS}}

An assembly that ships in more than one package is documented once. The Server
and ModdingKit sections therefore cover only what no other section already does.

Platform integration assemblies (Steam, Epic, GOG, BattleEye), generated
GauntletUI code, and test assemblies are left out.

## Linking to this from your own documentation

Add this version's xrefmap to your `docfx.json`:

    "xref": [ "{{SITE}}/v/{{GAME_VERSION}}/xrefmap.yml" ]

Game types can then be referenced by UID:

    [`MBSubModuleBase`](xref:TaleWorlds.MountAndBlade.MBSubModuleBase)

The map carries an absolute `baseUrl`, so those links keep resolving to
{{GAME_VERSION}} once later versions are published. Pin the version your mod
targets instead of following the newest one.
