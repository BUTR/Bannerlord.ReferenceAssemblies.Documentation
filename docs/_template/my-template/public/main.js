// Version picker.
//
// Every game version is built once and never rebuilt, so a list baked into the
// HTML would only know about versions that existed on its build day. The list is
// therefore fetched at run time from /versions.json, which lives at the real site
// root rather than inside any one version. That file is rewritten on every
// deploy, so an old version's picker still offers the newest ones.

const MANIFEST = '/versions.json'

// Which version is being viewed. null means the page came from the site root,
// which serves whatever /latest points at.
function currentVersion() {
  const m = location.pathname.match(/^\/v\/([^/]+)\//)
  return m ? m[1] : null
}

// The path below the version prefix, e.g. "api/core/TaleWorlds.Core.html".
function pathWithinVersion() {
  const m = location.pathname.match(/^\/v\/[^/]+\/(.*)$/)
  return m ? m[1] : location.pathname.replace(/^\//, '')
}

function go(version) {
  const target = `/v/${version}/${pathWithinVersion()}`
  const root = `/v/${version}/`
  // The module set differs between versions, so the page being viewed may not
  // exist in the one selected. Land on that version's home page, not a 404.
  fetch(target, { method: 'HEAD' })
    .then(r => { location.href = r.ok ? target : root })
    .catch(() => { location.href = root })
}

function build(manifest) {
  const versions = manifest.versions || []
  // One entry is still worth rendering: it names the version being read.
  if (versions.length < 1) return null

  const wrap = document.createElement('div')
  wrap.className = 'version-picker'

  const label = document.createElement('label')
  label.className = 'visually-hidden'
  label.setAttribute('for', 'version-select')
  label.textContent = 'Game version'
  wrap.appendChild(label)

  const select = document.createElement('select')
  select.id = 'version-select'
  select.className = 'form-select form-select-sm'
  select.title = 'Game version'

  for (const v of versions) {
    const opt = document.createElement('option')
    opt.value = v
    opt.textContent = v === manifest.latest ? `v${v} (latest)` : `v${v}`
    select.appendChild(opt)
  }
  select.value = currentVersion() || manifest.latest || versions[0]

  select.addEventListener('change', () => go(select.value))
  wrap.appendChild(select)
  return wrap
}

function install() {
  const navbar = document.getElementById('navbar')
  if (!navbar || document.getElementById('version-select')) return

  // A missing manifest, a single version, or a failed fetch leaves the navbar as
  // it was. The picker is an aid; it should never break the page.
  fetch(MANIFEST, { cache: 'no-cache' })
    .then(r => (r.ok ? r.json() : null))
    .then(manifest => {
      if (!manifest) return
      const picker = build(manifest)
      if (picker) navbar.insertBefore(picker, navbar.firstChild)
    })
    .catch(() => {})
}

export default {
  defaultTheme: 'dark',
  iconLinks: [
    {
      icon: 'github',
      href: 'https://github.com/BUTR/Bannerlord.ReferenceAssemblies.Documentation',
      title: 'GitHub'
    },
    {
      icon: 'discord',
      href: 'https://discord.gg/unBY2twS3V',
      title: 'Discord'
    }
  ],
  start: () => {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', install, { once: true })
    } else {
      install()
    }
  }
}
