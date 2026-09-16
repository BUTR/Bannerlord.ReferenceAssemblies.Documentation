# Bannerlord.ReferenceAssemblies.Documentation

API documentation for Mount & Blade II: Bannerlord, generated with DocFX from the
[Bannerlord.ReferenceAssemblies](https://github.com/BUTR/Bannerlord.ReferenceAssemblies)
NuGet packages.

Live site: https://bannerlordapi.butr.link/

Every game version is published under `/v/<version>/` (release) or `/e/<version>/`
(early access), and the site root serves the current stable version. Each version
ships an `xrefmap.yml` that other DocFX projects can reference; see the landing
page of any version for details.

## How it is built

The pipeline is split in two, and the two halves meet at a GitHub release:

The Metadata workflow ([metadata.yml](.github/workflows/metadata.yml)) is the half
that depends on the game. For each game version it resolves the highest package
build on NuGet, runs `docfx metadata` and the delta pass that reduces the Server
and ModdingKit sections to what those builds add, and publishes the result as the
release `meta/<id>`. The id always names the line of the game: `v1.5.1` is the
release build, `e1.5.1` the early access build of the same number. A bare `1.5.1`
given to either workflow means the release build. The release holds
`manifest.json` and one archive; the manifest's `pkgs` field hashes the package
builds the archive was made from. When a newer build ships under the same game
version the archive is replaced, so a release only ever holds the latest build.
Nothing in it depends on the site's design. It runs on the game version dispatch
from the `.github` repository, weekly as a sweep over every version on NuGet, and
by hand (`all=true` is the backfill).

The Render workflow ([render.yml](.github/workflows/render.yml)) is the half that
depends on the site's design. It downloads the archive a release names, generates
the landing page and site metadata from the archived `version.json` and
`api-delta-summary.json`, runs `docfx build`, and deploys. It never touches NuGet
or the packages. It runs on a push to `docs/` or `build/`, by hand, and is
dispatched by the Metadata workflow for the versions whose metadata changed. A
version is rebuilt only when its fingerprint on the host
(`meta=<pkgs> docs=<tree> build=<tree> docfx=<version>`, see
[fingerprint.sh](build/fingerprint.sh)) differs from the checkout, so a
template change re-renders every version while a run with nothing new skips them.

The scripts follow the same split: `generate-docfx-config.py plan` and
`apply-api-delta.py <docs>` produce the archive, `generate-docfx-config.py render`
and `apply-api-delta.py --fill-from` consume it.

Hosting and deployment are described in [deploy/README.md](deploy/README.md).
