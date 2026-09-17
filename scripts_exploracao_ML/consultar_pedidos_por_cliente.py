# scripts_exploracao_ML/consultar_pedidos_por_cliente.py
#
# Objetivo: dado o buyer_id do cliente (achado do lado do nome na etiqueta de
# venda comum, confirmado em 17/09/2026), listar TODOS os pedidos reais desse
# cliente pra você -- ordenados por data -- e classificar cada um em 1 de 3
# tipos, reaproveitando a mesma lógica de decisão que view_consultar_pedido()
# e consultar_fluxo_devolucao.py já usam pra 1 pedido conhecido:
#
#   - "Sem problema"                    -> nenhuma reclamação encontrada pro pedido
#   - "Com reclamação (sem devolução)"  -> tem reclamação, mas nenhuma delas
#                                          gerou uma devolução física associada
#   - "Com devolução"                   -> pelo menos 1 reclamação tem devolução
#                                          física associada (post-purchase/v2/
#                                          claims/$ID/returns respondeu com dado real)
#
# Isso existe pra resolver a ambiguidade real do "número grande" da etiqueta
# (às vezes é o Pedido, às vezes é o Pack ID/carrinho -- caras parecidas,
# fácil de confundir no dia a dia) -- o buyer_id nunca tem essa ambiguidade e
# sempre resolve pra pedidos individuais, nunca pra um carrinho.
#
# Só leitura. Não toca no banco. Sobrescreve o arquivo de saída (nunca
# acrescenta) a cada execução.

import argparse
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from rich import box
from rich.console import Console
from rich.table import Table

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Lista os pedidos de um cliente (por buyer_id) e classifica cada um "
                     "em sem problema / com reclamação / com devolução."
    )
    parser.add_argument("--empresa", type=str, required=True, choices=["MB", "SV"],
                         help="Conta a consultar (MB ou SV).")
    parser.add_argument("--buyer-id", type=str, required=True, dest="buyer_id",
                         help="ID do cliente (código visto ao lado do nome na etiqueta).")
    args = parser.parse_args()
    return args.empresa, args.buyer_id


CONTA, BUYER_ID = ler_argumentos()

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
NOME_LOG = "consultar_pedidos_por_cliente"
CAMINHO_SAIDA = Path(__file__).resolve().parent / f"pedidos_do_cliente_{BUYER_ID}_{CONTA}.json"
FUSO_HORARIO_EXIBICAO = ZoneInfo("America/Sao_Paulo")

console = Console()

CORES_POR_TIPO = {
    "Sem problema": "green",
    "Com reclamação (sem devolução)": "yellow",
    "Com devolução": "red",
}


def buscar_todos_os_pedidos(seller_id, buyer_id):
    """Pagina o /orders/search inteiro pra esse buyer, mesmo se passar do limite
    de 1 página -- pra garantir que 'todos os pedidos' seja literal."""
    pedidos = []
    offset = 0
    limite_por_pagina = 50
    while True:
        resposta = chamar_api(
            "GET", "/orders/search",
            pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
            params={
                "seller": seller_id,
                "buyer": buyer_id,
                "sort": "date_desc",
                "limit": limite_por_pagina,
                "offset": offset,
            },
        )
        resultado = resposta.json()
        pagina = resultado.get("results", [])
        pedidos.extend(pagina)
        total = (resultado.get("paging") or {}).get("total", len(pedidos))
        offset += limite_por_pagina
        if offset >= total or not pagina:
            break
    return pedidos


def classificar_pedido(order_id):
    """Mesma lógica de decisão de view_consultar_pedido(): busca as reclamações
    do pedido, tenta a devolução de cada uma (tipo return/fulfillment primeiro,
    já que o campo 'type' sozinho não é confiável -- já visto em outros scripts
    do projeto), e classifica pelo resultado."""
    try:
        resposta_claims = chamar_api(
            "GET", "/post-purchase/v1/claims/search",
            pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
            params={"order_id": order_id},
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        return "Sem problema", None  # erro na busca de claim = tratado como sem problema, não interrompe o lote

    claims = resposta_claims.json().get("data", [])
    if not claims:
        return "Sem problema", None

    claims_em_ordem_de_tentativa = sorted(
        claims, key=lambda c: 0 if c.get("type") in ("return", "fulfillment") else 1
    )

    for candidata in claims_em_ordem_de_tentativa:
        try:
            resposta_devolucao = chamar_api(
                "GET", f"/post-purchase/v2/claims/{candidata['id']}/returns",
                pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
            )
        except (ErroAPI, ErroAutenticacaoAPI):
            continue
        devolucao = resposta_devolucao.json()
        if devolucao:
            return "Com devolução", candidata.get("id")

    return "Com reclamação (sem devolução)", claims[0].get("id")


try:
    resposta_me = chamar_api(
        "GET", "/users/me",
        pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
    )
    seller_id = resposta_me.json()["id"]

    pedidos = buscar_todos_os_pedidos(seller_id, BUYER_ID)
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar a API: {erro}")
else:
    console.print(f"\nCliente (buyer_id {BUYER_ID}) -- {len(pedidos)} pedido(s) encontrado(s) pra conta {CONTA}.\n")

    tabela = Table(box=box.SIMPLE_HEAVY)
    tabela.add_column("Pedido")
    tabela.add_column("Data")
    tabela.add_column("Item")
    tabela.add_column("Pack ID")
    tabela.add_column("Classificação")

    resultado_final = []
    for pedido in pedidos:
        order_id = pedido.get("id")
        item = (pedido.get("order_items") or [{}])[0]
        titulo = (item.get("item") or {}).get("title", "—")
        pack_id = pedido.get("pack_id")
        tipo, claim_id = classificar_pedido(order_id)

        tabela.add_row(
            str(order_id),
            pedido.get("date_created", "—")[:19],
            titulo[:50],
            str(pack_id) if pack_id else "—",
            f"[{CORES_POR_TIPO[tipo]}]{tipo}[/{CORES_POR_TIPO[tipo]}]",
        )
        resultado_final.append({
            "pedido": order_id,
            "date_created": pedido.get("date_created"),
            "item": titulo,
            "pack_id": pack_id,
            "classificacao": tipo,
            "claim_id": claim_id,
        })

    console.print(tabela)

    texto_json = json.dumps(resultado_final, ensure_ascii=False, indent=2)
    with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
        f.write(texto_json)

    console.print(f"\nResultado completo salvo em: {CAMINHO_SAIDA}")
    console.print("Suba esse arquivo (ou cola a tabela acima) na conversa pra eu analisar.")