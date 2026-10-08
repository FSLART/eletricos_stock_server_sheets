// Backend do stock em Google Apps Script. A Google Sheet e a unica base de dados:
// cada aba com as colunas id, categoria e quantidade e uma categoria, e as
// restantes colunas (exceto imagem) sao as propriedades dos componentes.
const SHEET_ID = '1dWmr7VUUz6z15ZCDjgjLnDV5nMwh8FQYtp1BOOjx6Go';
const BASE_COLUMNS = ['id', 'categoria', 'imagem', 'quantidade'];
const IMAGE_URL_RE = /^https:\/\/lh3\.googleusercontent\.com\/d\/[\w-]+$/;
let spreadsheet = null;

const norm = value => String(value).toLowerCase().replace(/\s+/g, '');
const ss = () => spreadsheet || (spreadsheet = SpreadsheetApp.openById(SHEET_ID));
// Sem argumentos extra: com locale pt_PT, "4,80,80" partia a formula (separadores).
const imageFormula = url => `=IMAGE("${url}")`;

function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('Gaveta · Gestão de stock')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// Unica funcao chamada pelo frontend, via google.script.run.api(...).
function api(action, payload) {
  if (!Object.prototype.hasOwnProperty.call(ACTIONS, action)) throw new Error('Ação desconhecida');
  // Leituras nao esperam pelo lock: com varios browsers a atualizar, faziam fila (3-17 s).
  if (action === 'data') return cachedData_();
  // ponytail: lock global serializa as escritas; chega para uma equipa pequena.
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    return ACTIONS[action](payload || {});
  } finally {
    const cache = CacheService.getScriptCache();
    cache.put('versao', String(Date.now()), 21600);
    cache.remove('data');
    lock.releaseLock();
  }
}

// ponytail: cache de 10 s; edicoes feitas a mao na Sheet aparecem com ate 10 s de atraso.
function cachedData_() {
  const cache = CacheService.getScriptCache();
  const hit = cache.get('data');
  if (hit) return JSON.parse(hit);
  const versao = cache.get('versao');
  const data = ACTIONS.data();
  // So guarda se nenhuma escrita aconteceu durante a leitura (senao guardava dados velhos).
  if (cache.get('versao') === versao) {
    try { cache.put('data', JSON.stringify(data), 10); } catch (e) { /* >100KB: fica sem cache */ }
  }
  return data;
}

function categories_() {
  const cats = ss().getSheets().map(readSheet_).filter(Boolean);
  // Linhas adicionadas a mao no Sheets sem id recebem o proximo id livre.
  // ponytail: nas leituras corre sem lock; duas leituras em simultaneo podem repetir um id (raro).
  let next = Math.max(0, ...cats.flatMap(c => c.items.map(i => i.id)));
  cats.forEach(c => c.items.forEach(i => {
    if (i.id) return;
    i.id = ++next;
    c.sheet.getRange(i.row, c.col.id + 1).setValue(i.id);
  }));
  return cats;
}

function readSheet_(sheet) {
  const range = sheet.getDataRange();
  const shown = range.getDisplayValues();
  const headers = shown[0].map(h => h.trim());
  const col = {};
  headers.forEach((h, i) => { col[h.toLowerCase()] = i; });
  // Abas sem estas colunas nao sao do stock e ficam intactas.
  if (!['id', 'categoria', 'quantidade'].every(h => h in col)) return null;
  const values = range.getValues();
  const formulas = range.getFormulas();
  const props = headers.filter(h => h && !BASE_COLUMNS.includes(h.toLowerCase()));
  // Como no Flask, o nome vem da coluna categoria; a aba pode chamar-se "Res (2)".
  const name = shown.slice(1).map(row => row[col.categoria].trim()).find(Boolean) || sheet.getName();
  const items = [];
  for (let r = 1; r < shown.length; r++) {
    if (shown[r].every(v => v === '') && formulas[r].every(v => v === '')) continue;
    const item = {
      row: r + 1,
      id: Number(values[r][col.id]) || 0,
      cat: name,
      props: {},
      qty: Number(values[r][col.quantidade]) || 0,
      image: '',
    };
    props.forEach(name => {
      const value = shown[r][headers.indexOf(name)];
      if (value !== '') item.props[name] = value;
    });
    if ('imagem' in col) {
      const cell = formulas[r][col.imagem] || shown[r][col.imagem];
      const match = cell.match(/^=IMAGE\("([^"]+)"/i);
      item.image = match ? match[1] : cell;
    }
    items.push(item);
  }
  return {sheet, name, headers, col, props, image: 'imagem' in col, items};
}

function findItem_(id) {
  for (const c of categories_()) {
    const item = c.items.find(i => i.id === Number(id));
    if (item) return {c, item};
  }
  throw new Error('Item não encontrado');
}

function imageFolder_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('IMAGE_FOLDER_ID');
  if (id) return DriveApp.getFolderById(id);
  const folder = DriveApp.createFolder('Stock imagens');
  props.setProperty('IMAGE_FOLDER_ID', folder.getId());
  return folder;
}

const ACTIONS = {
  data() {
    const cats = categories_();
    return {
      categories: cats.map(c => ({name: c.name, props: c.props, image: c.image})),
      items: cats.flatMap(c => c.items)
        .map(({id, cat, props, qty, image}) => ({id, cat, props, qty, image}))
        .sort((a, b) => a.id - b.id),
    };
  },

  move({cat, props = {}, qty, mode, image = ''}) {
    qty = Number(qty);
    if (!Number.isInteger(qty) || qty < 1) throw new Error('A quantidade tem de ser 1 ou mais');
    const cats = categories_();
    const c = cats.find(x => x.name === String(cat || '').trim());
    if (!c) throw new Error('Categoria não encontrada');
    const values = c.props.map(name => String(props[name] || '').trim());
    if (!values.length || values.some(v => !v)) throw new Error('Preenche a categoria e todas as propriedades');
    image = String(image).trim();
    if (image && !c.image) throw new Error('Esta categoria não aceita imagens');
    if (image && !IMAGE_URL_RE.test(image)) throw new Error('Imagem inválida');
    // Dois itens sao o mesmo quando todas as propriedades normalizadas coincidem.
    const key = values.map(norm).join('|');
    const item = c.items.find(i => c.props.map(name => norm(i.props[name] || '')).join('|') === key);
    const cell = column => c.sheet.getRange(item.row, c.col[column] + 1);

    if (mode === 'out') {
      if (!item) throw new Error('Esse item não existe no stock');
      if (item.qty < qty) throw new Error(`Só há ${item.qty} em stock`);
      cell('quantidade').setValue(item.qty - qty);
      return {msg: `Retirado. Restam ${item.qty - qty}`};
    }
    if (item) {
      cell('quantidade').setValue(item.qty + qty);
      if (image) {
        cell('imagem').setValue(imageFormula(image));
        c.sheet.setRowHeight(item.row, 90);
      }
      return {msg: `Quantidade somada: agora ${item.qty + qty}`};
    }
    const fixed = {
      id: Math.max(0, ...cats.flatMap(x => x.items.map(i => i.id))) + 1,
      categoria: c.name,
      imagem: image ? imageFormula(image) : '',
      quantidade: qty,
    };
    const row = c.headers.map(h => BASE_COLUMNS.includes(h.toLowerCase())
      ? fixed[h.toLowerCase()]
      : c.props.includes(h) ? values[c.props.indexOf(h)] : '');
    const r = c.sheet.getLastRow() + 1;
    // Texto simples: sem isto a Sheet transforma "4.7" numa data (ex.: 46119 no Flask).
    c.props.forEach(h => c.sheet.getRange(r, c.headers.indexOf(h) + 1).setNumberFormat('@'));
    c.sheet.getRange(r, 1, 1, row.length).setValues([row])
      .setHorizontalAlignment('center').setVerticalAlignment('middle');
    // Como no Flask: todas as linhas de categorias com imagem tem 90px.
    if (c.image) c.sheet.setRowHeight(r, 90);
    return {msg: 'Item novo adicionado'};
  },

  step({id, delta}) {
    delta = Number(delta);
    if (!Number.isInteger(delta)) throw new Error('Valor inválido');
    const {c, item} = findItem_(id);
    c.sheet.getRange(item.row, c.col.quantidade + 1).setValue(Math.max(0, item.qty + delta));
    return {ok: true};
  },

  deleteItem({id}) {
    const {c, item} = findItem_(id);
    c.sheet.deleteRow(item.row);
    return {ok: true};
  },

  newCategory({name, props, image}) {
    name = String(name || '').trim();
    props = [...new Set((props || []).map(p => String(p).trim()).filter(Boolean))];
    if (!name || !props.length) throw new Error('Indica o nome e pelo menos uma propriedade');
    if (props.some(p => BASE_COLUMNS.includes(p.toLowerCase()))) {
      throw new Error(`As propriedades não podem chamar-se ${BASE_COLUMNS.join(', ')}`);
    }
    const taken = [...categories_().map(c => c.name), ...ss().getSheets().map(s => s.getName())];
    if (taken.some(n => n.toLowerCase() === name.toLowerCase())) throw new Error('Essa categoria já existe');
    const headers = ['id', 'categoria', ...props, ...(image ? ['imagem'] : []), 'quantidade'];
    const sheet = ss().insertSheet(name);
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]).setHorizontalAlignment('center');
    sheet.getRange(2, 3, sheet.getMaxRows() - 1, props.length).setNumberFormat('@');
    if (image) sheet.setColumnWidth(headers.indexOf('imagem') + 1, 100);
    return {msg: 'Categoria pronta para receber o primeiro item'};
  },

  deleteCategory({name}) {
    const c = categories_().find(x => x.name === name);
    if (!c) throw new Error('Categoria não encontrada');
    // Uma folha Google tem de ter pelo menos uma aba: a ultima e limpa em vez de apagada.
    if (ss().getSheets().length > 1) ss().deleteSheet(c.sheet);
    else c.sheet.clear();
    return {msg: 'Categoria apagada' + (c.items.length ? ` com ${c.items.length} referência(s)` : '')};
  },

  // Recebe um JPEG ja normalizado pelo browser e guarda-o no Drive do dono do script.
  uploadImage({data}) {
    const bytes = Utilities.base64Decode(String(data || ''));
    // Bytes sao assinados em Apps Script: 0xFF 0xD8 (inicio de JPEG) = -1 -40.
    if (bytes.length > 5 * 1024 * 1024 || bytes[0] !== -1 || bytes[1] !== -40) {
      throw new Error('O ficheiro enviado não é uma imagem válida');
    }
    const file = imageFolder_().createFile(Utilities.newBlob(bytes, 'image/jpeg', Utilities.getUuid() + '.jpg'));
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    return {url: 'https://lh3.googleusercontent.com/d/' + file.getId()};
  },
};

// Executar uma vez no editor: pede as autorizacoes e testa a logica numa folha
// temporaria (vai para o lixo no fim), sem tocar no stock real.
function selfTest() {
  spreadsheet = SpreadsheetApp.create('stock-selftest');
  const check = (ok, what) => { if (!ok) throw new Error('selfTest falhou: ' + what); };
  const fails = fn => { try { fn(); return false; } catch (e) { return true; } };
  try {
    const led = {cor: 'Vermelho', tamanho: '5'};
    ACTIONS.newCategory({name: 'LEDs', props: ['cor', 'tamanho']});
    check(fails(() => ACTIONS.newCategory({name: 'leds', props: ['x']})), 'categoria duplicada');
    ACTIONS.move({cat: 'LEDs', props: led, qty: 10, mode: 'in'});
    ACTIONS.move({cat: 'LEDs', props: {cor: ' vermelho', tamanho: '5 '}, qty: 5, mode: 'in'});
    let items = ACTIONS.data().items;
    check(items.length === 1 && items[0].qty === 15, 'entrada soma no mesmo item');
    check(fails(() => ACTIONS.move({cat: 'LEDs', props: led, qty: 99, mode: 'out'})), 'saida acima do stock');
    ACTIONS.move({cat: 'LEDs', props: led, qty: 3, mode: 'out'});
    check(ACTIONS.data().items[0].qty === 12, 'saida subtrai');
    ACTIONS.step({id: items[0].id, delta: -100});
    check(ACTIONS.data().items[0].qty === 0, 'step nunca fica negativo');
    spreadsheet.getSheetByName('LEDs').appendRow(['', 'LEDs', 'Azul', '3', 7]);
    items = ACTIONS.data().items;
    check(items.length === 2 && items[1].id === items[0].id + 1, 'linha manual recebe id');
    check(fails(() => ACTIONS.uploadImage({data: Utilities.base64Encode('nao e jpeg')})), 'upload rejeita lixo');
    ACTIONS.deleteItem({id: items[0].id});
    check(ACTIONS.data().items.length === 1, 'apagar item');
    ACTIONS.deleteCategory({name: 'LEDs'});
    check(ACTIONS.data().categories.length === 0, 'apagar categoria');
    // Aba criada pelo Flask: nome da aba != categoria, e "4.7" tem de ficar texto.
    spreadsheet.insertSheet('Res (2)').getRange(1, 1, 2, 4)
      .setValues([['id', 'categoria', 'valor', 'quantidade'], [1, 'Res', '10k', 3]]);
    check(fails(() => ACTIONS.newCategory({name: 'res', props: ['x']})), 'nome vem da coluna categoria');
    ACTIONS.move({cat: 'Res', props: {valor: '4.7'}, qty: 1, mode: 'in'});
    check(ACTIONS.data().items.some(i => i.props.valor === '4.7'), '4.7 fica texto, nao data');
    Logger.log('selfTest OK');
  } finally {
    DriveApp.getFileById(spreadsheet.getId()).setTrashed(true);
  }
}

// Executar uma vez no editor: cria as categorias que so existiam no SQLite do Flask.
function importarCategorias() {
  const antigas = [
    ['Condensadores', ['tamanho', 'tensão', 'capacidade']],
    ['LEDs', ['cor', 'tamanho']],
    ['Díodos', ['referência', 'tipo', 'tensão inversa (V)', 'corrente (A)']],
    ['Transístores', ['referência', 'tipo (NPN/PNP)', 'ganho hFE', 'corrente máx (A)']],
    ['Potenciómetros', ['valor (Ω)', 'tipo', 'eixo']],
    ['Indutores', ['valor (µH)', 'corrente (A)']],
    ['Cristais', ['frequência (MHz)']],
    ['Conectores', ['Entradas', 'Waterproof', 'Tipo'], true],
  ];
  const existentes = categories_().map(c => c.name.toLowerCase());
  antigas.filter(([name]) => !existentes.includes(name.toLowerCase()))
    .forEach(([name, props, image]) => ACTIONS.newCategory({name, props, image}));
  Logger.log('Categorias: ' + categories_().map(c => c.name).join(', '));
}
