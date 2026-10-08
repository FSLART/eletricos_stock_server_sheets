import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApi } from '../frontend/src/api.js'

const response = (data, ok = true) => ({ ok, json: async () => data })
beforeEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
  vi.stubGlobal('fetch', vi.fn())
})

describe('Flask adapter and offline compatibility', () => {
  it('maps actions to the existing HTTP routes and encoded category names', async () => {
    fetch.mockResolvedValue(response({ msg: 'ok' }))
    const api = createApi()
    await api.request('deleteCategory', { name: 'R&D / LEDs' })
    expect(fetch).toHaveBeenCalledWith('/api/categories/R%26D%20%2F%20LEDs', expect.objectContaining({ method: 'DELETE' }))
    await api.request('step', { id: 7, delta: -1 })
    expect(fetch).toHaveBeenLastCalledWith('/api/items/7/step', expect.objectContaining({ method: 'POST', body: '{"id":7,"delta":-1}' }))
  })

  it('uses the previous cached snapshot after a connection failure', async () => {
    const data = { categories: [], items: [{ id: 2 }] }
    localStorage.setItem('stock.data.v1', JSON.stringify(data))
    fetch.mockRejectedValue(new TypeError('Failed to fetch'))
    expect(await createApi().load()).toEqual(data)
  })

  it('queues failed writes and replays the previous HTTP queue format', async () => {
    fetch.mockRejectedValueOnce(new TypeError('offline'))
    const api = createApi()
    expect(await api.request('step', { id: 1, delta: 2 })).toMatchObject({ queued: true })
    expect(JSON.parse(localStorage.getItem('stock.pending.v1'))).toHaveLength(1)
    fetch.mockResolvedValue(response({ msg: 'ok' }))
    expect(await api.syncPending()).toBe(1)
    expect(JSON.parse(localStorage.getItem('stock.pending.v1'))).toEqual([])
  })

  it('keeps a queued write on transport failure and rejects server validation errors', async () => {
    localStorage.setItem('stock.pending.v1', JSON.stringify([{ url: '/api/move', method: 'POST', body: {} }]))
    fetch.mockRejectedValueOnce(new TypeError('offline'))
    const api = createApi()
    expect(await api.syncPending()).toBe(0)
    expect(JSON.parse(localStorage.getItem('stock.pending.v1'))).toHaveLength(1)
    fetch.mockResolvedValue(response({ error: 'Quantidade inválida' }, false))
    await expect(api.request('move', {})).rejects.toThrow('Quantidade inválida')
    expect(JSON.parse(localStorage.getItem('stock.pending.v1'))).toHaveLength(1)
  })

  it('does not claim a write is saved when storage is blocked', async () => {
    fetch.mockRejectedValue(new TypeError('offline'))
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    await expect(createApi().request('move', {})).rejects.toThrow('não permite guardar')
  })

  it('retains writes appended while an earlier write is being replayed', async () => {
    const earlier = { url: '/api/move', method: 'POST', body: { qty: 1 } }
    localStorage.setItem('stock.pending.v1', JSON.stringify([earlier]))
    fetch.mockImplementationOnce(async () => {
      localStorage.setItem('stock.pending.v1', JSON.stringify([earlier, { ...earlier, body: { qty: 2 } }]))
      return response({})
    }).mockResolvedValue(response({}))
    expect(await createApi().syncPending()).toBe(2)
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})

describe('Apps Script adapter', () => {
  it('calls google.script.run and replays the existing Apps Script queue', async () => {
    const run = {
      withSuccessHandler(handler) { this.success = handler; return this },
      withFailureHandler(handler) { this.failure = handler; return this },
      api: vi.fn(function (action, payload) { this.success({ action, payload }) }),
    }
    vi.stubGlobal('google', { script: { run } })
    const api = createApi()
    expect(await api.request('step', { id: 3, delta: 10 })).toEqual({ action: 'step', payload: { id: 3, delta: 10 } })
    localStorage.setItem('stock.pending.v1', JSON.stringify([{ action: 'move', payload: { qty: 2 } }]))
    expect(await api.syncPending()).toBe(1)
    expect(run.api).toHaveBeenLastCalledWith('move', { qty: 2 })
    expect(fetch).not.toHaveBeenCalled()
  })
})
