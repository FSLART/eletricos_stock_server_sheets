# Servidor Stocklart

Servidor Flask para gerir o stock e sincronizar os componentes com o Google Sheets.

## Requisitos

- Python 3 instalado e adicionado ao PATH
- `ngrok` instalado e autenticado
- `cloudflared` instalado
- Ficheiro `stocklart-c5ed300114c4.json` junto ao `app.py`
- Ficheiro `policy.yaml` junto ao `app.py`

## Instalacao no Windows

### 1. Python

Instala o Python a partir de:

```text
https://www.python.org/downloads/
```

Durante a instalacao, ativa a opcao `Add Python to PATH`. Confirma:

```powershell
python --version
```

### 2. Bibliotecas Python

Na pasta `meu_servidor`, executa:

```powershell
python -m pip install Flask openpyxl gspread google-auth Pillow
```

### 3. ngrok

Instala pelo PowerShell:

```powershell
winget install Ngrok.Ngrok
```

Cria uma conta gratuita em:

```text
https://dashboard.ngrok.com/signup
```

No painel do ngrok, copia o teu authtoken e configura-o uma vez:

```powershell
ngrok config add-authtoken COLOCA_AQUI_O_TEU_TOKEN
```

Confirma a instalacao:

```powershell
ngrok version
```

### 4. Cloudflare Tunnel

Instala pelo PowerShell:

```powershell
winget install Cloudflare.cloudflared
```

Confirma a instalacao:

```powershell
cloudflared --version
```

Para este modo de teste nao precisas de criar conta Cloudflare nem de configurar token.

### 5. Credenciais do Google Sheets

Mantem o ficheiro de credenciais:

```text
stocklart-c5ed300114c4.json
```

na mesma pasta do `app.py`. A conta de servico indicada nesse ficheiro tem de ter acesso de editor à folha Google Sheets usada pelo projeto.

## Arranque diario

Depois da instalacao inicial, nao precisas de abrir varios terminais nem repetir
os comandos do Flask, ngrok ou Cloudflare. Basta executar o script:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\iniciar_servidor.ps1
```

O script inicia automaticamente o servidor Flask, o ngrok e o Cloudflare,
deteta o novo endereco Cloudflare e configura `PUBLIC_BASE_URL` para as imagens
do Google Sheets. Mantem a janela aberta enquanto o servidor estiver a ser usado.

## O que o script inicia

Neste modo, o site e a API ficam acessiveis pelo ngrok, enquanto as imagens usadas no Google Sheets passam pelo Cloudflare.

O endereço do site é:

```text
https://outtakes-parsley-drastic.ngrok-free.dev
```

## Como funciona

- O site e os pedidos da aplicacao usam o ngrok.
- O Flask continua a correr localmente em `localhost:5000`.
- O Cloudflare e usado para que o Google Sheets consiga aceder as imagens.
- No Google Sheets, a coluna `imagem` usa uma formula `IMAGE` com tamanho fixo de `80x80`.
- Os ficheiros ficam guardados na pasta `uploads` deste servidor.

O script mantem os processos ativos. Se o Cloudflare for reiniciado e gerar outro endereco, o script atualiza `PUBLIC_BASE_URL` automaticamente.

## Sem Cloudflare

Sem `PUBLIC_BASE_URL`, o site pode funcionar pelo ngrok, mas o Google Sheets pode mostrar erro nas imagens porque o ngrok gratuito apresenta uma pagina de aviso ao Google.

Ao pressionar `Ctrl+C`, o script termina o Flask e os dois tuneis.
