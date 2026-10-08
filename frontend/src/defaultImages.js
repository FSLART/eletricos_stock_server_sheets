import resistor from './assets/component-icons/circuit-resistor.svg?raw'
import connector from './assets/component-icons/plug.svg?raw'
import capacitor from './assets/component-icons/circuit-capacitor.svg?raw'
import led from './assets/component-icons/bulb.svg?raw'
import diode from './assets/component-icons/circuit-diode.svg?raw'
import transistor from './assets/component-icons/transistor.svg?raw'
import potentiometer from './assets/component-icons/adjustments-horizontal.svg?raw'
import inductor from './assets/component-icons/circuit-inductor.svg?raw'
import crystal from './assets/component-icons/wave-sine.svg?raw'
import generic from './assets/component-icons/cpu.svg?raw'
import license from './assets/component-icons/LICENSE?raw'

// Embed assets and their license in the single-file builds for offline use.
const image = (svg, color) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
  `<!-- Tabler Icons license (excludes original transistor symbol):\n${license}\n-->\n${svg.replace('currentColor', color)}`
)}`
const defaults = [
  [/^(res|resistencia|resistor|resistance)/, image(resistor, '#93632c')],
  [/(conector|connector|header|plug|socket)/, image(connector, '#486477')],
  [/(condensador|capacitor)/, image(capacitor, '#2676ae')],
  [/led|light.emitting/, image(led, '#bb8031')],
  [/(diodo|diode)/, image(diode, '#65548b')],
  [/(transistor|mosfet|bjt)/, image(transistor, '#475569')],
  [/(potenciometro|potentiometer|trimmer)/, image(potentiometer, '#327e87')],
  [/(indutor|inductor|coil)/, image(inductor, '#a66430')],
  [/(cristal|cristais|crystal|oscillator|oscilador)/, image(crystal, '#58729c')],
]
const fallback = image(generic, '#64748b')

export function defaultImage(category) {
  const name = String(category || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim()
  return defaults.find(([pattern]) => pattern.test(name))?.[1] || fallback
}
