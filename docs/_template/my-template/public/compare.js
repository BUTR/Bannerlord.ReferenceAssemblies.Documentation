// Compare the public API of two game versions, on compare.html.
//
// Each version publishes api-index.json next to its pages (written by
// build/write-api-index.py): every documented type with its members and a hash
// of each declaration. This page fetches the index of two versions and diffs
// them here in the browser, so no server-side work and no rebuild is needed
// when a new version ships. Every entry links to the page that documents it,
// in the version where it exists.
//
// The comparison sees what the pages see: added and removed types, added and
// removed members, and members whose declaration (modifiers, return type,
// parameters, base type) changed. Bodies never change a hash; only the
// reference assemblies' public surface does.
//
// The page exists so mod authors can see whether anything their mod binds to
// breaks between two versions, so that answer comes first, as a list of
// binary-breaking changes: types moved to another namespace or
// assembly, types and members removed, signatures and declarations changed. A
// compiled mod references a type by namespace and assembly and a member by its
// exact signature, so every one of those fails at load time or at the call,
// even where the source would still compile after a rebuild. Additions never
// break anything and are only in the full listing.
//
// Two kinds of churn are folded rather than shown twice. A type that moved to
// another namespace is reported once, as moved, when its name and kind are
// unique on both sides. A member whose uid changed only because a parameter
// type moved (or was renamed the same way) is reported as changed, not as a
// removal plus an addition with the same visible signature.

import { currentVersion, isEarlyAccess, labelOf, loadManifest, rootOf } from './versions.js'

const INDEX = 'api-index.json'

// A version built before the index existed has no api-index.json until it is
// rebuilt. Say so instead of failing silently.
async function loadIndex(version) {
  const r = await fetch(rootOf(version) + INDEX)
  if (r.status === 404) {
    throw new Error(`${labelOf(version, {})} has no comparison index. It was built before this page existed and gets one when it is next rebuilt.`)
  }
  if (!r.ok) throw new Error(`Could not load the index of ${version} (HTTP ${r.status}).`)
  return r.json()
}

// The member anchor the modern template generates: the full uid with every
// non-word character turned into an underscore.
function anchor(uid) {
  return uid.replace(/\W/g, '_')
}

const QUALIFIERS = /(?:[A-Za-z_]\w*\.)+(?=[A-Za-z_])/g

function shortType(uid) {
  return uid.split(':').pop().split('.').pop()
}

// "Start(System.Boolean,System.Collections.Generic.List{System.String})" reads as
// "Start(Boolean, List<String>)" once the namespaces are dropped.
function prettyMember(id, typeUid) {
  const paren = id.indexOf('(')
  let name = paren < 0 ? id : id.slice(0, paren)
  // Constructors are "#ctor" / "#ctor(params)" in a uid; show the type's name.
  if (name === '#ctor' || name === '#cctor') {
    name = (name === '#cctor' ? 'static ' : '') + shortType(typeUid).replace(/`\d+$/, '')
    if (paren < 0) return `${name}()`
  }
  if (paren < 0) return name
  const params = id.slice(paren + 1, -1)
    .replace(QUALIFIERS, '')
    .replace(/[{]/g, '<').replace(/[}]/g, '>')
    .replace(/@/g, '&')
    .replace(/,/g, ', ')
  return `${name}(${params})`
}

// The member id with namespace qualifiers removed: what a reader sees, and the
// key used to pair a removal with an addition that is the same member.
function unqualified(id) {
  return id.replace(QUALIFIERS, '')
}

// Pair the entries of two lists whose key is unique on both sides.
function pairUnique(left, right, key) {
  const count = (list) => {
    const m = new Map()
    for (const x of list) { const k = key(x); m.set(k, (m.get(k) || 0) + 1) }
    return m
  }
  const lc = count(left), rc = count(right)
  const byKey = new Map(right.map(x => [key(x), x]))
  const pairs = [], leftRest = [], rightMatched = new Set()
  for (const l of left) {
    const k = key(l)
    if (lc.get(k) === 1 && rc.get(k) === 1) {
      pairs.push([l, byKey.get(k)]); rightMatched.add(k)
    } else leftRest.push(l)
  }
  return { pairs, leftRest, rightRest: right.filter(x => !rightMatched.has(key(x))) }
}

// Member-level comparison of one type present (under any uid) on both sides.
function compareMembers(old, t) {
  let added = [], removed = []
  const changed = []
  for (const [id, h] of Object.entries(t.m)) {
    if (!(id in old.m)) added.push(id)
    else if (old.m[id] !== h) changed.push({ id, oldId: id, why: 'declaration changed' })
  }
  for (const id of Object.keys(old.m)) if (!(id in t.m)) removed.push(id)
  const paired = pairUnique(removed, added, unqualified)
  for (const [oldId, id] of paired.pairs) changed.push({ id, oldId, why: 'parameter types changed' })
  removed = paired.leftRest
  added = paired.rightRest
  return { added, removed, changed }
}

// Diff two indexes into per-namespace buckets.
function diff(from, to) {
  const spaces = new Map()
  const bucket = ns => {
    if (!spaces.has(ns)) spaces.set(ns, { added: [], removed: [], changed: [] })
    return spaces.get(ns)
  }
  const totals = { typesAdded: 0, typesRemoved: 0, typesMoved: 0, membersAdded: 0, membersRemoved: 0, membersChanged: 0 }
  const both = [], onlyTo = [], onlyFrom = []

  for (const [uid, t] of Object.entries(to.types)) {
    const old = from.types[uid]
    if (old) both.push({ uid, t, old })
    else onlyTo.push({ uid, t })
  }
  for (const [uid, t] of Object.entries(from.types)) {
    if (!(uid in to.types)) onlyFrom.push({ uid, t })
  }

  // A type that only changed namespace: same kind and name, unique on both sides.
  const key = e => `${e.t.k} ${shortType(e.uid)}`
  const moved = pairUnique(onlyFrom, onlyTo, key)
  for (const [o, n] of moved.pairs) both.push({ uid: n.uid, t: n.t, old: o.t, movedFrom: o.uid })

  for (const e of both) {
    const m = compareMembers(e.old, e.t)
    const declaration = e.old.d !== e.t.d
    // Same uid, different assembly: the type moved between dlls, which breaks a
    // compiled reference just as a namespace move does.
    const movedAssembly = e.old.a && e.t.a && e.old.a !== e.t.a ? e.old.a : null
    if (e.movedFrom || movedAssembly || declaration || m.added.length || m.removed.length || m.changed.length) {
      bucket(e.t.n).changed.push({ ...e, ...m, declaration, movedAssembly })
      totals.membersAdded += m.added.length
      totals.membersRemoved += m.removed.length
      totals.membersChanged += m.changed.length
      if (e.movedFrom || movedAssembly) totals.typesMoved++
    }
  }
  for (const e of moved.rightRest) {
    bucket(e.t.n).added.push(e)
    totals.typesAdded++
    totals.membersAdded += Object.keys(e.t.m).length
  }
  for (const e of moved.leftRest) {
    bucket(e.t.n).removed.push(e)
    totals.typesRemoved++
    totals.membersRemoved += Object.keys(e.t.m).length
  }
  return { spaces, totals }
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v
    else if (k === 'text') node.textContent = v
    else if (v != null && v !== '') node.setAttribute(k, v)
  }
  for (const c of children) if (c != null) node.append(c)
  return node
}

const MARK = { added: '+', removed: '−', changed: '~' }
const badge = (kind, text) => el('span', { class: `badge cmp-${kind}`, text: text || MARK[kind] })
const note = text => el('span', { class: 'cmp-count text-body-secondary', text: ' ' + text })

function link(version, path, text, title) {
  return el('a', { href: rootOf(version) + path, text, title })
}

function memberUid(typeUid, id) {
  return typeUid.replace(/^[a-z]+:/, '') + '.' + id
}

function memberLine(kind, version, typeUid, page, id, extra) {
  const uid = memberUid(typeUid, id)
  const li = el('li', { class: `cmp-line cmp-${kind}` },
    badge(kind), ' ', link(version, `${page}#${anchor(uid)}`, prettyMember(id, typeUid), uid))
  if (extra) li.append(note(extra))
  return li
}

function typeLine(kind, version, entry) {
  return el('li', { class: `cmp-line cmp-${kind}` },
    badge(kind), ' ',
    link(version, entry.t.h, `${entry.t.k} ${shortType(entry.uid)}`, entry.uid),
    note(`${Object.keys(entry.t.m).length} members`))
}

function changedType(fromV, toV, entry) {
  const li = el('li', { class: 'cmp-line cmp-changed' },
    badge('changed'), ' ',
    link(toV, entry.t.h, `${entry.t.k} ${shortType(entry.uid)}`, entry.uid))
  if (entry.movedFrom) {
    li.append(note('moved from '), link(fromV, entry.old.h, entry.old.n, entry.movedFrom))
  }
  if (entry.movedAssembly) li.append(note(`moved from ${entry.movedAssembly}.dll to ${entry.t.a}.dll`))
  if (entry.declaration) li.append(note('declaration changed'))
  const ul = el('ul', { class: 'cmp-members' })
  for (const id of entry.added) ul.append(memberLine('added', toV, entry.uid, entry.t.h, id))
  for (const id of entry.removed) {
    ul.append(memberLine('removed', fromV, entry.movedFrom || entry.uid, entry.old.h, id))
  }
  for (const c of entry.changed) {
    const line = memberLine('changed', toV, entry.uid, entry.t.h, c.id, c.why)
    if (c.oldId !== c.id) line.querySelector('a').title += `\nwas: ${memberUid(entry.movedFrom || entry.uid, c.oldId)}`
    ul.append(line)
  }
  if (ul.childElementCount) li.append(ul)
  return li
}

// Everything a compiled mod can be bound to that no longer resolves the same
// way. Additions are left out on purpose: nothing that exists in the old
// version stops working because something new appeared.
function breakingChanges(spaces) {
  const b = { movedTypes: [], removedTypes: [], removedMembers: [], changedMembers: [], changedTypes: [] }
  for (const bucket of spaces.values()) {
    for (const e of bucket.removed) b.removedTypes.push(e)
    for (const e of bucket.changed) {
      if (e.movedFrom || e.movedAssembly) b.movedTypes.push(e)
      if (e.declaration) b.changedTypes.push(e)
      for (const id of e.removed) b.removedMembers.push({ e, id })
      for (const c of e.changed) b.changedMembers.push({ e, c })
    }
  }
  return b
}

function renderBreaking(b, fromV, toV, fromLabel, toLabel) {
  const total = b.movedTypes.length + b.removedTypes.length + b.removedMembers.length +
    b.changedMembers.length + b.changedTypes.length
  const wrap = el('section', { class: 'cmp-breaking' })
  if (!total) {
    wrap.append(el('div', { class: 'alert alert-success' },
      el('strong', { text: 'No binary-breaking changes. ' }),
      `Everything a mod compiled against ${fromLabel} can bind to still resolves the same way on ${toLabel}. Only additions were made.`))
    return wrap
  }
  const alert = el('div', { class: 'alert alert-warning' })
  alert.append(el('strong', { text: `${total} ${total === 1 ? 'change breaks' : 'changes break'} binary compatibility. ` }),
    `A mod compiled against ${fromLabel} that uses any type or member listed here fails to load, or crashes at the call, on ${toLabel}. ` +
    'Moved types and moved parameter types are fixed by rebuilding the mod against the new version, after updating the using directive or reference. ' +
    'Removed types and members and changed signatures need the code changed as well.')
  wrap.append(alert)

  const byType = (x, y) => shortType(x.uid).localeCompare(shortType(y.uid))
  const category = (title, items, explain, line) => {
    if (!items.length) return
    const d = el('details', { class: 'cmp-category' })
    d.open = items.length <= 200
    d.append(el('summary', {}, el('span', { class: 'cmp-ns', text: `${title} ` }), badge('removed', String(items.length))))
    d.append(el('p', { class: 'text-body-secondary small cmp-explain', text: explain }))
    const ul = el('ul', { class: 'cmp-types' })
    for (const it of items) ul.append(line(it))
    d.append(ul)
    wrap.append(d)
  }
  const owner = (li, e) => li.insertBefore(el('span', { class: 'cmp-owner', text: `${shortType(e.uid)}.` }), li.childNodes[2])

  category('Types moved', b.movedTypes.sort(byType),
    'The type still exists, but a compiled mod references it by its old namespace and assembly, so the game ' +
    'cannot resolve it. Rebuild the mod against the new version; the source usually needs no more than a new ' +
    'using directive or a new assembly reference.',
    e => {
      const li = el('li', { class: 'cmp-line cmp-changed' }, badge('changed'), ' ',
        link(toV, e.t.h, `${e.t.k} ${shortType(e.uid)}`, e.uid))
      if (e.movedFrom) li.append(note(`namespace ${e.old.n} → ${e.t.n}`))
      if (e.movedAssembly) li.append(note(`assembly ${e.movedAssembly}.dll → ${e.t.a}.dll`))
      return li
    })
  category('Types removed', b.removedTypes.sort(byType),
    `Gone in ${toLabel}. A mod that uses one of these needs a replacement before it can be rebuilt.`,
    e => typeLine('removed', fromV, e))
  category('Members removed', b.removedMembers.sort((x, y) => byType(x.e, y.e)),
    `Gone in ${toLabel} while the type remains. Calls to them fail with a missing method or field.`,
    ({ e, id }) => {
      const li = memberLine('removed', fromV, e.movedFrom || e.uid, e.old.h, id)
      owner(li, e)
      return li
    })
  category('Members with a changed signature', b.changedMembers.sort((x, y) => byType(x.e, y.e)),
    'Same name, different declaration: modifiers, return type, parameter types or a parameter type that moved ' +
    'namespace. A compiled call binds to the exact signature, so it fails until the mod is rebuilt, and the ' +
    'code must change wherever the parameters or the return type did.',
    ({ e, c }) => {
      const li = memberLine('changed', toV, e.uid, e.t.h, c.id, c.why)
      owner(li, e)
      if (c.oldId !== c.id) li.querySelector('a').title += `\nwas: ${memberUid(e.movedFrom || e.uid, c.oldId)}`
      return li
    })
  category('Types with a changed declaration', b.changedTypes.sort(byType),
    'The base type, the interfaces, or a modifier such as sealed, abstract or static changed. A mod that ' +
    'derives from the type or casts to it may fail to load or behave differently.',
    e => el('li', { class: 'cmp-line cmp-changed' }, badge('changed'), ' ',
      link(toV, e.t.h, `${e.t.k} ${shortType(e.uid)}`, e.uid), note('declaration changed')))
  return wrap
}

function render(result, fromV, toV, manifest, sections) {
  const { spaces, totals } = result
  const out = el('div', { class: 'cmp-result' })
  const total = Object.values(totals).reduce((a, b) => a + b, 0)
  const fromLabel = labelOf(fromV, manifest), toLabel = labelOf(toV, manifest)

  const summary = el('p', { class: 'cmp-summary' })
  summary.append(el('strong', { text: `${fromLabel} → ${toLabel}: ` }))
  if (!total) {
    summary.append('no difference in the documented public API.')
    out.append(summary)
    return out
  }
  const parts = [
    [totals.typesAdded, 'added', 'type', 'types'],
    [totals.typesRemoved, 'removed', 'type', 'types'],
    [totals.typesMoved, 'moved', 'type', 'types'],
    [totals.membersAdded, 'added', 'member', 'members'],
    [totals.membersRemoved, 'removed', 'member', 'members'],
    [totals.membersChanged, 'changed', 'member', 'members'],
  ]
  summary.append(parts.filter(p => p[0]).map(([n, what, one, many]) => `${n} ${n === 1 ? one : many} ${what}`).join(', ') + '.')
  out.append(summary)
  out.append(el('p', { class: 'text-body-secondary small',
    text: `Added and changed entries link to ${toLabel}, removed entries to ${fromLabel}.` }))

  const filter = el('input', { class: 'form-control form-control-sm cmp-filter', type: 'search',
    placeholder: 'Filter by name', 'aria-label': 'Filter by name' })
  out.append(filter)

  out.append(el('h2', { id: 'breaking', text: 'Breaking changes' }))
  out.append(renderBreaking(breakingChanges(spaces), fromV, toV, fromLabel, toLabel))
  out.append(el('h2', { id: 'all-changes', text: 'All changes by namespace' }))
  out.append(el('p', { class: 'text-body-secondary small',
    text: 'Additions included. A moved type is listed under its new namespace.' }))

  // Large diffs (a major release) run to thousands of lines; collapse the
  // namespaces then so the page stays navigable. Small ones open up front.
  const open = total <= 400

  const names = [...spaces.keys()].sort((a, b) => a.localeCompare(b))
  for (const ns of names) {
    const b = spaces.get(ns)
    const details = el('details', { class: 'cmp-namespace' })
    if (open) details.open = true
    const sum = el('summary')
    sum.append(el('span', { class: 'cmp-ns', text: ns || '(no namespace)' }), ' ')
    if (b.added.length) sum.append(badge('added', `+${b.added.length}`), ' ')
    if (b.removed.length) sum.append(badge('removed', `−${b.removed.length}`), ' ')
    if (b.changed.length) sum.append(badge('changed', `~${b.changed.length}`), ' ')
    const sect = new Set([...b.added, ...b.removed, ...b.changed].map(e => sections[e.t.s] || e.t.s))
    sum.append(el('span', { class: 'cmp-count text-body-secondary small', text: [...sect].join(', ') }))
    details.append(sum)
    const ul = el('ul', { class: 'cmp-types' })
    const byName = (x, y) => shortType(x.uid).localeCompare(shortType(y.uid))
    for (const e of b.added.sort(byName)) ul.append(typeLine('added', toV, e))
    for (const e of b.removed.sort(byName)) ul.append(typeLine('removed', fromV, e))
    for (const e of b.changed.sort(byName)) ul.append(changedType(fromV, toV, e))
    details.append(ul)
    out.append(details)
  }

  filter.addEventListener('input', () => {
    const q = filter.value.trim().toLowerCase()
    for (const d of out.querySelectorAll('details.cmp-namespace, details.cmp-category')) {
      let any = false
      for (const li of d.querySelectorAll('ul.cmp-types > li')) {
        const hit = !q || li.textContent.toLowerCase().includes(q)
        li.hidden = !hit
        any = any || hit
      }
      d.hidden = !any
      if (q) d.open = true
    }
  })
  return out
}

// The version the reader is looking at is the natural "to"; "from" defaults to
// the previous version on the same line (release or early access).
function defaults(manifest, versions) {
  const params = new URLSearchParams(location.search)
  let to = params.get('to') || currentVersion() || manifest.latest || manifest.stable || versions[0]
  if (!versions.includes(to)) to = versions[0]
  let from = params.get('from')
  if (!from || !versions.includes(from)) {
    const line = versions.filter(v => isEarlyAccess(v) === isEarlyAccess(to))
    const i = line.indexOf(to)
    from = i >= 0 && i + 1 < line.length ? line[i + 1] : line[line.length - 1]
  }
  return { from, to }
}

function select(id, versions, manifest, value) {
  const s = el('select', { id, class: 'form-select form-select-sm' })
  for (const v of versions) s.append(el('option', { value: v, text: labelOf(v, manifest) }))
  s.value = value
  return s
}

export async function installCompare() {
  const host = document.getElementById('api-compare')
  if (!host) return
  const manifest = await loadManifest()
  if (!manifest || !(manifest.versions || []).length) {
    host.append(el('p', { class: 'text-body-secondary', text: 'The version list is not available, so there is nothing to compare.' }))
    return
  }
  const versions = [...manifest.versions]
  const current = currentVersion()
  if (current && !versions.includes(current)) versions.unshift(current)
  const { from, to } = defaults(manifest, versions)

  const form = el('form', { class: 'cmp-form row g-2 align-items-end' })
  const fromSel = select('cmp-from', versions, manifest, from)
  const toSel = select('cmp-to', versions, manifest, to)
  const field = (label, control) => el('div', { class: 'col-auto' },
    el('label', { class: 'form-label small mb-1', for: control.id, text: label }), control)
  const button = el('button', { class: 'btn btn-primary btn-sm', type: 'submit', text: 'Compare' })
  form.append(field('From', fromSel), field('To', toSel), el('div', { class: 'col-auto' }, button))
  const status = el('p', { class: 'cmp-status text-body-secondary' })
  const result = el('div')
  host.append(form, status, result)

  let running = 0
  async function run() {
    const id = ++running
    const f = fromSel.value, t = toSel.value
    result.replaceChildren()
    if (f === t) { status.textContent = 'Pick two different versions.'; return }
    status.textContent = 'Loading both indexes…'
    const url = new URL(location.href)
    url.searchParams.set('from', f); url.searchParams.set('to', t)
    history.replaceState(null, '', url)
    try {
      const [a, b] = await Promise.all([loadIndex(f), loadIndex(t)])
      if (id !== running) return
      status.textContent = ''
      result.replaceChildren(render(diff(a, b), f, t, manifest, Object.assign({}, a.sections, b.sections)))
    } catch (e) {
      if (id !== running) return
      status.textContent = e.message
    }
  }
  form.addEventListener('submit', ev => { ev.preventDefault(); run() })
  run()
}
