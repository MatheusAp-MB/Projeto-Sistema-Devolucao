# scripts_exploracao_ML/validar_lote_devolucoes_conhecidas.py
#
# Objetivo: validar em lote a ideia buyer_id -> lista de pedidos do cliente ->
# classificacao por tipo (sem problema / com reclamacao / com devolucao),
# contra uma lista de pedidos que voce ja sabe terem devolucao real (relatorios
# em maos). Ver vault, "Ideia — Etiqueta...", secao "Confirmado -- Codigo do
# Lado do Nome e o buyer.id".
#
# Pra cada linha de CLIENTES_PARA_TESTAR:
#   1. GET /orders/$PEDIDO -- descobre o buyer_id e o nome que a API devolve
#      (compara com o nome do seu relatorio -- ja vimos 1 caso, o do Tancredo,
#      onde o nome da API nao bate exatamente)
#   2. Agrupa por (empresa, buyer_id) UNICO -- evita repetir a mesma busca se
#      2 linhas da sua lista forem do mesmo cliente
#   3. Pra cada cliente unico: lista TODOS os pedidos dele e classifica cada
#      um (mesma logica de consultar_pedidos_por_cliente.py)
#   4. Imprime 1 tabela-resumo, 1 linha por item da sua lista original
#
# O detalhe completo (todos os pedidos de cada cliente) vai pro JSON -- só
# sobe na conversa se quiser aprofundar algum caso.
#
# Só leitura. Não toca no banco.

import json
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI

# ==== CONFIGURA AQUI ANTES DE RODAR ====
# (Nº, "Nome do Cliente", "Número do Pedido", "Empresa") -- cole os 14 aqui
CLIENTES_PARA_TESTAR = [
    (1, "Tancredo Goncalves Pereira", "2000017862978392", "MB"),
    (2, "Giovania Uchoas Pires Palomo", "2000017697078004", "SV"),
    (3, "Luis Ricardo Jamelli", "2000017863490392", "SV"),
    (4, "Cristina Felipe de Sousa", "2000017960227630", "SV"),
    (5, "Nelson Domingos dos Santos", "2000017751384000", "SV"),
    (6, "Rafael Ramos Machado", "2000017939871998", "MB"),
    (7, "Rafael Ramos Machado", "2000018113512820", "MB"),
    (8, "Rodrigo Aguiar Gomes", "2000017872643042", "MB"),
    (9, "Aline Conceicao Silva Santos", "2000017520971040", "MB"),
    (10, "Antonio Felix dos Reis", "2000018050154756", "MB"),
    (11, "Edgar Augusto Batista", "2000017788033354", "SV"),
    (12, "Joel Marcos Marcelino", "2000017861290966", "MB"),
    (13, "Claudia Aparecida Rizzatti", "2000014649100973", "MB"),
    (14, "Dionifer Neuenfeld", "2000017749492836", "MB"),
]
# ========================================

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
NOME_LOG = "validar_lote_devolucoes_conhecidas"
CAMINHO_SAIDA = Path(__file__).resolve().parent / "validacao_lote_devolucoes_conhecidas.json"

console = Console()

CORES_POR_TIPO = {
    "Sem problema": "green",
    "Com reclamação (sem devolução)": "yellow",
    "Com devolução": "red",
}

_cache_seller_id = {}  # conta -> seller_id, pra não chamar /users/me de novo pra cada linha


def obter_seller_id(conta):
    if conta not in _cache_seller_id:
        resposta = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG)
        _cache_seller_id[conta] = resposta.json()["id"]
    return _cache_seller_id[conta]


def descobrir_buyer_id(pedido, conta):
    resposta = chamar_api("GET", f"/orders/{pedido}", pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG)
    dados = resposta.json()
    comprador = dados.get("buyer") or {}
    nome_api = f"{comprador.get('first_name', '')} {comprador.get('last_name', '')}".strip()
    return comprador.get("id"), nome_api


def buscar_todos_os_pedidos(seller_id, buyer_id, conta):
    pedidos, offset, limite = [], 0, 50
    while True:
        resposta = chamar_api(
            "GET", "/orders/search", pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG,
            params={"seller": seller_id, "buyer": buyer_id, "sort": "date_desc",
                    "limit": limite, "offset": offset},
        )
        resultado = resposta.json()
        pagina = resultado.get("results", [])
        pedidos.extend(pagina)
        total = (resultado.get("paging") or {}).get("total", len(pedidos))
        offset += limite
        if offset >= total or not pagina:
            break
    return pedidos


def classificar_pedido(order_id, conta):
    try:
        resposta_claims = chamar_api(
            "GET", "/post-purchase/v1/claims/search", pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG,
            params={"order_id": order_id},
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        return "Sem problema", None

    claims = resposta_claims.json().get("data", [])
    if not claims:
        return "Sem problema", None

    claims_em_ordem_de_tentativa = sorted(claims, key=lambda c: 0 if c.get("type") in ("return", "fulfillment") else 1)
    for candidata in claims_em_ordem_de_tentativa:
        try:
            resposta_devolucao = chamar_api(
                "GET", f"/post-purchase/v2/claims/{candidata['id']}/returns",
                pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG,
            )
        except (ErroAPI, ErroAutenticacaoAPI):
            continue
        if resposta_devolucao.json():
            return "Com devolução", candidata.get("id")

    return "Com reclamação (sem devolução)", claims[0].get("id")


# ---- Passo 1: descobre o buyer_id de cada linha ----
linhas = []
for numero, nome_informado, pedido, empresa in CLIENTES_PARA_TESTAR:
    try:
        buyer_id, nome_api = descobrir_buyer_id(pedido, empresa)
        linhas.append({"numero": numero, "nome_informado": nome_informado, "pedido": pedido,
                        "empresa": empresa, "buyer_id": buyer_id, "nome_api": nome_api})
    except (ErroAPI, ErroAutenticacaoAPI) as erro:
        linhas.append({"numero": numero, "nome_informado": nome_informado, "pedido": pedido,
                        "empresa": empresa, "erro": str(erro)})

# ---- Passo 2 e 3: agrupa por cliente único e classifica os pedidos de cada um ----
clientes_unicos = {(l["empresa"], l["buyer_id"]) for l in linhas if "buyer_id" in l}
detalhe_por_cliente = {}
for empresa, buyer_id in clientes_unicos:
    seller_id = obter_seller_id(empresa)
    pedidos_do_cliente = buscar_todos_os_pedidos(seller_id, buyer_id, empresa)
    detalhado = []
    for pedido_obj in pedidos_do_cliente:
        order_id = pedido_obj.get("id")
        item = (pedido_obj.get("order_items") or [{}])[0]
        titulo = (item.get("item") or {}).get("title", "—")
        tipo, claim_id = classificar_pedido(order_id, empresa)
        detalhado.append({"pedido": order_id, "date_created": pedido_obj.get("date_created"),
                           "item": titulo, "pack_id": pedido_obj.get("pack_id"),
                           "classificacao": tipo, "claim_id": claim_id})
    detalhe_por_cliente[(empresa, buyer_id)] = sorted(detalhado, key=lambda p: p["date_created"] or "", reverse=True)

# ---- Passo 4: tabela-resumo, 1 linha por item da lista original ----
tabela = Table(box=box.SIMPLE_HEAVY)
for coluna in ["Nº", "Cliente (informado)", "Nome via API", "Pedido", "Empresa", "buyer_id", "Classificação", "Total pedidos"]:
    tabela.add_column(coluna)

for linha in linhas:
    if "erro" in linha:
        tabela.add_row(str(linha["numero"]), linha["nome_informado"], "[red]erro[/red]",
                        linha["pedido"], linha["empresa"], "—", linha["erro"][:40], "—")
        continue

    pedidos_do_cliente = detalhe_por_cliente[(linha["empresa"], linha["buyer_id"])]
    classificacao = next((p["classificacao"] for p in pedidos_do_cliente if str(p["pedido"]) == str(linha["pedido"])),
                          "não encontrado")
    cor = CORES_POR_TIPO.get(classificacao, "white")
    nome_bate = linha["nome_api"].strip().lower() == linha["nome_informado"].strip().lower()
    nome_api_exibido = linha["nome_api"] if nome_bate else f"[yellow]{linha['nome_api']} (≠ informado)[/yellow]"

    tabela.add_row(str(linha["numero"]), linha["nome_informado"], nome_api_exibido, linha["pedido"],
                    linha["empresa"], str(linha["buyer_id"]), f"[{cor}]{classificacao}[/{cor}]",
                    str(len(pedidos_do_cliente)))

console.print(tabela)

saida = {
    "resumo_por_linha": linhas,
    "detalhe_por_cliente": {f"{e}_{b}": p for (e, b), p in detalhe_por_cliente.items()},
}
with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
    f.write(json.dumps(saida, ensure_ascii=False, indent=2))

console.print(f"\nDetalhe completo salvo em: {CAMINHO_SAIDA}")
console.print("Cola só a tabela acima aqui -- o JSON só sobe se quiser que eu olhe algum caso a fundo.")