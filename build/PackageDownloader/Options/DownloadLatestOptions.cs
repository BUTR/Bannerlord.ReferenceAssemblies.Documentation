using CommandLine;

namespace PackageDownloader.Options
{
    internal class DownloadLatestOptions
    {
        [Option('t', "target", Required = true)]
        public string Target { get; set; } = default!;

        [Option('s', "stableVersion", Required = true)]
        public string StableVersion { get; set; } = default!;

        [Option('b', "betaVersion", Required = false)]
        public string? BetaVersion { get; set; }

        [Option('f', "feedUrl", Required = false)]
        public string? FeedUrl { get; set; }

        [Option('u', "feedUser", Required = true)]
        public string FeedUser { get; set; } = default!;

        [Option('p', "feedPassword", Required = true)]
        public string FeedPassword { get; set; } = default!;

        [Option('n', "packageBaseName", Required = true)]
        public string PackageBaseName { get; set; } = default!;
    }
}