import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../frontend/src/App.vue'

const data = {
  can_edit: true,
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

it('combines property and stock filters and clears them together with search', async () => {
  wrapper = mount(App)
  await flushPromises()
  expect(wrapper.find('table').exists()).toBe(true)
  await wrapper.find('input[aria-label="Filtrar cor: <1A & azul"]').setValue(true)
  expect(wrapper.findAll('tbody .row')).toHaveLength(1)
  expect(wrapper.find('tbody').text()).toContain('LEDs')
  await wrapper.find('select[aria-label="Filtrar stock"]').setValue('available')
  expect(wrapper.findAll('tbody .row')).toHaveLength(1)
  await wrapper.find('select[aria-label="Filtrar stock"]').setValue('empty')
  expect(wrapper.findAll('tbody .row')).toHaveLength(0)
  await wrapper.find('input[aria-label="Pesquisar componentes"]').setValue('nothing')
  await wrapper.find('button[aria-label="Limpar filtros"]').trigger('click')
  expect(wrapper.findAll('tbody .row')).toHaveLength(2)
  expect(wrapper.find('.sub').text()).toBe('2 referências · 23 unidades')
})

it('sorts quantities numerically in both directions', async () => {
  wrapper = mount(App)
  await flushPromises()
  const sort = wrapper.find('button[aria-label="Ordenar por Quantidade"]')
  await sort.trigger('click')
  expect(wrapper.findAll('tbody output').map(row => row.text())).toEqual(['3', '20'])
  await sort.trigger('click')
  expect(wrapper.findAll('tbody output').map(row => row.text())).toEqual(['20', '3'])
})

it('keeps unused category properties out of the populated table and filters', async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ ...structuredClone(data), categories: [
    ...data.categories, { name: 'Empty category', props: ['unused'], image: false },
  ] }) })
  wrapper = mount(App)
  await flushPromises()
  expect(wrapper.find('button[aria-label="Ordenar por unused"]').exists()).toBe(false)
  expect(wrapper.find('input[aria-label="Pesquisar filtro unused"]').exists()).toBe(false)
})

it('filters image availability and resets property selections when switching category', async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ ...structuredClone(data), items: [
    { ...data.items[0], image: '/uploads/led.png' }, data.items[1],
  ] }) })
  wrapper = mount(App)
  await flushPromises()
  await wrapper.find('select[aria-label="Filtrar imagens"]').setValue('yes')
  expect(wrapper.findAll('tbody .row')).toHaveLength(1)
  await wrapper.find('select[aria-label="Filtrar imagens"]').setValue('no')
  expect(wrapper.find('tbody').text()).toContain('R&D')
  await wrapper.find('select[aria-label="Filtrar imagens"]').setValue('')
  await wrapper.find('input[aria-label="Filtrar cor: <1A & azul"]').setValue(true)
  await wrapper.findAll('nav .cat-row > button:first-child')[2].trigger('click')
  expect(wrapper.findAll('tbody .row')).toHaveLength(1)
  expect(wrapper.find('tbody').text()).toContain('10 Ω')
})

it('opens an item with its values and saves an absolute quantity without clearing its image', async () => {
  wrapper = mount(App)
  await flushPromises()
  await wrapper.find('button[aria-label="Editar componente"]').trigger('click')
  const form = wrapper.find('dialog form')
  expect(form.find('h2').text()).toBe('Editar componente')
  expect(form.find('.fields input').element.value).toBe('<1A & azul')
  await form.find('.fields input').setValue('verde')
  await form.find('input[type=number]').setValue(0)
  await form.trigger('submit')
  await flushPromises()
  const request = fetch.mock.calls.find(([url, options]) => url === '/api/items/1' && options.method === 'PATCH')
  expect(JSON.parse(request[1].body)).toEqual({ id: 1, props: { cor: 'verde' }, qty: 0 })
})

it('edits category and field names while sending the original field identity', async () => {
  wrapper = mount(App)
  await flushPromises()
  await wrapper.find('button[aria-label="Editar categoria LEDs"]').trigger('click')
  const form = wrapper.findAll('dialog form')[1]
  await form.find('input').setValue('Luzes')
  await form.find('.property-editor input').setValue('tonalidade')
  await form.trigger('submit')
  await flushPromises()
  const request = fetch.mock.calls.find(([url, options]) => url === '/api/categories/LEDs' && options.method === 'PATCH')
  expect(JSON.parse(request[1].body)).toEqual({ originalName: 'LEDs', name: 'Luzes', fields: [{ source: 'cor', name: 'tonalidade' }], image: true })
})

it('keeps rejected edits open with the server error and does not offer editing on unsupported backends', async () => {
  wrapper = mount(App)
  await flushPromises()
  await wrapper.find('button[aria-label="Editar categoria LEDs"]').trigger('click')
  fetch.mockResolvedValueOnce({ ok: false, json: async () => ({ error: 'Já existe essa categoria' }) })
  await wrapper.findAll('dialog form')[1].trigger('submit')
  await flushPromises()
  expect(wrapper.findAll('dialog')[1].element.open).toBe(true)
  expect(wrapper.find('[role=alert]').text()).toBe('Já existe essa categoria')
  wrapper.unmount()
  fetch.mockResolvedValue({ ok: true, json: async () => ({ ...structuredClone(data), can_edit: false }) })
  wrapper = mount(App)
  await flushPromises()
  expect(wrapper.find('button[aria-label="Editar componente"]').exists()).toBe(false)
})
