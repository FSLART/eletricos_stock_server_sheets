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

### Editar componentes e categorias

O stock aparece numa tabela compacta com colunas para as propriedades presentes
nos componentes. Clica num cabeçalho para ordenar; clica novamente para inverter
a ordem. Os painéis de filtros permitem pesquisar e selecionar vários valores
da mesma propriedade. Valores da mesma propriedade são alternativas; propriedades
diferentes, pesquisa, categoria, stock e imagens são combinados. Usa **Limpar
filtros** para voltar a todos os componentes. Em ecrãs estreitos, os painéis e a
tabela permitem deslocamento horizontal.

Componentes sem fotografia mostram um ícone padrão da categoria (resistências,
conectores, condensadores, LEDs, díodos, transístores, potenciómetros, indutores
e cristais), ou um ícone genérico para outras categorias. Os ícones estão
incluídos no HTML e funcionam offline; fotografias carregadas têm prioridade.
Os filtros de imagens continuam a distinguir componentes com e sem fotografia
própria. Os ícones são do [Tabler Icons](https://github.com/tabler/tabler-icons)
(licença MIT incluída em `frontend/src/assets/component-icons/LICENSE`), com um
símbolo original para transístores.

No servidor principal em modo local, usa **Editar** junto a um componente para
alterar as propriedades, a quantidade total ou a imagem. Sem selecionar outra
imagem, a atual é mantida; podes removê-la explicitamente.

Usa **Editar** junto a uma categoria para mudar o nome, permitir imagens ou
adicionar, renomear e remover propriedades. Renomear campos mantém os valores
dos componentes. A remoção de campos pede confirmação e alterações que tornem
dois componentes iguais são rejeitadas. Os controlos de edição só aparecem nas
implementações que suportam estas operações (servidor principal em modo local).

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
