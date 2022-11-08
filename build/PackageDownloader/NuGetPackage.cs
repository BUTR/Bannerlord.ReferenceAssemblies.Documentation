using NuGet.Packaging.Core;
using NuGet.Versioning;

namespace Bannerlord.ReferenceAssemblies
{
    internal readonly partial struct NuGetPackage
    {
        public static NuGetPackage? Get(PackageIdentity identity, string tags)
        {
            var appId = ParseAppIdEmbedding(tags);
            var buildId = ParseBuildIdEmbedding(tags);

            if (appId == null || buildId == null)
                return null;

            return new NuGetPackage(identity, appId.Value, buildId.Value);
        }

        public readonly PackageIdentity PkgIdentity;
        public readonly string Name => PkgIdentity.Id;
        public readonly NuGetVersion PkgVersion  => PkgIdentity.Version;

        public readonly uint AppId;
        public readonly uint BuildId;

        private NuGetPackage(PackageIdentity pkgIdentity, uint appId, uint buildId)
        {
            PkgIdentity = pkgIdentity;
            AppId = appId;
            BuildId = buildId;
        }

        public override string ToString() => $"{Name} {PkgVersion} ({AppId}, {BuildId})";
    }
}