using CommandLine;

namespace PackageDownloader.Options
{
    internal class DownloadOptions
    {
        [Option('t', "target", Required = true, HelpText = "Directory to extract into; packages land under <target>/game/<id>/<version>/.")]
        public string Target { get; set; } = default!;

        [Option('v', "version", Required = true, HelpText = "Game version as x.y.z. The highest package build for that version is taken.")]
        public string Version { get; set; } = default!;

        [Option('f', "feedUrl", Required = false, Default = "https://api.nuget.org/v3/index.json")]
        public string FeedUrl { get; set; } = default!;

        [Option('u', "feedUser", Required = false)]
        public string? FeedUser { get; set; }

        [Option('p', "feedPassword", Required = false)]
        public string? FeedPassword { get; set; }
    }
}
