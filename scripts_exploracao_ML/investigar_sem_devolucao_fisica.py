# scripts_exploracao_ML/investigar_sem_devolucao_fisica.py

# Função Objetivo: Investigação do candidato 2 da tela Consultar Pedido — pedidos que a
# Ana registrou como devolução e a tela responde "Nenhuma reclamação tem devolução física
# associada". Pra cada pedido mostra: o que está no banco, o pedido e o envio de ida no
# Mercado Livre, TODAS as claims do pedido e o que o endpoint /returns responde pra cada
# uma — inclusive o texto do erro, que a tela engole com `continue` (ela não distingue
# "essa claim não tem devolução" de "a API falhou").
# Só leitura: SELECT no banco e GET na API.
#
# Rodar da raiz do projeto, com o ambiente virtual ativo:
#   python scripts_exploracao_ML/investigar_sem_devolucao_fisica.py
#   python scripts_exploracao_ML/investigar_sem_devolucao_fisica.py --pedido 2000017753255440

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ─── Prepara o Django (mesmo bootstrap dos outros scripts de exploração) ─
_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projeto_sistema_devolucao_mb_sv.settings")

import django

django.setup()

from django.conf import settings
from django.utils import timezone
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api
from devolucoes.models import Devolucao

console = Console()

PASTA_LOGS_ML = settings.DADOS_DIR / "logs" / "mercado_livre"
NOME_LOG = "investigar_sem_devolucao_fisica"
FUSO = ZoneInfo("America/Sao_Paulo")
DATA_INICIO_PONTE = date(2026, 9, 18)

BANCO_POR_CONTA = {"MB": "magazine", "SV": "samvale"}

# Os 7 pedidos em que a tela respondeu "Nenhuma reclamação tem devolução física
# associada" na rodada completa de 03/10/2026 (todos SV).
PEDIDOS_DA_RODADA = [
    "2000017753255440",
    "2000017419665406",
    "2000017756290502",
    "2000017589434980",
    "2000017996760264",
    "2000017855878272",
    "2000017846786276",
]


# ─── Utilitários ────────────────────────────────────────────────────────

def _data(valor_iso):
    if not valor_iso or not isinstance(valor_iso, str):
        return "—"
    try:
        return datetime.fromisoformat(valor_iso).astimezone(FUSO).strftime("%d/%m/%Y")
    except ValueError:
        return valor_iso


def _data_banco(valor):
    return valor.strftime("%d/%m/%Y") if valor else "—"


def _resumir(valor, limite=60):
    if valor in (None, "", [], {}):
        return "—"
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def consultar(endpoint, conta, params=None):
    """GET que nunca levanta erro: devolve (json, None) se deu certo e (None, texto_do_erro)
    se falhou — o texto do ErroAPI já inclui o código HTTP e o corpo da resposta."""
    try:
        resposta = chamar_api(
            "GET", endpoint, pasta_logs=PASTA_LOGS_ML, conta=conta, params=params, nome_log=NOME_LOG,
        )
        return resposta.json(), None
    except Exception as erro:
        return None, f"{type(erro).__name__}: {erro}"


def _codigo_do_erro(texto_do_erro):
    achado = re.search(r"Erro (\d{3})", texto_do_erro or "")
    return achado.group(1) if achado else "erro"


# ─── Investigação de 1 pedido ───────────────────────────────────────────

def investigar_pedido(conta, numero_pedido):
    resumo = {"pedido": numero_pedido, "ponte": "?", "pedido_ml": "—", "envio_ida": "—", "claims": "—", "returns": "—"}
    console.rule(f"[bold]{conta} {numero_pedido}[/bold]")

    # ----- 1) O que está no banco (digitado) -----
    devolucao = Devolucao.objects.using(BANCO_POR_CONTA[conta]).filter(numero_pedido=numero_pedido).first()
    if devolucao is None:
        console.print("[yellow]No banco:[/yellow] não existe devolução com esse número de pedido")
    else:
        criado = devolucao.criado_em
        if timezone.is_aware(criado):
            criado = timezone.localtime(criado)
        resumo["ponte"] = "depois" if criado.date() >= DATA_INICIO_PONTE else "antes"
        console.print(
            "[bold]No banco:[/bold] "
            f"reclamação {_data_banco(devolucao.data_reclamacao_cliente)} | "
            f"recebido pelo cliente {_data_banco(devolucao.data_recebimento_cliente)} | "
            f"recebido por nós {_data_banco(devolucao.data_recebimento_por_nos)} | "
            f"mediação {_data_banco(devolucao.data_abertura_mediacao)} → {_data_banco(devolucao.data_finalizacao_mediacao)} | "
            f"claim_id {devolucao.claim_id or '—'} | "
            f"reembolsado {devolucao.reembolsado} (valor {devolucao.valor_reembolsado}) | "
            f"destino {escape(str(devolucao.destino_produto or '—'))}"
        )
        console.print(f"          motivo digitado: {escape(_resumir(devolucao.motivo_reclamacao, 140))}")

    # ----- 2) O pedido no Mercado Livre -----
    pedido, erro = consultar(f"/orders/{numero_pedido}", conta)
    shipping_id = None
    if erro:
        resumo["pedido_ml"] = f"ERRO {_codigo_do_erro(erro)}"
        console.print(f"[bold]Pedido no ML:[/bold] {escape(_resumir(erro, 200))}")
    else:
        pedido = pedido or {}
        shipping_id = (pedido.get("shipping") or {}).get("id")
        resumo["pedido_ml"] = str(pedido.get("status"))
        console.print(
            f"[bold]Pedido no ML:[/bold] status {pedido.get('status')} | criado {_data(pedido.get('date_created'))} | "
            f"pack {pedido.get('pack_id') or '—'} | tags {escape(_resumir(pedido.get('tags'), 100))}"
        )

    # ----- 3) O envio de ida (mesma chamada que a tela usa pros endereços) -----
    if shipping_id:
        envio, erro = consultar(f"/shipments/{shipping_id}", conta)
        if erro:
            resumo["envio_ida"] = f"ERRO {_codigo_do_erro(erro)}"
            console.print(f"[bold]Envio de ida:[/bold] {escape(_resumir(erro, 200))}")
        else:
            envio = envio or {}
            logistica = envio.get("logistic") if isinstance(envio.get("logistic"), dict) else {}
            resumo["envio_ida"] = f"{envio.get('status')}/{envio.get('substatus') or '—'}"
            console.print(
                f"[bold]Envio de ida:[/bold] status {envio.get('status')} / {envio.get('substatus') or '—'} | "
                f"logistic_type {envio.get('logistic_type') or '—'} | logistic.type {logistica.get('type') or '—'}"
            )
    else:
        console.print("[bold]Envio de ida:[/bold] o pedido não tem shipping.id")

    # ----- 4) Todas as claims do pedido e o /returns de cada uma -----
    busca, erro = consultar("/post-purchase/v1/claims/search", conta, params={"order_id": numero_pedido})
    if erro:
        resumo["claims"] = f"ERRO {_codigo_do_erro(erro)}"
        console.print(f"[bold]Claims:[/bold] {escape(_resumir(erro, 200))}")
        return resumo

    claims = (busca or {}).get("data") or []
    # Mesma ordem de tentativa que a tela usa: tipo return/fulfillment primeiro.
    claims = sorted(claims, key=lambda c: 0 if c.get("type") in ("return", "fulfillment") else 1)
    console.print(f"[bold]Claims:[/bold] {len(claims)} encontrada(s) — na ordem em que a tela tenta")

    descricoes, codigos = [], []
    for claim_da_busca in claims:
        claim_id = claim_da_busca.get("id")
        detalhe, erro_detalhe = consultar(f"/post-purchase/v1/claims/{claim_id}", conta)
        claim = detalhe if detalhe else claim_da_busca
        entidades = ",".join(str(e) for e in (claim.get("related_entities") or [])) or "—"

        retorno, erro_retorno = consultar(f"/post-purchase/v2/claims/{claim_id}/returns", conta)
        if erro_retorno:
            texto_retorno = f"ERRO — {_resumir(erro_retorno, 170)}"
            codigos.append(_codigo_do_erro(erro_retorno))
        elif not retorno:
            texto_retorno = "OK, mas vazio"
            codigos.append("vazio")
        elif isinstance(retorno, dict):
            texto_retorno = (
                f"OK — status {retorno.get('status')} | subtipo {retorno.get('subtype') or '—'} | "
                f"fechada {_data(retorno.get('date_closed'))} | envios {len(retorno.get('shipments') or [])}"
            )
            codigos.append("OK")
        else:
            texto_retorno = f"OK, formato inesperado ({type(retorno).__name__})"
            codigos.append("formato?")

        descricoes.append(f"{claim.get('type')}/{claim.get('stage')}/{claim.get('status')}")
        console.print(
            f"  claim {claim_id} | tipo {claim.get('type')} | etapa {claim.get('stage')} | status {claim.get('status')} | "
            f"motivo {claim.get('reason_id') or '—'} | aberta {_data(claim.get('date_created'))} | "
            f"atualizada {_data(claim.get('last_updated'))}"
        )
        console.print(
            f"      entidades relacionadas: {escape(entidades)} | resolução: {escape(_resumir(claim.get('resolution'), 90))}"
        )
        console.print(f"      /returns → {escape(texto_retorno)}")
        if erro_detalhe:
            console.print(f"      [yellow](o detalhe da claim falhou: {escape(_resumir(erro_detalhe, 120))})[/yellow]")

    resumo["claims"] = "; ".join(descricoes) or "nenhuma"
    resumo["returns"] = ", ".join(codigos) or "—"
    return resumo


# ─── Resumo final ───────────────────────────────────────────────────────

def imprimir_resumo_final(resumos):
    tabela = Table(title="Resumo — o que cada pedido tem no Mercado Livre")
    for coluna in ("Pedido", "Ponte", "Pedido ML", "Envio de ida", "Claims (tipo/etapa/status)", "/returns de cada claim"):
        tabela.add_column(coluna, overflow="fold")
    for r in resumos:
        tabela.add_row(
            r["pedido"], r["ponte"], escape(r["pedido_ml"]), escape(r["envio_ida"]),
            escape(r["claims"]), escape(r["returns"]),
        )
    console.print(tabela)


# ─── Execução ───────────────────────────────────────────────────────────

def ler_argumentos():
    parser = argparse.ArgumentParser(description="Investiga pedidos que a tela Consultar Pedido diz não ter devolução física.")
    parser.add_argument("--conta", choices=list(BANCO_POR_CONTA), default="SV", help="MB ou SV (padrão: SV)")
    parser.add_argument("--pedido", nargs="+", help="um ou mais números de pedido (padrão: os 7 da rodada de 03/10/2026)")
    return parser.parse_args()


def main():
    argumentos = ler_argumentos()
    pedidos = argumentos.pedido or PEDIDOS_DA_RODADA

    console.print(f"[bold]{len(pedidos)} pedido(s)[/bold], conta {argumentos.conta} — só leitura: SELECT no banco e GET na API.\n")

    resumos = []
    try:
        for numero_pedido in pedidos:
            resumos.append(investigar_pedido(argumentos.conta, numero_pedido))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrompido — mostrando só o que já foi consultado.[/yellow]")

    console.print()
    if resumos:
        imprimir_resumo_final(resumos)


if __name__ == "__main__":
    main()