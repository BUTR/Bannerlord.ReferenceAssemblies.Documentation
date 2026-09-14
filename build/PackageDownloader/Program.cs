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
    /// </summary>
    public static class Program
    {
        private const string Prefix = "Bannerlord.ReferenceAssemblies";

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

            if (!TryParseGameVersion(o.Version, out var wanted))
            {
                Console.Error.WriteLine($"error: --version must be x.y.z, got '{o.Version}'");
                return 1;
            }

            var source = new PackageSource(o.FeedUrl, "Feed", true, false, false) { MaxHttpRequestsPerSource = 8 };
            if (!string.IsNullOrEmpty(o.FeedUser))
                source.Credentials = new PackageSourceCredential(o.FeedUrl, o.FeedUser, o.FeedPassword ?? "", true, string.Empty);
            var repository = new SourceRepository(source, Repository.Provider.GetCoreV3());

            using var cache = new SourceCacheContext();
            var byId = await repository.GetResourceAsync<FindPackageByIdResource>(CancellationToken.None);
            var download = await repository.GetResourceAsync<DownloadResource>(CancellationToken.None);
            var gameDir = Path.Combine(o.Target, "game");
            Directory.CreateDirectory(gameDir);

            var missing = new List<string>();
            foreach (var suffix in Packages)
            {
                var id = $"{Prefix}.{suffix}";
                var versions = await byId.GetAllVersionsAsync(id, cache, Logger, CancellationToken.None);
                // Package versions are game version + changeset (1.4.8.119303[-beta]); the highest
                // changeset for the requested x.y.z is the build the docs describe.
                var best = versions
                    .Where(v => v.Version.Major == wanted.Major && v.Version.Minor == wanted.Minor && v.Version.Build == wanted.Build)
                    .Max();
                if (best is null)
                {
                    Console.WriteLine($"{id}: no build for {o.Version}, skipping");
                    missing.Add(suffix);
                    continue;
                }

                Console.Write($"{id} {best}...");
                var identity = new PackageIdentity(id, best);
                using var result = await download.GetDownloadResourceResultAsync(identity, new PackageDownloadContext(cache), gameDir, Logger, CancellationToken.None);
                if (result.Status != DownloadResourceResultStatus.Available)
                {
                    Console.WriteLine($" failed ({result.Status})");
                    Console.Error.WriteLine($"error: could not download {identity}");
                    return 2;
                }
                Console.WriteLine(" done");
            }

            if (missing.Contains("Core"))
            {
                Console.Error.WriteLine($"error: {Prefix}.Core has no build for {o.Version}; nothing can be documented");
                return 2;
            }

            var surfaces = ApiSurface.HashAll(gameDir);
            var surfaceFile = Path.Combine(gameDir, ApiSurface.FileName);
            await File.WriteAllTextAsync(surfaceFile, JsonSerializer.Serialize(surfaces, new JsonSerializerOptions { WriteIndented = true }));
            Console.WriteLine($"{surfaces.Count} assemblies hashed into {surfaceFile}");
            return 0;
        }

        private static bool TryParseGameVersion(string text, out Version version)
        {
            version = default!;
            var parts = text.TrimStart('v').Split('.');
            if (parts.Length != 3 || !parts.All(p => int.TryParse(p, out _)))
                return false;
            version = new Version(int.Parse(parts[0]), int.Parse(parts[1]), int.Parse(parts[2]));
            return true;
        }
    }
}
