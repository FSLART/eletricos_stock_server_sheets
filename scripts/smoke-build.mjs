import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { JSDOM, VirtualConsole } from 'jsdom'

const html = await readFile('dist/index.html', 'utf8')
const fixture = {
  categories: [{ name: 'LEDs', props: ['cor'], image: false }],
  items: [{ id: 1, cat: 'LEDs', props: { cor: '<azul & verde>' }, qty: 3, image: '' }],
}
for (const host of ['Flask', 'Apps Script']) {
  const errors = []
  const calls = []
  const virtualConsole = new VirtualConsole()
  virtualConsole.on('jsdomError', error => errors.push(error.message))
  const dom = new JSDOM(html, {
    url: 'http://localhost:5179/', runScripts: 'dangerously', virtualConsole,
    beforeParse(window) {
      window.fetch = async url => {
        calls.push(url)
        return { ok: true, json: async () => structuredClone(fixture) }
      }
      if (host === 'Apps Script') {
        const run = {
          withSuccessHandler(handler) { this.success = handler; return this },
          withFailureHandler() { return this },
          api(action) { calls.push(action); this.success(structuredClone(fixture)) },
        }
        window.google = { script: { run } }
      }
    },
  })
  try {
    await new Promise(resolve => setTimeout(resolve, 50))
    const doc = dom.window.document
    assert.deepEqual(errors, [], 'Production bundle must run without browser errors')
    assert.equal(calls[0], host === 'Flask' ? '/api/data' : 'data')
    assert.equal(doc.querySelector('output')?.textContent, '3')
    assert.equal(doc.querySelector('.val')?.textContent, '<azul & verde>')
    const search = doc.querySelector('input[type=search]')
    search.value = 'missing'
    search.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    await Promise.resolve()
    assert.equal(doc.querySelectorAll('.row').length, 0)
    console.log(`${host}: compiled bundle mounts, reads stock, escapes text and filters search`)
  } finally { dom.window.close() }
}
