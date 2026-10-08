# O Excel e a base de dados nao guardam dicionarios Python diretamente.
# json transforma, por exemplo, {"valor": "10"} em texto para guardar
# e faz o caminho inverso quando os dados sao lidos.
import json
import re
from io import BytesIO
# Le configuracoes do sistema, como o caminho personalizado do Excel,
# e fornece funcoes para substituir ficheiros temporarios com seguranca.
import os
# SQLite e a base de dados local onde ficam categorias, componentes e quantidades.
import sqlite3
# Permite executar o verificador do Excel sem bloquear os pedidos web.
import threading
# Faz a thread esperar alguns segundos entre duas verificacoes do Excel.
import time
# Permite criar funcoes que funcionam com o bloco "with".
from contextlib import contextmanager
# Representa caminhos de ficheiros de forma independente do sistema operativo.
from pathlib import Path
from urllib.parse import urlparse

# Flask recebe pedidos HTTP; jsonify responde em JSON, render_template entrega
# a pagina HTML e request permite ler os dados enviados pelo frontend.
from flask import Flask, jsonify, render_template, request, send_from_directory
# Workbook cria um livro vazio; load_workbook abre o ficheiro ja existente.
from openpyxl import Workbook, load_workbook
# Estas classes pertencem ao formato antigo que criava uma tabela Excel.
from openpyxl.worksheet.table import Table, TableStyleInfo
# Import mantido por compatibilidade com a versao anterior da escrita Excel.
from openpyxl.utils.cell import range_boundaries
from openpyxl.utils import get_column_letter
import gspread
from google.oauth2.service_account import Credentials
from uuid import uuid4
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, UnidentifiedImageError

# Este objeto regista as rotas e configura o servidor web da aplicacao.
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
# Evita que o Flask reorganize alfabeticamente os campos enviados ao frontend.
app.json.sort_keys = False
# Permite construir caminhos relativos ao projeto, independentemente da pasta
# a partir da qual o comando para iniciar o servidor foi executado.
BASE_DIR = Path(__file__).parent
# Ficheiro SQLite principal. DB_PATH no ambiente permite usar outra base,
# por exemplo numa instalacao de testes sem tocar na base real.
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "stock.db"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
NORMALIZED_IMAGE_SIZE = (800, 800)
# Ficheiro sincronizado com a base de dados. EXCEL_PATH no ambiente permite
# escolher outro livro sem alterar o codigo.
EXCEL_PATH = Path(os.getenv("EXCEL_PATH", BASE_DIR / "Stock_sala.xlsx"))
# Configuracao principal do Google Sheets; o Excel continua disponivel como fallback.
GOOGLE_SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    "1dWmr7VUUz6z15ZCDjgjLnDV5nMwh8FQYtp1BOOjx6Go",
).strip()
GOOGLE_CREDENTIALS = str(os.getenv(
    "GOOGLE_CREDENTIALS",
    BASE_DIR / "stocklart-c5ed300114c4.json",
)).strip()
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Folha1").strip() or "Folha1"
GOOGLE_SPREADSHEET = None
GOOGLE_ITEMS_CACHE = None
GOOGLE_ITEMS_CACHE_TIME = 0
GOOGLE_ITEMS_CACHE_TTL = 10
IMAGE_FORMULA_RE = re.compile(r'^=IMAGE\("([^\"]+)"(?:[;,]4[;,]\d+[;,]\d+)?\)$', re.IGNORECASE)
# Nome usado pelo formato antigo de folha unica. As folhas atuais usam o nome
# da categoria, mas esta variavel permite continuar a ler o formato antigo.
EXCEL_SHEET = os.getenv("EXCEL_SHEET", "Stock")
# Nome tecnico da tabela Excel usada apenas pela funcao de compatibilidade.
EXCEL_TABLE = "StockTable"
# Depois de uma alteracao externa, o worker pode demorar no maximo este tempo
# a deteta-la; as leituras HTTP tambem fazem uma verificacao imediata.
EXCEL_SYNC_INTERVAL = 5 #tempo de sinc do sv
# RLock protege operacoes que podem ocorrer ao mesmo tempo: pedidos Flask,
# worker automatico e escrita do Excel. RLock permite reentrar na mesma thread.
EXCEL_LOCK = threading.RLock()
# Cabecalhos necessarios para reconhecer e ler o formato antigo do Excel.
HEADERS = ["id", "categoria", "propriedades", "quantidade"]
# O Excel limita o nome de uma folha a 31 caracteres e nao aceita estes simbolos.
CATEGORY_SHEET_MAX_LENGTH = 31
CATEGORY_SHEET_INVALID_CHARS = set('[]:*?/\\')
# Larguras para tornar o livro legivel; propriedades sem largura especifica
# recebem o valor 22 mais abaixo.
EXCEL_COLUMN_WIDTHS = {
    "id": 10,
    "categoria": 20,
    "quantidade": 14,
}
# Dados iniciais usados apenas na primeira criacao da base de dados.
# Cada chave e uma categoria e cada lista define os campos que o frontend deve
# pedir para um componente dessa categoria.
CATEGORIAS_INICIAIS = {
    "Resistências": ["valor (Ω)", "tolerância (%)", "potência (W)", "encapsulamento"],
    "Condensadores": ["capacidade (µF)", "tensão (V)", "tipo", "encapsulamento"],
    "LEDs": ["cor", "tamanho (mm)", "tensão direta (V)"],
    "Díodos": ["referência", "tipo", "tensão inversa (V)", "corrente (A)"],
    "Transístores": ["referência", "tipo (NPN/PNP)", "ganho hFE", "corrente máx (A)"],
    "Potenciómetros": ["valor (Ω)", "tipo", "eixo"],
    "Indutores": ["valor (µH)", "corrente (A)"],
    "Cristais": ["frequência (MHz)"],
}


def norm(value):
    # Converte qualquer valor para texto, remove espacos e passa para minusculas.
    # Assim, "  10 Ohm " e "10ohm" podem ser comparados como a mesma chave.
    return "".join(str(value).lower().split())


def erro(msg, codigo=400):
    # Centraliza o formato das respostas de erro: mensagem legivel no campo
    # error e codigo HTTP que informa ao frontend que o pedido falhou.
    return jsonify(error=msg), codigo


@contextmanager
def db_connection():
    # Abre uma ligacao SQLite e transforma a funcao num gestor de contexto.
    # Ao sair do bloco with, confirma alteracoes ou desfaz tudo se houver erro.
    connection = sqlite3.connect(DB_PATH)
    # Sem isto, as linhas seriam tuplos e teriamos de usar indices numericos.
    # Com isto, row["name"] e mais claro e menos sujeito a erros.
    connection.row_factory = sqlite3.Row
    # Ativa as chaves estrangeiras: apagar uma categoria tambem pode apagar
    # os seus componentes relacionados, conforme definido no esquema SQL.
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    # Prepara a base de dados antes de qualquer leitura ou escrita.
    # Pode ser chamada muitas vezes porque CREATE TABLE IF NOT EXISTS nao
    # recria tabelas que ja existem.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connection() as connection:
        # categories define os tipos de componentes e as suas propriedades.
        # items guarda cada referencia concreta, ligada a uma categoria por cat_id.
        # meta guarda estados internos, como "os valores padrao ja foram inseridos".
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                props TEXT NOT NULL,
                image_enabled INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                cat_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                props TEXT NOT NULL,
                key TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                image TEXT NOT NULL DEFAULT '',
                UNIQUE (cat_id, key)
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        category_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(categories)")
        }
        if "image_enabled" not in category_columns:
            connection.execute(
                "ALTER TABLE categories ADD COLUMN image_enabled INTEGER NOT NULL DEFAULT 0"
            )
        item_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(items)")
        }
        if "image" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN image TEXT NOT NULL DEFAULT ''")
        # As categorias padrao sao inseridas apenas uma vez. Isto preenche uma
        # base nova sem voltar a recriar uma categoria que o utilizador apagou.
        ja_semeado = connection.execute(
            "SELECT 1 FROM meta WHERE key = 'defaults_seeded'"
        ).fetchone()
        if ja_semeado is None:
            # casefold permite comparar nomes sem distinguir maiusculas/minusculas,
            # evitando criar, por exemplo, "LEDs" e "leds" como duas categorias.
            existentes = {
                row["name"].casefold()
                for row in connection.execute("SELECT name FROM categories")
            }
            em_falta = [
                (name, json.dumps(props, ensure_ascii=False))
                for name, props in CATEGORIAS_INICIAIS.items()
                if name.casefold() not in existentes
            ]
            if em_falta:
                # Guarda as propriedades como JSON porque a coluna props e TEXT.
                connection.executemany(
                    "INSERT INTO categories (name, props) VALUES (?, ?)",
                    em_falta,
                )
            connection.execute(
                # Na proxima chamada, este registo impede novo preenchimento automatico.
                "INSERT INTO meta (key, value) VALUES ('defaults_seeded', '1')"
            )


def db_items():
    # Consulta os componentes e substitui o cat_id interno pelo nome legivel
    # da categoria, que e o formato esperado pelo frontend e pelo Excel.
    init_db()
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT items.id, categories.name AS category, items.props, items.qty, items.image
            FROM items
            JOIN categories ON categories.id = items.cat_id
            ORDER BY items.id
            """
        ).fetchall()
    return [
        # Cada linha e convertida num dicionario; props volta de texto JSON
        # para dicionario Python antes de ser enviado para a aplicacao.
        {
            "id": row["id"],
            "cat": row["category"],
            "props": json.loads(row["props"]),
            "qty": row["qty"],
            "image": image_path(row["image"]),
        }
        for row in rows
    ]


def db_categories():
    # Devolve a configuracao das categorias para o frontend construir os formularios.
    # A lista props diz quais os campos que o utilizador deve preencher.
    init_db()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT name, props, image_enabled FROM categories ORDER BY id"
        ).fetchall()
    return [
        {
            "name": row["name"],
            "props": json.loads(row["props"]),
            "image": bool(row["image_enabled"]),
        }
        for row in rows
    ]


def google_sheet():
    # Abre o documento uma vez e reutiliza a sessao autenticada.
    global GOOGLE_SPREADSHEET
    if not GOOGLE_SHEET_ID or not GOOGLE_CREDENTIALS:
        return None
    if GOOGLE_SPREADSHEET is None:
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        GOOGLE_SPREADSHEET = gspread.authorize(credentials).open_by_key(GOOGLE_SHEET_ID)
    return GOOGLE_SPREADSHEET


def google_items():
    # Le as abas com colunas id, categoria e quantidade.
    global GOOGLE_ITEMS_CACHE, GOOGLE_ITEMS_CACHE_TIME
    now = time.monotonic()
    if GOOGLE_ITEMS_CACHE is not None and now - GOOGLE_ITEMS_CACHE_TIME < GOOGLE_ITEMS_CACHE_TTL:
        return json.loads(json.dumps(GOOGLE_ITEMS_CACHE, ensure_ascii=False))
    spreadsheet = google_sheet()
    if spreadsheet is None:
        return None
    items = []
    found_sheet = False
    for worksheet in spreadsheet.worksheets():
        values = worksheet.get_all_values(value_render_option="FORMULA")
        if not values or not any(any(row) for row in values):
            continue
        headers = [str(value).strip() for value in values[0]]
        positions = {header.casefold(): index for index, header in enumerate(headers)}
        if not {"id", "categoria", "quantidade"}.issubset(positions):
            continue
        found_sheet = True
        for row in values[1:]:
            if not any(row):
                continue
            row += [""] * (len(headers) - len(row))
            image_index = positions.get("imagem")
            image_value = row[image_index] if image_index is not None else ""
            image_match = IMAGE_FORMULA_RE.match(str(image_value).strip())
            image = image_match.group(1) if image_match else str(image_value).strip()
            if headers[:len(HEADERS)] == HEADERS:
                props = json.loads(row[2] or "{}")
            else:
                props = {
                    headers[index]: str(value)
                    for index, value in enumerate(row)
                    if headers[index].casefold() not in {"id", "categoria", "imagem", "quantidade"}
                    and value != ""
                }
            items.append({
                "id": int(row[positions["id"]]),
                "cat": str(row[positions["categoria"]]).strip() or worksheet.title,
                "props": props,
                "qty": int(row[positions["quantidade"]] or 0),
                "image": image,
            })
    if not found_sheet:
        return None
    GOOGLE_ITEMS_CACHE = items
    GOOGLE_ITEMS_CACHE_TIME = now
    return json.loads(json.dumps(items, ensure_ascii=False))


def sync_google_to_db():
    # Copia alteracoes manuais do Google Sheets para a base usada pela API.
    sheet_items = google_items()
    if sheet_items is None or sheet_items == db_items():
        return False
    init_db()
    with db_connection() as connection:
        categories = {
            row["name"].casefold(): row["id"]
            for row in connection.execute("SELECT id, name FROM categories")
        }
        for item in sheet_items:
            key = item["cat"].casefold()
            if key not in categories:
                cursor = connection.execute(
                    "INSERT INTO categories (name, props) VALUES (?, ?)",
                    (item["cat"], json.dumps(list(item["props"]), ensure_ascii=False)),
                )
                categories[key] = cursor.lastrowid
        connection.execute("DELETE FROM items")
        connection.executemany(
            "INSERT INTO items (id, cat_id, props, key, qty, image) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    item["id"], categories[item["cat"].casefold()],
                    json.dumps(item["props"], ensure_ascii=False),
                    "|".join(norm(value) for value in item["props"].values()),
                    item["qty"], item.get("image", ""),
                )
                for item in sheet_items
            ],
        )
    return True


def save_google_items(items):
    # Recria o formato visual: uma aba por categoria e uma coluna por propriedade.
    spreadsheet = google_sheet()
    if spreadsheet is None:
        return
    if any(item.get("image") for item in items) and not PUBLIC_BASE_URL:
        raise RuntimeError(
            "Define PUBLIC_BASE_URL antes de guardar imagens no Google Sheets"
        )
    managed = []
    for worksheet in spreadsheet.worksheets():
        values = worksheet.get_all_values()
        headers = [str(value).casefold() for value in values[0]] if values else []
        if not values or not any(any(row) for row in values) or {"id", "categoria", "quantidade"}.issubset(headers):
            managed.append(worksheet)
    if not managed:
        managed = [spreadsheet.add_worksheet(title="Folha1", rows=1000, cols=10)]
    grouped = {}
    for item in items:
        grouped.setdefault(item["cat"], []).append(item)
    while len(managed) < len(grouped):
        managed.append(spreadsheet.add_worksheet(title=f"Categoria {len(managed) + 1}", rows=1000, cols=10))
    used_names = {sheet.title.casefold() for sheet in spreadsheet.worksheets() if sheet not in managed}
    image_categories = {
        category["name"]: category["image"] for category in db_categories()
    }
    for index, (category, category_items) in enumerate(grouped.items()):
        worksheet = managed[index]
        worksheet.update_title(category_sheet_name(category, used_names))
        property_names = list(dict.fromkeys(
            name for item in category_items for name in item["props"]
        ))
        has_images = image_categories.get(category, False)
        headers = ["id", "categoria", *property_names]
        if has_images:
            headers.append("imagem")
        headers.append("quantidade")
        rows = [headers] + [
            [item["id"], item["cat"]]
            + [item["props"].get(name, "") for name in property_names]
            + ([f'=IMAGE("{sheet_image_url(item["image"])}";4;80;80)'] if has_images and item.get("image") else ([""] if has_images else []))
            + [item["qty"]]
            for item in category_items
        ]
        worksheet.clear()
        worksheet.resize(rows=max(1000, len(rows)), cols=max(10, len(headers)))
        worksheet.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
        worksheet.format(
            f"A1:{get_column_letter(len(headers))}{len(rows)}",
            {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"},
        )
        if has_images:
            image_column = headers.index("imagem")
            spreadsheet.batch_update({
                "requests": [
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": worksheet.id,
                                "dimension": "ROWS",
                                "startIndex": 1,
                                "endIndex": len(rows),
                            },
                            "properties": {"pixelSize": 90},
                            "fields": "pixelSize",
                        }
                    },
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": worksheet.id,
                                "dimension": "COLUMNS",
                                "startIndex": image_column,
                                "endIndex": image_column + 1,
                            },
                            "properties": {"pixelSize": 100},
                            "fields": "pixelSize",
                        }
                    },
                ]
            })
    for worksheet in managed[len(grouped):]:
        if len(spreadsheet.worksheets()) > 1:
            spreadsheet.del_worksheet(worksheet)
        else:
            worksheet.clear()
    GOOGLE_ITEMS_CACHE = None


def sheet_image_url(image_url):
    """Troca o host local pelo endereco publico configurado para o Sheets."""
    if not image_url:
        return image_url
    path = image_path(image_url)
    if not PUBLIC_BASE_URL:
        return image_url
    return f"{PUBLIC_BASE_URL}{path}"


def image_path(image_url):
    """Mantem imagens como caminhos locais para funcionarem em qualquer tunnel."""
    if not image_url:
        return ""
    filename = Path(urlparse(str(image_url)).path).name
    return f"/uploads/{filename}" if filename else ""


def excel_table(workbook, create=True):
    # Funcao de compatibilidade com a primeira versao do programa.
    # Recebe um Workbook e procura a folha Stock; se create=True, cria a folha
    # e uma tabela A1:D1 com os cabecalhos antigos.
    if EXCEL_SHEET in workbook.sheetnames:
        sheet = workbook[EXCEL_SHEET]
    elif create:
        sheet = workbook.create_sheet(EXCEL_SHEET)
    else:
        raise RuntimeError(f"A folha {EXCEL_SHEET!r} não existe")

    if EXCEL_TABLE in sheet.tables:
        return sheet, sheet.tables[EXCEL_TABLE]
    if not create:
        raise RuntimeError(f"A tabela {EXCEL_TABLE!r} não existe")

    for column, header in enumerate(HEADERS, start=1):
        sheet.cell(row=1, column=column, value=header)
    tabela = Table(displayName=EXCEL_TABLE, ref="A1:D1")
    tabela.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
        showRowStripes=True, showColumnStripes=False,
    )
    sheet.add_table(tabela)
    return sheet, tabela


def read_excel_items():
    # Converte todas as linhas validas do Excel para a estrutura interna:
    # {"id": ..., "cat": ..., "props": {...}, "qty": ...}.
    if not EXCEL_PATH.exists():
        # Sem ficheiro, a base de dados atual nao deve ser apagada.
        return None
    # data_only=True le o resultado das formulas em vez da formula em si.
    workbook = load_workbook(EXCEL_PATH, data_only=True)
    # Um livro antigo tem a folha Stock. O formato novo tem uma folha por
    # categoria, por isso nesse caso todas as folhas precisam de ser percorridas.
    sheets = [workbook[EXCEL_SHEET]] if EXCEL_SHEET in workbook.sheetnames else [
        workbook[sheet_name] for sheet_name in workbook.sheetnames
    ]
    if not sheets:
        return None

    # Acumula componentes de todas as folhas para depois substituir os dados DB.
    items = []
    # Serve para atribuir identificadores a linhas adicionadas manualmente no Excel.
    next_id = 0
    for sheet in sheets:
        # max_row/max_col definem o retangulo lido: cabecalhos na linha 1 e
        # componentes a partir da linha 2.
        min_row, min_col = 1, 1
        max_row, max_col = max(sheet.max_row, 1), max(sheet.max_column, len(HEADERS))
        headers = [sheet.cell(min_row, col).value for col in range(min_col, max_col + 1)]
        positions = {str(header).casefold(): index for index, header in enumerate(headers)}
        # Se todas as colunas antigas existirem, propriedades vem num JSON unico.
        legacy_sheet = all(header.casefold() in positions for header in HEADERS)
        # No formato novo, basta existirem id e quantidade; as outras colunas
        # (exceto categoria) sao tratadas como propriedades dinamicas.
        dynamic_sheet = all(header in positions for header in ("id", "quantidade"))
        if not legacy_sheet and not dynamic_sheet:
            if EXCEL_SHEET in workbook.sheetnames:
                missing = [header for header in HEADERS if header.casefold() not in positions]
                raise RuntimeError(f"Faltam colunas no Excel: {', '.join(missing)}")
            continue

        for row in sheet.iter_rows(min_row=min_row + 1, max_row=max_row, min_col=min_col, max_col=max_col, values_only=True):
            # Linhas vazias podem existir no fim da folha e nao representam itens.
            if not any(value is not None for value in row):
                continue

            def value(name):
                # positions transforma o nome do cabecalho no indice correto da linha.
                return row[positions[name.casefold()]]

            if legacy_sheet:
                # JSON pode ja ser um dicionario ou ainda ser texto, dependendo do Excel.
                raw_props = value("propriedades") or "{}"
                props = json.loads(raw_props) if isinstance(raw_props, str) else raw_props
            else:
                # O nome do cabecalho torna-se a chave e a celula torna-se o valor
                # da propriedade, por exemplo coluna "valor" -> props["valor"].
                excluded = {"id", "categoria", "quantidade"}
                props = {
                    headers[index]: str(cell_value)
                    for index, cell_value in enumerate(row)
                    if index < len(headers)
                    and str(headers[index]).casefold() not in excluded
                    and cell_value is not None
                }
            category_value = row[positions["categoria"]] if "categoria" in positions else sheet.title
            # Um id existente e preservado; uma linha sem id recebe o proximo valor
            # maior ja encontrado para evitar colisao com os itens anteriores.
            raw_id = value("id")
            if raw_id is None or str(raw_id).strip() == "":
                next_id += 1
                item_id = next_id
            else:
                item_id = int(raw_id)
                next_id = max(next_id, item_id)
            items.append({
                "id": item_id,
                "cat": str(category_value or sheet.title).strip(),
                "props": {str(key): str(val) for key, val in props.items()},
                "qty": int(value("quantidade") or 0),
            })
    return items


def category_sheet_name(category, used_names):
    # Recebe o nome da categoria e devolve o nome que sera usado no Excel.
    # Substitui simbolos proibidos, corta nomes longos e garante unicidade.
    name = "".join("_" if char in CATEGORY_SHEET_INVALID_CHARS else char for char in category)
    name = name.strip()[:CATEGORY_SHEET_MAX_LENGTH] or "Categoria"
    candidate = name
    suffix = 2
    while candidate.casefold() in used_names:
        # Duas categorias com nomes iguais depois da limpeza recebem sufixos
        # para que o openpyxl nao tente criar duas folhas com o mesmo nome.
        suffix_text = f" ({suffix})"
        candidate = f"{name[:CATEGORY_SHEET_MAX_LENGTH - len(suffix_text)]}{suffix_text}"
        suffix += 1
    used_names.add(candidate.casefold())
    return candidate


def sync_excel_to_db():
    # Usa o Excel como fonte quando o utilizador edita o ficheiro manualmente.
    # A comparacao evita apagar e recriar a base quando nada foi alterado.
    with EXCEL_LOCK:
        excel_items = read_excel_items()
        if excel_items is None or excel_items == db_items():
            # Se nao existe Excel, mantemos a base. Se os dados sao iguais,
            # nao fazemos uma escrita desnecessaria.
            return False

        init_db()
        with db_connection() as connection:
            categories = {
                row["name"].casefold(): row["id"]
                for row in connection.execute("SELECT id, name FROM categories")
            }
            excel_categories = {item["cat"].casefold() for item in excel_items}
            for item in excel_items:
                # Uma categoria nova escrita no Excel passa a existir tambem no DB.
                category_key = item["cat"].casefold()
                if category_key not in categories:
                    cursor = connection.execute(
                        "INSERT INTO categories (name, props) VALUES (?, ?)",
                        (item["cat"], json.dumps(list(item["props"]), ensure_ascii=False)),
                    )
                    categories[category_key] = cursor.lastrowid
            connection.execute("DELETE FROM items")
            # A lista Excel e considerada completa: primeiro removemos a versao
            # anterior e depois inserimos todos os itens novamente.
            connection.executemany(
                "INSERT INTO items (id, cat_id, props, key, qty, image) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        item["id"],
                        categories[item["cat"].casefold()],
                        json.dumps(item["props"], ensure_ascii=False),
                        "|".join(norm(value) for value in item["props"].values()),
                        item["qty"], item.get("image", ""),
                    )
                    for item in excel_items
                ],
            )
            excel_category_ids = [categories[key] for key in excel_categories]
            if excel_category_ids:
                # Mantem apenas categorias representadas por pelo menos um item
                # no Excel; categorias vazias deixam de existir neste sincronismo.
                placeholders = ",".join("?" for _ in excel_category_ids)
                connection.execute(
                    f"DELETE FROM categories WHERE id NOT IN ({placeholders})",
                    excel_category_ids,
                )
            else:
                connection.execute("DELETE FROM categories")
    return True


def excel_sync_worker():
    # Executa continuamente fora do pedido HTTP. Assim, o servidor pode detetar
    # uma edicao feita no Excel mesmo quando nao ha pedidos naquele momento.
    last_signature = None
    while True:
        try:
            signature = None
            if EXCEL_PATH.exists():
                # Se data ou tamanho mudarem, o Excel sera lido novamente.
                stat = EXCEL_PATH.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
            if signature != last_signature:
                if sync_excel_to_db():
                    last_signature = signature
                else:
                    last_signature = signature
        except Exception:
            # Um erro de leitura fica isolado nesta tentativa; a proxima verificacao
            # tenta novamente sem desligar a aplicacao Flask.
            pass
        time.sleep(EXCEL_SYNC_INTERVAL)


def start_excel_sync():
    # daemon=True faz a thread terminar automaticamente quando o servidor termina.
    # A funcao nao espera pelo worker: inicia-o e devolve o controlo ao Flask.
    if GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS:
        return
    threading.Thread(target=excel_sync_worker, name="excel-sync", daemon=True).start()


def read_items():
    # E o ponto unico usado pelas rotas para ler componentes. Sincronizar aqui
    # garante que uma alteracao manual fica visivel mesmo antes dos 5 segundos.
    if GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS:
        sync_google_to_db()
    else:
        sync_excel_to_db()
    return None, None, None, db_items()


def save_items(items):
    # Recebe a lista completa atual e grava a mesma informacao em dois locais:
    # SQLite para a aplicacao e Excel para consulta/edicao manual.
    with EXCEL_LOCK:
        init_db()
        with db_connection() as connection:
            categories = {
                row["name"]: row["id"]
                for row in connection.execute("SELECT id, name FROM categories")
            }
            for item in items:
                # Antes de inserir items, cria a categoria caso ela ainda nao exista.
                if item["cat"] not in categories:
                    cursor = connection.execute(
                        "INSERT INTO categories (name, props) VALUES (?, ?)",
                        (item["cat"], json.dumps(list(item["props"]), ensure_ascii=False)),
                    )
                    categories[item["cat"]] = cursor.lastrowid
            connection.execute("DELETE FROM items")
            # Reescreve os itens para que apagamentos e alteracoes tambem sejam
            # refletidos na base, em vez de apenas adicionar novos registos.
            connection.executemany(
                "INSERT INTO items (id, cat_id, props, key, qty, image) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        item["id"],
                        categories[item["cat"]],
                        json.dumps(item["props"], ensure_ascii=False),
                        "|".join(norm(value) for value in item["props"].values()),
                        item["qty"], item.get("image", ""),
                    )
                    for item in items
                ],
            )

        if GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS:
            save_google_items(items)
            return

        # Mantem folhas nao geridas pelo programa e abre/cria o livro de trabalho.
        workbook = load_workbook(EXCEL_PATH) if EXCEL_PATH.exists() else Workbook()
        if EXCEL_SHEET in workbook.sheetnames:
            del workbook[EXCEL_SHEET]
        for sheet in list(workbook.worksheets):
            # Uma folha e considerada gerida se tiver as colunas base do formato
            # atual. Remove-a para evitar nomes repetidos como "Res (2)".
            headers = {
                str(sheet.cell(row=1, column=column).value).casefold()
                for column in range(1, sheet.max_column + 1)
            }
            if {"id", "categoria", "quantidade"}.issubset(headers):
                del workbook[sheet.title]

        used_names = {sheet.title.casefold() for sheet in workbook.worksheets}
        # Dicionario: nome da categoria -> lista dos seus componentes.
        # Este agrupamento e o que garante uma folha por categoria, nao por item.
        items_by_category = {}
        for item in items:
            items_by_category.setdefault(item["cat"], []).append(item)
        for category, category_items in items_by_category.items():
            # A folha e criada uma vez; cada componente sera uma linha dentro dela.
            sheet = workbook.create_sheet(category_sheet_name(category, used_names))
            # Junta as propriedades dos itens da categoria pela ordem em que aparecem.
            # dict.fromkeys elimina repeticoes sem perder essa ordem.
            property_names = list(dict.fromkeys(
                property_name
                for item in category_items
                for property_name in item["props"]
            ))
            headers = ["id", "categoria", *property_names, "quantidade"]
            for column, header in enumerate(headers, start=1):
                # Coloca os nomes das colunas na primeira linha e define a largura
                # para que valores e nomes de propriedades sejam visiveis.
                sheet.cell(row=1, column=column, value=header)
                sheet.column_dimensions[sheet.cell(row=1, column=column).column_letter].width = EXCEL_COLUMN_WIDTHS.get(header, 22)
            for item in category_items:
                # O id e categoria ficam no inicio, as propriedades no meio e a
                # quantidade no fim; valores ausentes ficam como celula vazia.
                sheet.append([item["id"], item["cat"]] + [
                    item["props"].get(property_name, "") for property_name in property_names
                ] + [item["qty"]])
        if len(workbook.worksheets) > 1:
            for sheet in list(workbook.worksheets):
                # Workbook() cria por vezes uma folha vazia chamada Sheet; remove-a
                # quando ja existem folhas de categorias.
                if not any(cell.value is not None for row in sheet.iter_rows() for cell in row):
                    del workbook[sheet.title]
        EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Se o processo falhar durante save, o Excel original permanece intacto.
        temporary_path = EXCEL_PATH.with_name(f".{EXCEL_PATH.stem}.tmp.xlsx")
        workbook.save(temporary_path)
        os.replace(temporary_path, EXCEL_PATH)


def data_from_items(items):
    # Junta configuracao das categorias e lista de itens numa unica resposta JSON.
    return {
        "categories": db_categories(),
        "items": items,
    }


@app.post("/api/images")
def upload_image():
    image = request.files.get("image")
    if image is None or not image.filename:
        return erro("Seleciona uma imagem")
    extension = Path(image.filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return erro("Formato de imagem não suportado")
    try:
        source = Image.open(image.stream)
        source.load()
        source = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError):
        return erro("O ficheiro enviado não é uma imagem válida")

    contained = ImageOps.contain(source, NORMALIZED_IMAGE_SIZE, Image.Resampling.LANCZOS)
    normalized = Image.new("RGB", NORMALIZED_IMAGE_SIZE, "white")
    offset = (
        (NORMALIZED_IMAGE_SIZE[0] - contained.width) // 2,
        (NORMALIZED_IMAGE_SIZE[1] - contained.height) // 2,
    )
    normalized.paste(contained, offset)
    filename = f"{uuid4().hex}.jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    output = BytesIO()
    normalized.save(output, format="JPEG", quality=88, optimize=True)
    (UPLOAD_DIR / secure_filename(filename)).write_bytes(output.getvalue())
    return jsonify(url=f"/uploads/{filename}")


@app.get("/uploads/<path:filename>")
def uploaded_image(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/")
def home():
    # Rota da pagina principal; o HTML trata da apresentacao e chama as APIs abaixo.
    return render_template("index.html")


@app.get("/api/data")
def dados():
    # GET /api/data e a leitura inicial e atualizada usada pela interface web.
    try:
        _, _, _, items = read_items()
        return jsonify(data_from_items(items))
    except Exception as exc:
        return erro(str(exc), 500)


@app.post("/api/move")
def mover():
    # POST /api/move processa entrada ou saida de stock enviada pelo frontend.
    data = request.get_json(silent=True) or {}
    # A quantidade vem do JSON como texto ou numero; converte para int e exige
    # pelo menos uma unidade antes de alterar qualquer dado.
    try:
        qty = int(data.get("qty", 0))
    except (TypeError, ValueError):
        qty = 0
    if qty < 1:
        return erro("A quantidade tem de ser 1 ou mais")

    try:
        _, _, _, items = read_items()
        # Extrai do pedido a categoria e os valores preenchidos nas propriedades.
        category = str(data.get("cat", "")).strip()
        props = {str(key): str(value).strip() for key, value in (data.get("props") or {}).items()}
        image = str(data.get("image", "")).strip()
        category_config = next((item for item in db_categories() if item["name"] == category), None)
        if not category or not props or not all(props.values()):
            return erro("Preenche a categoria e todas as propriedades")
        if not category_config:
            return erro("Categoria não encontrada", 404)
        if image and not category_config["image"]:
            return erro("Esta categoria não aceita imagens")
        key = "|".join(norm(props[name]) for name in props)
        # Dois itens sao considerados iguais quando pertencem a mesma categoria
        # e todos os valores das propriedades, depois de normalizados, coincidem.
        item = next((current for current in items if current["cat"] == category and "|".join(norm(current["props"].get(name, "")) for name in props) == key), None)

        if data.get("mode") == "out":
            # Na saida, nunca se cria um item novo e nunca se permite stock negativo.
            if not item:
                return erro("Esse item não existe no stock", 404)
            if item["qty"] < qty:
                return erro(f"Só há {item['qty']} em stock")
            item["qty"] -= qty
            message = f"Retirado. Restam {item['qty']}"
        elif item:
            # Na entrada, um item existente recebe apenas o aumento de quantidade.
            item["qty"] += qty
            if image:
                item["image"] = image
            message = f"Quantidade somada: agora {item['qty']}"
        else:
            # Se nao houve correspondencia, cria uma referencia com id novo.
            new_id = max((item["id"] for item in items), default=0) + 1
            items.append({"id": new_id, "cat": category, "props": props, "qty": qty, "image": image})
            message = "Item novo adicionado"
        save_items(items)
        return jsonify(msg=message)
    except Exception as exc:
        return erro(str(exc), 500)


@app.post("/api/items/<int:item_id>/step")
def ajustar(item_id):
    # POST /api/items/<id>/step altera a quantidade de um item ja identificado.
    try:
        delta = int((request.get_json(silent=True) or {}).get("delta", 0))
        _, _, _, items = read_items()
        item = next((current for current in items if current["id"] == item_id), None)
        if not item:
            return erro("Item não encontrado", 404)
        item["qty"] = max(0, item["qty"] + delta)
        # max protege a regra de negocio: a quantidade minima possivel e zero.
        save_items(items)
        return jsonify(ok=True)
    except (TypeError, ValueError):
        return erro("Valor inválido")
    except Exception as exc:
        return erro(str(exc), 500)


@app.delete("/api/items/<int:item_id>")
def apagar(item_id):
    # DELETE /api/items/<id> remove uma referencia inteira, nao apenas unidades.
    try:
        _, _, _, items = read_items()
        restantes = [item for item in items if item["id"] != item_id]
        if len(restantes) == len(items):
            return erro("Item não encontrado", 404)
        save_items(restantes)
        return jsonify(ok=True)
    except Exception as exc:
        return erro(str(exc), 500)


@app.post("/api/categories")
def nova_categoria():
    # POST /api/categories cria a configuracao de uma categoria para uso futuro.
    data = request.get_json(silent=True) or {}
    # strip remove espacos laterais; dict.fromkeys remove propriedades repetidas
    # mantendo a ordem original enviada pelo utilizador.
    name = str(data.get("name", "")).strip()
    props = list(dict.fromkeys(str(prop).strip() for prop in data.get("props", []) if str(prop).strip()))
    image_enabled = bool(data.get("image"))
    if not name or not props:
        return erro("Indica o nome e pelo menos uma propriedade")
    try:
        init_db()
        if any(category["name"].casefold() == name.casefold() for category in db_categories()):
            return erro("Essa categoria já existe")
        with db_connection() as connection:
            connection.execute(
                "INSERT INTO categories (name, props, image_enabled) VALUES (?, ?, ?)",
                (name, json.dumps(props, ensure_ascii=False), int(image_enabled)),
            )
        return jsonify(msg="Categoria pronta para receber o primeiro item")
    except Exception as exc:
        return erro(str(exc), 500)


@app.delete("/api/categories/<name>")
def apagar_categoria(name):
    # DELETE /api/categories/<name> remove a categoria e, pela chave estrangeira,
    # os componentes ligados a ela; depois atualiza tambem o Excel.
    try:
        init_db()
        with db_connection() as connection:
            row = connection.execute(
                "SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if not row:
                return erro("Categoria não encontrada", 404)
            n_itens = connection.execute(
                "SELECT COUNT(*) AS n FROM items WHERE cat_id = ?", (row["id"],)
            ).fetchone()["n"]
            connection.execute("DELETE FROM categories WHERE id = ?", (row["id"],))
        # read_items obtem os restantes itens e save_items reconstrui as folhas,
        # deixando de criar a folha da categoria apagada.
        # sincroniza a base de dados (já sem a categoria/itens) com o Excel
        _, _, _, items = read_items()
        save_items(items)
        msg = "Categoria apagada"
        if n_itens:
            msg += f" com {n_itens} referência(s)"
        return jsonify(msg=msg)
    except Exception as exc:
        return erro(str(exc), 500)


if __name__ == "__main__":
    # Este bloco nao corre quando o modulo e apenas importado por testes ou WSGI.
    if os.environ.get("WERKZEUG_RUN_MAIN") in (None, "true"):
        # O reloader do Flask inicia o processo mais de uma vez; esta condicao
        # evita criar dois workers a sincronizar o mesmo Excel.
        start_excel_sync()
    # debug=True ativa recarregamento e mensagens detalhadas durante desenvolvimento;
    # host 0.0.0.0 aceita ligacoes locais na porta 5000.
    app.run(host="0.0.0.0", port=5000, debug=True)
