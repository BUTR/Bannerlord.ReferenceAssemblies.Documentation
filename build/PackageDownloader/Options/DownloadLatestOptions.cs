using CommandLine;

namespace PackageDownloader.Options
{
    internal class DownloadLatestOptions
    {
        [Option('t', "target", Required = true)]
        public string Target { get; set; } = default!;

        [Option('v', "version", Required = true)]
        public string Version { get; set; } = default!;

        [Option('f', "feedUrl", Required = false)]
        public string? FeedUrl { get; set; }

        [Option('u', "feedUser", Required = false)]
        public string? FeedUser { get; set; } = default!;

        [Option('p', "feedPassword", Required = false)]
        public string? FeedPassword { get; set; } = default!;
    }
}