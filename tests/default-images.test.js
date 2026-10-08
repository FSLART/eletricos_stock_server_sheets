import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StockItem from '../frontend/src/components/StockItem.vue'

const item = (cat, image = '') => ({ id: 1, cat, image, props: {}, qty: 10 })

it('uses distinct embedded defaults for the supported component categories and aliases', () => {
  const categories = ['Resistências', 'Conectores', 'Condensadores', 'LEDs', 'Díodos', 'Transístores', 'Potenciómetros', 'Indutores', 'Cristais']
  const sources = categories.map(cat => {
    const wrapper = mount(StockItem, { props: { item: item(cat) } })
    const src = wrapper.find('img').attributes('src')
    expect(src).toMatch(/^data:image\/svg\+xml/)
    expect(decodeURIComponent(src)).toContain('<svg')
    wrapper.unmount()
    return src
  })
  expect(new Set(sources).size).toBe(9)
  const wrapper = mount(StockItem, { props: { item: item('Res') } })
  expect(wrapper.find('img').attributes('src')).toBe(sources[0])
  wrapper.unmount()
})

it('uses a generic default for unknown categories without changing stored images', () => {
  const record = item('Custom category')
  const wrapper = mount(StockItem, { props: { item: record } })
  expect(wrapper.find('img').attributes('src')).toMatch(/^data:image\/svg\+xml/)
  expect(record.image).toBe('')
  wrapper.unmount()
})

it('prefers uploaded photos, falls back on loading errors and retries when the photo changes', async () => {
  const wrapper = mount(StockItem, { props: { item: item('Conectores', '/uploads/photo.png') } })
  expect(wrapper.find('img').attributes('src')).toBe('/uploads/photo.png')
  await wrapper.find('img').trigger('error')
  expect(wrapper.find('img').attributes('src')).toMatch(/^data:image\/svg\+xml/)
  await wrapper.setProps({ item: item('Conectores', '/uploads/replacement.png') })
  expect(wrapper.find('img').attributes('src')).toBe('/uploads/replacement.png')
  wrapper.unmount()
})
