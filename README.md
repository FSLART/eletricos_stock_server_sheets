# Gaveta · Stock de componentes

Interface em **Vue 3**, com componentes Single File (`.vue`) e Vite. A mesma
aplicação funciona com a API Flask e com o Google Apps Script.

## Modo local (por defeito)

O Flask usa SQLite em `meu_servidor/stock.db` e guarda imagens em
`meu_servidor/uploads/`. Não precisa de Google, credenciais ou ligação à Internet
para gerir o stock. Os registos locais existentes são preservados. Faz cópias de
segurança da base de dados e da pasta de imagens.

`STORAGE_MODE` permite escolher `local` (valor por defeito), `excel` (sincronizar
com `Stock_sala.xlsx`) ou `google` (sincronizar com Google Sheets, requer
credenciais válidas). Em modo local não há sincronização automática com folhas
de cálculo. A implementação separada Apps Script continua a usar Google Sheets.

## Desenvolvimento

Requer Node.js 22.12+ ou 24+ e npm.

```sh
npm ci
npm run dev
```

Inicia também o servidor Flask na porta 5000. Na raiz do projeto, prepara o
ambiente Python uma vez:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r meu_servidor/requirements.txt
```

No Windows, usa `python -m venv .venv` e
`.venv\Scripts\python.exe -m pip install -r meu_servidor/requirements.txt`.

Depois, mantém dois terminais abertos:

```sh
# Terminal 1: backend Flask
npm run dev:api
# Terminal 2: frontend Vue
npm run dev
```

O Vite encaminha `/api` e `/uploads` para o Flask; abre o endereço HTTP indicado
pelo Vite, não o ficheiro `index.html` diretamente. `ECONNREFUSED 127.0.0.1:5000`
significa que o backend não está iniciado. Para o arranque com túneis no Windows,
consulta as [instruções do servidor](meu_servidor/README.md).

## Build e testes

```sh
npm test
npm run build
npm run test:build
.venv/bin/python -m unittest discover -s tests -p test_local_storage.py -v
```

Edita `frontend/src/`, não os HTML gerados. O build inclui o runtime Vue, o
JavaScript e o CSS num único HTML, sem dependência de CDN para arrancar a app.
As fontes Google continuam opcionais, com fontes locais como alternativa.
O build atualiza:

- `meu_servidor/templates/index.html` — servidor principal;
- `apps_script/index.html` — implementação Google Apps Script;
- `serverstocklart-main/meu_servidor/templates/index.html` — cópia antiga do servidor;
- `dist/index.html` — artefacto local de build.

Os HTML gerados estão versionados para que o arranque habitual do Flask continue
a funcionar sem instalar Node.js no servidor. Para publicar no Apps Script,
copia o novo `apps_script/index.html` e o `Code.gs` existente para o projeto e
publica uma nova versão da aplicação web. O frontend deteta `google.script.run`
automaticamente; fora do Apps Script usa os endpoints HTTP do Flask.

## Estrutura

- `frontend/src/App.vue`: estado reativo, filtros, atualizações e movimentos;
- `frontend/src/components/`: lista de stock e formulários;
- `frontend/src/api.js`: transportes Flask/Apps Script, cache, fila offline e imagens;
- `frontend/src/style.css`: estilos e layout responsivo;
- `scripts/build.mjs`: build autónomo para ambas as plataformas;
- `tests/`: testes de componentes, APIs e compatibilidade offline.

Mantêm-se as chaves `stock.pending.v1` e `stock.data.v1`, incluindo o formato das
operações pendentes de cada implementação. Se o browser bloquear o armazenamento,
as operações online continuam disponíveis; as escritas offline apresentam erro
em vez de indicar falsamente que foram guardadas.

O backend Python continua responsável pelo SQLite, Excel, Google Sheets e
ficheiros carregados; o Apps Script continua responsável pela integração com
Sheets/Drive. A cópia antiga mantém as limitações da sua API original (incluindo
a ausência de upload de imagens). O ZIP histórico é um arquivo de origem e não
é usado para executar a aplicação.

Para reverter a migração, restaura os ficheiros da revisão anterior com Git.
Não é necessária uma migração de dados.
