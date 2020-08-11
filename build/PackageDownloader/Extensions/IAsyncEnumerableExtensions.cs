using System.Collections.Generic;
using System.Threading.Tasks;

namespace PackageDownloader.Extensions
{
    internal static class IAsyncEnumerableExtensions
    {
        public static async IAsyncEnumerable<TResult> AsAsyncEnumerable<TResult>(this Task<IEnumerable<TResult>> @this)
        {
            foreach (var iteration in await @this)
                yield return iteration;
        }
    }
}