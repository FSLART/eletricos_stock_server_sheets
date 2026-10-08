import { existsSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'
if (!existsSync(new URL(`../${python}`, import.meta.url))) {
  console.error('Create the Python environment first:\npython -m venv .venv\nThen install meu_servidor/requirements.txt using the Python inside .venv (see README.md).')
  process.exit(1)
}
const child = spawn(fileURLToPath(new URL(`../${python}`, import.meta.url)), [
  '-m', 'flask', '--app', 'meu_servidor/app.py', 'run', '--host', '127.0.0.1', '--port', '5000',
], { cwd: root, stdio: 'inherit', env: process.env })
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal))
child.on('error', error => { console.error(error.message); process.exitCode = 1 })
child.on('exit', code => { process.exitCode = code ?? 1 })
