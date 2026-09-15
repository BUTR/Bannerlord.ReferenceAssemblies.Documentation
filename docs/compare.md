---
title: Compare versions
---

# Compare two game versions

Pick the game version your mod was built against and the one you are moving to.
The page lists what breaks binary compatibility between them first: types moved
to another namespace or assembly, types and members removed, and members whose
signature changed. A compiled mod references a type by its namespace and
assembly and a member by its exact signature, so each of those fails at load
time or at the call even where the source would still compile. Below that comes
the full list of changes, additions included. Every entry links to the page
that documents it, in the version where it exists.

The comparison runs in your browser from an index each version publishes with
its pages, so any two published versions can be compared, release or early
access. A version built before that index existed cannot be compared until it
is rebuilt; the page says so when that happens.

<div id="api-compare"></div>
