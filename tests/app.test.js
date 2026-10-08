import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../frontend/src/App.vue'

const data = {
  categories: [{ name: 'LEDs', props: ['cor'], image: true }, { name: 'R&D', props: ['valor'], image: false }],
  items: [
    { id: 1, cat: 'LEDs', props: { cor: '<1A & azul' }, qty: 3, image: '' },
    { id: 2, cat: 'R&D', props: { valor: '10 Ω' }, qty: 20, image: '' },
  ],
}
let wrapper
beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => structuredClone(data) })))
  HTMLDialogElement.prototype.showModal = function () { this.open = true }
  HTMLDialogElement.prototype.close = function () { this.open = false }
})
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('renders safe text, filters search and categories, and reports totals', async () => {
  wrapper = mount(App)
  await flushPromises()
  expect(wrapper.find('.sub').text()).toBe('2 referências · 23 unidades')
  expect(wrapper.find('.chips').text()).toContain('<1A & azul')
  expect(wrapper.find('.chips').html()).toContain('&lt;1A &amp; azul')
  await wrapper.find('input[type=search]').setValue('10Ω')
  expect(wrapper.findAll('.row')).toHaveLength(1)
  await wrapper.find('input[type=search]').setValue('')
  await wrapper.findAll('nav .cat-row > button:first-child')[1].trigger('click')
  expect(wrapper.find('h1').text()).toBe('LEDs')
  expect(wrapper.find('.sub').text()).toBe('1 referências · 3 unidades')
})

it('clamps a decrement at zero and sends only the actual stock change', async () => {
  vi.useFakeTimers()
  wrapper = mount(App)
  await flushPromises()
  await wrapper.find('button[aria-label="Retirar 10"]').trigger('click')
  expect(wrapper.find('output').text()).toBe('0')
  await vi.advanceTimersByTimeAsync(151)
  expect(fetch).toHaveBeenCalledWith('/api/items/1/step', expect.objectContaining({ body: '{"id":1,"delta":-3}' }))
})

it('submits a movement using the selected dynamic properties', async () => {
  wrapper = mount(App)
  await flushPromises()
  await wrapper.find('.top .primary').trigger('click')
  const form = wrapper.find('dialog form')
  await form.find('.fields input').setValue('vermelho')
  await form.find('input[type=number]').setValue(4)
  await form.trigger('submit')
  await flushPromises()
  expect(fetch).toHaveBeenCalledWith('/api/move', expect.objectContaining({ body: JSON.stringify({ cat: 'LEDs', props: { cor: 'vermelho' }, qty: 4, mode: 'in', image: '' }) }))
})

it('handles an empty stock without opening an invalid movement', async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ categories: [], items: [] }) })
  wrapper = mount(App)
  await flushPromises()
  expect(wrapper.find('.top .primary').attributes('disabled')).toBeDefined()
  expect(wrapper.find('.empty').text()).toContain('Nada encontrado')
})
