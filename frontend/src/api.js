const PENDING_KEY = 'stock.pending.v1'
const DATA_KEY = 'stock.data.v1'

export function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback }
  catch { return fallback }
}

export function writeStored(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true }
  catch { return false }
}

const routes = {
  data: () => ['/api/data', 'GET'],
  move: () => ['/api/move', 'POST'],
  newCategory: () => ['/api/categories', 'POST'],
  deleteCategory: p => [`/api/categories/${encodeURIComponent(p.name)}`, 'DELETE'],
  deleteItem: p => [`/api/items/${p.id}`, 'DELETE'],
  step: p => [`/api/items/${p.id}/step`, 'POST'],
}

export function createApi() {
  const appsScript = Boolean(globalThis.google?.script?.run)
  let syncing = false

  function callGoogle(action, payload) {
    return new Promise((resolve, reject) => {
      google.script.run.withSuccessHandler(resolve).withFailureHandler(reject).api(action, payload)
    })
  }

  function requestFor(action, payload = {}) {
    const [url, method] = routes[action](payload)
    return { url, method, body: method === 'GET' ? null : payload }
  }

  async function http({ url, method, body }) {
    let response
    try {
      response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      })
    } catch (cause) {
      const error = new Error('Sem ligação ao servidor', { cause })
      error.offline = true
      throw error
    }
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.error || 'Erro no servidor')
    return data
  }

  async function direct(action, payload = {}) {
    if (appsScript) {
      if (!navigator.onLine) {
        const error = new Error('Sem ligação ao servidor')
        error.offline = true
        throw error
      }
      return callGoogle(action, payload)
    }
    return http(requestFor(action, payload))
  }

  async function request(action, payload = {}) {
    try { return await direct(action, payload) }
    catch (error) {
      if (action === 'data' || !(error.offline || !navigator.onLine)) throw error
      const requests = readStored(PENDING_KEY, [])
      // Preserve each deployment's existing queue format during migration.
      requests.push(appsScript ? { action, payload } : requestFor(action, payload))
      if (!writeStored(PENDING_KEY, requests)) {
        throw new Error('Sem ligação. Este browser não permite guardar a operação offline.')
      }
      return { queued: true, msg: 'Sem ligação. Operação guardada e será sincronizada quando o servidor voltar.' }
    }
  }

  async function load() {
    try {
      const data = await request('data')
      writeStored(DATA_KEY, data)
      return data
    } catch (error) {
      const cached = readStored(DATA_KEY, null)
      if (!cached) throw error
      return cached
    }
  }

  async function syncPending(notify = () => {}) {
    if (syncing || !navigator.onLine) return 0
    syncing = true
    let count = 0
    try {
      // Re-read after each await so writes queued meanwhile are never lost.
      while (true) {
        const pending = readStored(PENDING_KEY, [])[0]
        if (!pending) break
        try {
          if (pending.action) await direct(pending.action, pending.payload || {})
          else await http(pending)
          count++
        } catch (error) {
          if (error.offline || !navigator.onLine) break
          notify(error.message || 'Uma operação offline não foi aceite pelo servidor')
        }
        const requests = readStored(PENDING_KEY, [])
        requests.shift()
        if (!writeStored(PENDING_KEY, requests)) break
      }
    } finally { syncing = false }
    return count
  }

  async function uploadImage(file) {
    if (appsScript) return (await callGoogle('uploadImage', { data: await jpegBase64(file) })).url
    const body = new FormData()
    body.append('image', file)
    const response = await fetch('/api/images', { method: 'POST', body })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.error || 'Não foi possível enviar a imagem')
    return data.url
  }

  return { request, load, syncPending, uploadImage }
}

async function jpegBase64(file) {
  let bitmap
  try { bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' }) }
  catch { throw new Error('O ficheiro enviado não é uma imagem válida') }
  try {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 800
    const ctx = canvas.getContext('2d')
    const scale = Math.min(800 / bitmap.width, 800 / bitmap.height)
    const w = bitmap.width * scale, h = bitmap.height * scale
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, 800, 800)
    ctx.drawImage(bitmap, (800 - w) / 2, (800 - h) / 2, w, h)
    return canvas.toDataURL('image/jpeg', 0.88).split(',')[1]
  } finally { bitmap.close() }
}
