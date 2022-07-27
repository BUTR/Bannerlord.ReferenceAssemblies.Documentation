using CommandLine;

using MoreLinq.Extensions;

using NuGet.Common;
using NuGet.Configuration;
using NuGet.Packaging.Core;
using NuGet.Protocol.Core.Types;

using PackageDownloader.Extensions;
using PackageDownloader.Options;

using System;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

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
                var rxPackageName = new Regex($"{o.PackageBaseName}*", RegexOptions.Compiled);
                var packageSource = new PackageSource(o.FeedUrl, "Feed1", true, false, false)
                {
                    Credentials = new PackageSourceCredential(o.FeedUrl, o.FeedUser ?? "", o.FeedPassword ?? "", true, "basic"),
                    ProtocolVersion = 3,
                    MaxHttpRequestsPerSource = 8
                };
                var sourceRepository = new SourceRepository(packageSource, Repository.Provider.GetCoreV3());

                var sourceCacheContext = new SourceCacheContext();
                var downloadContext = new PackageDownloadContext(sourceCacheContext);
                var packageLister = sourceRepository.GetResource<PackageSearchResource>();
                var finderPackageByIdResource = sourceRepository.GetResource<FindPackageByIdResource>();
                var metadataResource = sourceRepository.GetResource<PackageMetadataResource>();
                var downloadResource = sourceRepository.GetResource<DownloadResource>();

                Console.Write("Checking Feed...");
                var versions = await packageLister.SearchAsync("", new SearchFilter(false) { SupportedFrameworks = new[] { "net472", "netstandard2.0" } }, 0, 100, _logger, _ct)
                    .AsAsyncEnumerable()
                    .Where(p => rxPackageName.IsMatch(p.Identity.Id))
                    .SelectAwait(async package =>
                    {
                        var metadatas = await finderPackageByIdResource
                            .GetAllVersionsAsync(package.Identity.Id, sourceCacheContext, _logger, _ct)
                            .AsAsyncEnumerable()
                            .Select(v => metadataResource.GetMetadataAsync(new PackageIdentity(package.Identity.Id, v), sourceCacheContext, _logger, _ct))
                            .SelectMany(x => x.ToAsyncEnumerable())
                            .ToListAsync();

                        return (PackageId: package.Identity.Id, PackageMetadatas: metadatas);
                    })
                    .ToListAsync();
                Console.WriteLine("Done!");


                if (!string.IsNullOrEmpty(o.StableVersion))
                {
                    Console.WriteLine("Downloading Stable");

                    var stableDict = versions
                        .Select(t => (PackageId: t.PackageId, PackageMetadata: t.PackageMetadatas
                            .Where(x => x.Identity.Version.OriginalVersion.StartsWith(o.StableVersion))
                            .MaxBy(x => x.Identity.Version).FirstOrDefault()))
                        .ToDictionary(x => x.PackageId, x => x.PackageMetadata);

                    foreach (var (packageId, packageMetadata) in stableDict)
                    {
                        if (packageMetadata is null)
                        {
                            Console.WriteLine($"Couldn't find metadata for {packageId}! Skipping.");
                            continue;
                        }
                        
                        Console.Write($"Downloading {packageId} {packageMetadata.Identity.Version}...");
                        downloadResource.GetDownloadResourceResultAsync(packageMetadata.Identity, downloadContext, Path.Combine(o.Target, "Stable"), _logger, _ct).GetAwaiter().GetResult();
                        Console.WriteLine("Done!");
                    }
                }

                if (!string.IsNullOrEmpty(o.BetaVersion))
                {
                    Console.WriteLine("Downloading Beta");

                    var betaDict = versions
                        .Select(t => (PackageId: t.PackageId, PackageMetadata: t.PackageMetadatas
                            .Where(x => x.Identity.Version.OriginalVersion.StartsWith(o.BetaVersion))
                            .MaxBy(x => x.Identity.Version).FirstOrDefault()))
                        .ToDictionary(x => x.PackageId, x => x.PackageMetadata);

                    foreach (var (packageId, packageMetadata) in betaDict)
                    {
                        if (packageMetadata is null)
                        {
                            Console.WriteLine($"Couldn't find metadata for {packageId}! Skipping.");
                            continue;
                        }
                        
                        Console.Write($"Downloading {packageId} {packageMetadata.Identity.Version}...");
                        downloadResource.GetDownloadResourceResultAsync(packageMetadata.Identity, downloadContext, Path.Combine(o.Target, "Beta"), _logger, _ct).GetAwaiter().GetResult();
                        Console.WriteLine("Done!");
                    }
                }
            });
    }
}
