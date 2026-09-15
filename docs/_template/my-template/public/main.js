// Version picker, and the hook for the comparison page.
//
// The picker lists every published version, fetched at run time from the site
// root (see versions.js for why), and switches to the same page in another
// version. compare.js diffs two versions' API on compare.html.

import { currentVersion, isEarlyAccess, labelOf, loadManifest, pathWithinVersion, rootOf } from './versions.js'
import { installCompare } from './compare.js'

function go(version) {
  const root = rootOf(version)
  const target = root + pathWithinVersion()
  // The module set differs between versions, so the page being viewed may not
  // exist in the one selected. Land on that version's home page, not a 404.
  fetch(target, { method: 'HEAD' })
    .then(r => { location.href = r.ok ? target : root })
    .catch(() => { location.href = root })
}

function build(manifest) {
  const versions = [...(manifest.versions || [])]
  // A version can be deployed before the manifest lists it (a backfill job that
  // has not reached the manifest step yet). Without this the select would show
  // nothing at all for the page being read.
  const current = currentVersion()
  if (current && !versions.includes(current)) versions.unshift(current)
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

  const option = v => {
    const opt = document.createElement('option')
    opt.value = v
    opt.textContent = labelOf(v, manifest)
    return opt
  }

  // Release and early access are separate lines of the game with overlapping
  // numbers, so they get their own groups when both are present.
  const release = versions.filter(v => !isEarlyAccess(v))
  const early = versions.filter(isEarlyAccess)
  if (release.length && early.length) {
    for (const [name, list] of [['Release', release], ['Early access', early]]) {
      const group = document.createElement('optgroup')
      group.label = name
      for (const v of list) group.appendChild(option(v))
      select.appendChild(group)
    }
  } else {
    for (const v of versions) select.appendChild(option(v))
  }
  select.value = current || manifest.latest || manifest.stable || versions[0]

  select.addEventListener('change', () => go(select.value))
  wrap.appendChild(select)
  return wrap
}

function install() {
  const navbar = document.getElementById('navbar')
  if (!navbar || document.getElementById('version-select')) return

  // A missing manifest, a single version, or a failed fetch leaves the navbar as
  // it was. The picker is an aid; it should never break the page.
  loadManifest()
    .then(manifest => {
      if (!manifest) return
      const picker = build(manifest)
      if (picker) navbar.insertBefore(picker, navbar.firstChild)
    })
    .catch(() => {})
}

function start() {
  install()
  installCompare().catch(() => {})
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
      document.addEventListener('DOMContentLoaded', start, { once: true })
    } else {
      start()
    }
  }
}
