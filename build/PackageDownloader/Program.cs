using CommandLine;

using NuGet.Common;
using NuGet.Configuration;
using NuGet.Packaging.Core;
using NuGet.Protocol;
using NuGet.Protocol.Core.Types;

using PackageDownloader.Options;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace PackageDownloader
{
    /// <summary>
    /// Downloads the reference assembly packages for one game version and writes game/api-surface.json.
    ///
    /// The package list is fixed rather than discovered through NuGet search: search is relevance
    /// ranked, capped per page and lags the flat container, none of which a build should depend on.
    /// A package that has no build for the requested version is reported and skipped; the module set
    /// differs between game versions, so that is normal. Core is the exception: without it there is
    /// nothing to document, so its absence is an error.
    ///
    /// The version follows the reference assemblies' own convention: "1.5.2" is the release build and
    /// "e1.5.2" the early access build of the same number, which lives in the *.EarlyAccess packages.
    ///
    /// Resolution and download are separate so that the metadata workflow can ask "which builds would
    /// this version document?" without pulling a gigabyte of packages. --resolve-only prints the
    /// resolved map (lower-case package id -> normalized package version) as JSON and stops; a real
    /// download writes the same map to game/packages.json. Both hash to the same value, which is what
    /// the workflow records as the pkgs fingerprint of a version's metadata.
    /// </summary>
    public static class Program
    {
        private const string Prefix = "Bannerlord.ReferenceAssemblies";

        public const string PackagesFile = "packages.json";

        // Keep in step with PRIMARY and DERIVED in build/generate-docfx-config.py.
        private static readonly string[] Packages =
        {
            "Core",
            "Native",
            "SandBox",
            "StoryMode",
            "Multiplayer",
            "CustomBattle",
            "BirthAndDeath",
            "NavalDLC",
            "FastMode",
            "DedicatedCustomServerHelper",
            "Server.Core",
            "ModdingKit.Core",
        };

        private static readonly ILogger Logger = NullLogger.Instance;

        public static async Task<int> Main(string[] args)
        {
            var parsed = Parser.Default.ParseArguments<DownloadOptions>(args);
            if (parsed is not Parsed<DownloadOptions> { Value: var o })
                return 1; // CommandLineParser already printed the usage text

            if (!TryParseGameVersion(o.Version, out var wanted, out var earlyAccess))
            {
                Console.Error.WriteLine($"error: --version must be x.y.z or ex.y.z, got '{o.Version}'");
                return 1;
            }
            var packageSuffix = earlyAccess ? ".EarlyAccess" : "";
            if (!o.ResolveOnly && string.IsNullOrEmpty(o.Target))
            {
                Console.Error.WriteLine("error: --target is required unless --resolve-only is given");
                return 1;
            }
            // Progress goes to stderr in resolve mode so that stdout is the JSON map and nothing else.
            var log = o.ResolveOnly ? Console.Error : Console.Out;

            var source = new PackageSource(o.FeedUrl, "Feed", true, false, false) { MaxHttpRequestsPerSource = 8 };
            if (!string.IsNullOrEmpty(o.FeedUser))
                source.Credentials = new PackageSourceCredential(o.FeedUrl, o.FeedUser, o.FeedPassword ?? "", true, string.Empty);
            var repository = new SourceRepository(source, Repository.Provider.GetCoreV3());

            using var cache = new SourceCacheContext();
            var byId = await repository.GetResourceAsync<FindPackageByIdResource>(CancellationToken.None);

            var resolved = new List<PackageIdentity>();
            var missing = new List<string>();
            foreach (var suffix in Packages)
            {
                var id = $"{Prefix}.{suffix}{packageSuffix}";
                var versions = await byId.GetAllVersionsAsync(id, cache, Logger, CancellationToken.None);
                // Package versions are game version + changeset (1.4.8.119303[-beta]); the highest
                // changeset for the requested x.y.z is the build the docs describe.
                var best = versions
                    .Where(v => v.Version.Major == wanted.Major && v.Version.Minor == wanted.Minor && v.Version.Build == wanted.Build)
                    .Max();
                if (best is null)
                {
                    log.WriteLine($"{id}: no build for {o.Version}, skipping");
                    missing.Add(suffix);
                    continue;
                }
                resolved.Add(new PackageIdentity(id, best));
            }

            if (missing.Contains("Core"))
            {
                Console.Error.WriteLine($"error: {Prefix}.Core{packageSuffix} has no build for {o.Version}; nothing can be documented");
                return 2;
            }

            // Sorted by id so the serialized form, and therefore its hash, does not depend on the
            // order of the Packages array.
            var map = resolved
                .OrderBy(p => p.Id.ToLowerInvariant(), StringComparer.Ordinal)
                .ToDictionary(p => p.Id.ToLowerInvariant(), p => p.Version.ToNormalizedString());
            var mapJson = JsonSerializer.Serialize(map, new JsonSerializerOptions { WriteIndented = true });

            if (o.ResolveOnly)
            {
                Console.WriteLine(mapJson);
                return 0;
            }

            var download = await repository.GetResourceAsync<DownloadResource>(CancellationToken.None);
            var gameDir = Path.Combine(o.Target!, "game");
            Directory.CreateDirectory(gameDir);

            foreach (var identity in resolved)
            {
                Console.Write($"{identity.Id} {identity.Version}...");
                using var result = await download.GetDownloadResourceResultAsync(identity, new PackageDownloadContext(cache), gameDir, Logger, CancellationToken.None);
                if (result.Status != DownloadResourceResultStatus.Available)
                {
                    Console.WriteLine($" failed ({result.Status})");
                    Console.Error.WriteLine($"error: could not download {identity}");
                    return 2;
                }
                Console.WriteLine(" done");
            }

            var packagesFile = Path.Combine(gameDir, PackagesFile);
            await File.WriteAllTextAsync(packagesFile, mapJson + "\n");
            Console.WriteLine($"{map.Count} package builds recorded in {packagesFile}");

            var surfaces = ApiSurface.HashAll(gameDir);
            var surfaceFile = Path.Combine(gameDir, ApiSurface.FileName);
            await File.WriteAllTextAsync(surfaceFile, JsonSerializer.Serialize(surfaces, new JsonSerializerOptions { WriteIndented = true }));
            Console.WriteLine($"{surfaces.Count} assemblies hashed into {surfaceFile}");
            return 0;
        }

        private static bool TryParseGameVersion(string text, out Version version, out bool earlyAccess)
        {
            version = default!;
            earlyAccess = text.StartsWith('e');
            var parts = (earlyAccess ? text[1..] : text.TrimStart('v')).Split('.');
            if (parts.Length != 3 || !parts.All(p => int.TryParse(p, out _)))
                return false;
            version = new Version(int.Parse(parts[0]), int.Parse(parts[1]), int.Parse(parts[2]));
            return true;
        }
    }
}
