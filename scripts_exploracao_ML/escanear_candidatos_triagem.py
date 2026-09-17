# scripts_exploracao_ML/escanear_candidatos_triagem.py
#
# Objetivo: escanear várias reclamações FECHADAS de uma vez (GET /post-purchase/v1/claims/search)
# e, pra cada uma, encadear automaticamente GET /post-purchase/v2/claims/$CLAIM_ID/returns,
# GET /post-purchase/v1/returns/$RETURN_ID/reviews e GET /orders/$ORDER_ID (campo "fulfilled") --
# pra achar, sem testar candidato por candidato na mão, um caso cuja review de triagem tenha
# product_condition DIFERENTE de "unsaleable", OU que seja venda Full de verdade.
#
# Contexto (atualizado 17/09/2026): já testamos 8 casos reais de triagem via este script --
# 3 "unsaleable" e 5 "saleable" -- e em NENHUM dos 8 apareceu um 2º shipment "return_from_triage",
# nem uma continuação no histórico do mesmo shipment depois de "delivered". As 2 hipóteses
# testadas (condição do produto decide / é o mesmo shipment ganhando status novo) foram
# derrubadas. Hipótese atual: talvez o par return/return_from_triage só exista pra devoluções
# de venda FULL de verdade (fulfilled: true) -- nenhum dos 8 candidatos testados até agora foi
# confirmado como Full. Por isso o campo "fulfilled" do pedido entrou no escaneamento.
#
# Não filtra por "type" de propósito -- os casos já confirmados como devolução real vieram com
# type:"mediations" ou até "returns" (plural, confirma inconsistência já suspeitada na doc),
# não "return"/"fulfillment" -- filtrar por tipo descartaria silenciosamente os próprios casos
# que procuramos (mesmo raciocínio já usado em investigar_claims_recentes.py).
#
# Só leitura. Não grava nada no banco. Sobrescreve o arquivo de saída (nunca acrescenta) a cada
# execução. Pode demorar mais que os outros scripts -- pra cada claim candidato, faz até mais
# 3 chamadas de API (devolução + review + pedido), então o LIMITE por padrão é baixo de propósito.

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import json
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Escaneia reclamações fechadas em lote e busca, pra cada uma, a devolução, a review e o fulfilled do pedido."
    )
    parser.add_argument("--empresa", type=str, required=True, choices=["MB", "SV"],
                         help="Conta a consultar (MB ou SV).")
    parser.add_argument("--dias-atras-inicio", type=int, default=90, dest="dias_atras_inicio",
                         help="Início da janela de busca, em dias atrás (padrão: 90).")
    parser.add_argument("--dias-atras-fim", type=int, default=30, dest="dias_atras_fim",
                         help="Fim da janela de busca, em dias atrás -- folga até hoje pro processo "
                              "ter tido tempo de concluir (padrão: 30).")
    parser.add_argument("--limite", type=int, default=15,
                         help="Quantas reclamações fechadas trazer da busca inicial, e testar 1 a 1 "
                              "(padrão: 15; cada uma gera até +3 chamadas de API extras).")
    parser.add_argument("--tipo", type=str, default=None,
                         help="Filtro opcional de 'type' da reclamação (ex: mediations, return). "
                              "Por padrão não filtra -- ver comentário no topo do arquivo.")
    args = parser.parse_args()
    return args.empresa, args.dias_atras_inicio, args.dias_atras_fim, args.limite, args.tipo


CONTA, DIAS_ATRAS_INICIO, DIAS_ATRAS_FIM, LIMITE, TIPO_FILTRO = ler_argumentos()

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
NOME_LOG = "escanear_candidatos_triagem"
CAMINHO_SAIDA = Path(__file__).resolve().parent / f"escaneamento_candidatos_triagem_{CONTA}.json"
FUSO_HORARIO_EXIBICAO = ZoneInfo("America/Sao_Paulo")

console = Console()


def formatar_data_para_filtro(instante):
    """Mesmo formato exigido pelo parâmetro 'range' da API: milissegundos obrigatórios, offset
    sem dois-pontos (ex: 2026-07-15T00:00:00.000-0300)."""
    texto = instante.isoformat(timespec="milliseconds")
    return texto[:-6] + texto[-6:].replace(":", "")


def buscar_devolucao(claim_id):
    """Retorna (return_id, shipments) do claim, ou (None, []) se não existir devolução associada
    (claim de outro tipo, ex: cancelamento puro sem devolução física)."""
    try:
        resposta = chamar_api(
            "GET", f"/post-purchase/v2/claims/{claim_id}/returns",
            pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        return None, []
    dados = resposta.json()
    return dados.get("id"), dados.get("shipments", [])


def buscar_review(return_id):
    """Retorna um dict com 'method' + os campos do 1º resource_review, ou None se não existir
    review pra essa devolução (ex: devolução ainda sem revisão, ou method 'none')."""
    if return_id is None:
        return None
    try:
        resposta = chamar_api(
            "GET", f"/post-purchase/v1/returns/{return_id}/reviews",
            pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        return None
    reviews = resposta.json().get("reviews", [])
    if not reviews:
        return None
    resource_reviews = reviews[0].get("resource_reviews", [])
    if not resource_reviews:
        return {"method": reviews[0].get("method")}
    return {"method": reviews[0].get("method"), **resource_reviews[0]}


def buscar_fulfilled(order_id):
    """Retorna o campo 'fulfilled' do PEDIDO (nivel pedido, GET /orders/$ID -- não confundir com
    o 'fulfilled' que também existe no nivel do claim), ou None se a chamada falhar (ex: claims
    cujo resource_id não é um order_id de verdade, como cancel_purchase)."""
    try:
        resposta = chamar_api(
            "GET", f"/orders/{order_id}",
            pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        return None
    return resposta.json().get("fulfilled")


try:
    resposta_me = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG)
    user_id = resposta_me.json()["id"]

    agora = datetime.now(FUSO_HORARIO_EXIBICAO)
    inicio_janela = agora - timedelta(days=DIAS_ATRAS_INICIO)
    fim_janela = agora - timedelta(days=DIAS_ATRAS_FIM)

    console.print()
    console.print(f"[bold blue]Buscando reclamações ENCERRADAS da conta {CONTA} (vendedor {user_id})[/bold blue]")
    console.print(f"  Janela: {inicio_janela.strftime('%d/%m/%Y')} até {fim_janela.strftime('%d/%m/%Y')}"
                  + (f" | tipo: {TIPO_FILTRO}" if TIPO_FILTRO else " | todos os tipos"))

    params = {
        "players.user_id": user_id,
        "players.role": "respondent",
        "status": "closed",
        "range": (
            f"date_created:after:{formatar_data_para_filtro(inicio_janela)},"
            f"before:{formatar_data_para_filtro(fim_janela)}"
        ),
        "sort": "date_created:desc",
        "limit": LIMITE,
        "offset": 0,
    }
    if TIPO_FILTRO:
        params["type"] = TIPO_FILTRO

    with console.status("[bold green]Consultando /post-purchase/v1/claims/search...[/bold green]", spinner="dots"):
        resposta_busca = chamar_api(
            "GET", "/post-purchase/v1/claims/search",
            pasta_logs=PASTA_LOGS, conta=CONTA, params=params, nome_log=NOME_LOG,
        )
    claims = resposta_busca.json().get("data", [])

    if not claims:
        console.print("  Nenhuma reclamação encerrada nessa janela. Ajuste --dias-atras-inicio/--dias-atras-fim.")
        sys.exit(0)

    console.print(f"  {len(claims)} reclamação(ões) encontrada(s) -- testando devolução + review + fulfilled de cada uma...")
    console.print()

    resultados = []
    for indice, claim in enumerate(claims, start=1):
        claim_id = claim.get("id")
        order_id = claim.get("resource_id")
        console.print(f"  [{indice}/{len(claims)}] claim {claim_id} (pedido {order_id})...")

        return_id, shipments = buscar_devolucao(claim_id)
        review = buscar_review(return_id)
        fulfilled = buscar_fulfilled(order_id)

        resultados.append({
            "claim_id": claim_id,
            "order_id": order_id,
            "type": claim.get("type"),
            "resource": claim.get("resource"),
            "stage": claim.get("stage"),
            "reason_id": claim.get("reason_id"),
            "date_created": claim.get("date_created"),
            "resolution_reason": (claim.get("resolution") or {}).get("reason"),
            "resolution_applied_coverage": (claim.get("resolution") or {}).get("applied_coverage"),
            "fulfilled": fulfilled,
            "return_id": return_id,
            "shipments_count": len(shipments),
            "shipment_types": [s.get("type") for s in shipments],
            "review_method": review.get("method") if review else None,
            "product_condition": review.get("product_condition") if review else None,
            "product_destination": review.get("product_destination") if review else None,
            "seller_status": review.get("seller_status") if review else None,
        })
        time.sleep(0.2)  # folga gentil entre chamadas, além do retry automático do chamar_api em 429

except (ErroAPI, ErroAutenticacaoAPI) as erro:
    console.print(f"\n[bold red]Erro ao chamar a API:[/bold red] {escape(str(erro))}")
else:
    tabela = Table(box=box.SIMPLE_HEAD, header_style="bold")
    tabela.add_column("Claim ID")
    tabela.add_column("Pedido")
    tabela.add_column("Tipo")
    tabela.add_column("Fulfilled")
    tabela.add_column("Return ID")
    tabela.add_column("Nº Ship.")
    tabela.add_column("Review Method")
    tabela.add_column("Product Condition")
    tabela.add_column("Seller Status")
    tabela.add_column("Observação")

    for r in resultados:
        observacao = ""
        if r["shipments_count"] > 1:
            observacao = "[bold red]2+ SHIPMENTS[/bold red]"
        elif r["fulfilled"] is True:
            observacao = "[bold yellow]FULL DE VERDADE[/bold yellow]"
        elif r["product_condition"] and r["product_condition"] != "unsaleable":
            observacao = "[bold green]CANDIDATO (condição != unsaleable)[/bold green]"

        tabela.add_row(
            str(r["claim_id"]),
            str(r["order_id"]),
            escape(r["type"] or "—"),
            escape(str(r["fulfilled"]) if r["fulfilled"] is not None else "—"),
            str(r["return_id"] or "—"),
            str(r["shipments_count"]),
            escape(r["review_method"] or "—"),
            escape(r["product_condition"] or "—"),
            escape(r["seller_status"] or "—"),
            observacao,
        )

    console.print()
    console.print(tabela)
    console.print()

    saida = {
        "conta": CONTA,
        "janela": {"dias_atras_inicio": DIAS_ATRAS_INICIO, "dias_atras_fim": DIAS_ATRAS_FIM},
        "total_testado": len(resultados),
        "resultados": resultados,
    }
    texto_json = json.dumps(saida, ensure_ascii=False, indent=2)
    texto_json_oculto = texto_json.replace(str(user_id), "SEU_USER_ID_OCULTO")

    with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
        f.write(texto_json_oculto)

    console.print(f"  Resultado completo salvo em: {CAMINHO_SAIDA}")
    console.print("  Suba esse arquivo na conversa pra eu analisar.")