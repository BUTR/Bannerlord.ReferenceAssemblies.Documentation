using CommandLine;

using NuGet.Common;
using NuGet.Configuration;
using NuGet.Packaging.Core;
using NuGet.Protocol.Core.Types;

using PackageDownloader.Options;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Bannerlord.ReferenceAssemblies;
using NuGet.Versioning;

namespace PackageDownloader
{
    public static class Program
    {
        private static readonly ILogger _logger = NullLogger.Instance;
        private static readonly CancellationToken _ct = CancellationToken.None;

        public static Task Main(string[] args) => Parser
            .Default
            .ParseArguments<DownloadLatestOptions>(args)
            .WithNotParsed(e =>
            {
                Console.WriteLine("ERROR");
            })
            .WithParsedAsync<DownloadLatestOptions>(async o =>
            {
                var packageSource = new PackageSource(o.FeedUrl, "Feed1", true, false, false)
                {
                    Credentials = new PackageSourceCredential(o.FeedUrl, o.FeedUser ?? "", o.FeedPassword ?? "", true, string.Empty),
                    MaxHttpRequestsPerSource = 8,
                };
                var sourceRepository = new SourceRepository(packageSource, Repository.Provider.GetCoreV3());

                var sourceCacheContext = new SourceCacheContext();
                var downloadContext = new PackageDownloadContext(sourceCacheContext);
                var packageLister = sourceRepository.GetResource<PackageSearchResource>();
                var finderPackageByIdResource = sourceRepository.GetResource<FindPackageByIdResource>();
                var metadataResource = sourceRepository.GetResource<PackageMetadataResource>();
                var downloadResource = sourceRepository.GetResource<DownloadResource>();

                Console.Write("Checking Feed...");
                var foundPackages = await packageLister.SearchAsync("Bannerlord.ReferenceAssemblies", new SearchFilter(true), 0, 50, _logger, _ct);
                var packages = await foundPackages
                    .ToAsyncEnumerable()
                    .SelectAwait(async package =>
                    {
                        var versions = MaxVersions(finderPackageByIdResource.GetAllVersionsAsync(package.Identity.Id, sourceCacheContext, _logger, _ct));
                        var metadatas = GetMetadataAsync(versions, version => metadataResource.GetMetadataAsync(new PackageIdentity(package.Identity.Id, version), sourceCacheContext, _logger, _ct), _ct);
                        return (PackageId: package.Identity.Id, PackageMetadatas: (IReadOnlyList<NuGetPackage>) await GetPackageVersionsAsync(metadatas, _ct).ToListAsync(_ct));
                    })
                    .ToListAsync();
                Console.WriteLine("Done!");

                Console.WriteLine("Downloading Version");

                var versionDict = packages.Where(x => StripEnding(x.PackageId) == x.PackageId)
                    .Select(t => (PackageId: t.PackageId, PackageMetadata: t.PackageMetadatas
                        .Where(x => x.PkgVersion.Version.ToString().StartsWith(o.Version))
                        .MaxBy(x => x.PkgVersion.Version)))
                    .ToDictionary(x => x.PackageId, x => x.PackageMetadata);

                foreach (var (packageId, packageMetadata) in versionDict)
                {
                    if (packageMetadata.PkgIdentity == null || packageMetadata.PkgVersion is null)
                    {
                        Console.WriteLine($"Couldn't find metadata for {packageId}! Skipping.");
                        continue;
                    }

                    Console.Write($"Downloading {packageId} {packageMetadata.PkgVersion.Version}...");
                    await downloadResource.GetDownloadResourceResultAsync(packageMetadata.PkgIdentity, downloadContext, Path.Combine(o.Target, "game"), _logger, _ct);
                    Console.WriteLine("Done!");
                }
            });

        private static readonly IReadOnlyList<string?> Prefixes = new List<string?>
        {
            "Alpha",
            "Beta",
            "EarlyAccess",
            "Development",
            "Invalid",
        };

        private static string StripEnding(string packageId) => Prefixes.Aggregate(packageId, (current, value) => current.Replace($".{value}", string.Empty));

        private static async IAsyncEnumerable<NuGetVersion> MaxVersions(Task<IEnumerable<NuGetVersion>> source)
        {
            var dict = new Dictionary<string, NuGetVersion>();
            foreach (var version in await source)
            {
                var v = version.Version.ToString(3);
                var currentMax = dict.TryGetValue(v, out var c) ? c : null;
                if (currentMax is null) dict[v] = version;
                // Release reset their build index. For now everything that is higher than 200000 is considered EA
                // TODO: better fix?
                else if (version.Version.Build < 100000 && currentMax.Version < version.Version) dict[v] = version;
                else if (currentMax.Version < version.Version) dict[v] = version;
            }
            foreach (var value in dict.Values)
                yield return value;
        }

        private static async IAsyncEnumerable<IPackageSearchMetadata> GetMetadataAsync(IAsyncEnumerable<NuGetVersion> versions, Func<NuGetVersion, Task<IPackageSearchMetadata>> getMeta, CancellationToken cancellationToken = default)
        {
            await foreach (var version in versions.WithCancellation(cancellationToken))
            {
                yield return await getMeta(version);
            }
        }

        private static async IAsyncEnumerable<NuGetPackage> GetPackageVersionsAsync(IAsyncEnumerable<IPackageSearchMetadata> metadatas, [EnumeratorCancellation] CancellationToken cancellation = default)
        {
            await foreach (var metadata in metadatas.WithCancellation(cancellation))
            {
                var package = NuGetPackage.Get(metadata.Identity, metadata.Tags);
                if (package != null)
                    yield return package.Value;
            }
        }
    }
}