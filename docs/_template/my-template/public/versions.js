// What the site knows about versions, shared by the picker (main.js) and the
// comparison page (compare.js).
//
// Every game version is built once and never rebuilt, so a list baked into the
// HTML would only know about versions that existed on its build day. The list is
// therefore fetched at run time from /versions.json, which lives at the real site
// root rather than inside any one version. That file is rewritten on every
// deploy, so an old version's picker still offers the newest ones.
//
// Version ids follow the game's own naming: "1.5.2" is a release build and is
// served from /v/1.5.2/, "e1.5.2" is the early access build of the same number
// and is served from /e/1.5.2/.

export const MANIFEST = '/versions.json'
const VERSION_PATH = /^\/(v|e)\/([^/]+)\//

export function isEarlyAccess(id) {
  return id.startsWith('e')
}

// The site path a version id is served from, with a trailing slash.
export function rootOf(id) {
  return isEarlyAccess(id) ? `/e/${id.slice(1)}/` : `/v/${id}/`
}

// Which version is being viewed. null means the page came from the site root,
// which serves whatever /latest points at.
export function currentVersion() {
  const m = location.pathname.match(VERSION_PATH)
  if (!m) return null
  return m[1] === 'e' ? 'e' + m[2] : m[2]
}

// The path below the version prefix, e.g. "api/core/TaleWorlds.Core.html".
export function pathWithinVersion() {
  const m = location.pathname.match(/^\/(?:v|e)\/[^/]+\/(.*)$/)
  return m ? m[1] : location.pathname.replace(/^\//, '')
}

// How a version id is shown: release builds get the game's "v" prefix and the
// channel label, early access ids are already distinctive.
export function labelOf(id, manifest) {
  if (isEarlyAccess(id)) return id
  const channel =
    id === manifest.stable ? ' (Stable)' : id === manifest.beta ? ' (Beta)' : ''
  return `v${id}${channel}`
}

// Fetch the manifest; null when it is missing or unreadable. Callers treat that
// as "no version information", never as an error the reader has to see.
export function loadManifest() {
  return fetch(MANIFEST, { cache: 'no-cache' })
    .then(r => (r.ok ? r.json() : null))
    .catch(() => null)
}
