# scripts_exploracao_ML/preencher_precos_faltantes.py
#
# Função Objetivo: Preencher o "Preço do produto" das devoluções que ficaram sem ele, buscando o valor
# na API do Mercado Livre. É o MESMO dado que a tela Nova devolução já traz sozinho quando a Ana usa o
# botão "Criar devolução" da Consultar Pedido: GET /orders/{pedido} -> order_items[i].unit_price (preço
# unitário JÁ com o desconto aplicado — decisão de Matheus, 19/09/2026).
#
# Por que existe: no teste de 05/10/2026 (testar_visoes_prontas_analise.py) metade das devoluções
# (25 de 49) estava sem preço, e sem preço a Análise não consegue somar dinheiro nem calcular a
# "diferença" (preço − reembolsado). Esse dado é da API e não depende de ninguém digitar, então pode
# ser completado em lote.
#
# O QUE ELE FAZ (por padrão, só SIMULA — nada é gravado):
#   1. Pega as devoluções com preço vazio, nas 2 empresas (MB e SV).
#   2. Para cada uma de Mercado Livre, consulta o pedido (1 chamada GET) e decide:
#        - pedido com 1 produto  -> usa o unit_price dele;
#        - pedido com vários     -> só usa se EXATAMENTE 1 dos produtos tiver o SKU igual ao SKU do
#                                   produto cadastrado na devolução; senão PULA (melhor vazio do que o
#                                   preço do produto errado — mesma regra do botão "Criar devolução");
#        - outras plataformas, número de pedido fora do padrão do ML, pedido que a API não acha,
#          resposta parcial, preço ausente/zero ou moeda diferente de BRL -> PULA e diz o motivo.
#   3. Mostra 2 tabelas: "vai preencher" (com o preço que seria gravado) e "pulou / erro" (com o motivo).
#
# SÓ GRAVA com --aplicar, e mesmo assim pede para você digitar GRAVAR depois de ver a lista. Regras de
# segurança de quem grava:
#   - só preenche o que está VAZIO: nunca sobrescreve um preço que a Ana digitou (a gravação confere de
#     novo no instante do UPDATE; se alguém preencheu no meio tempo, aquela linha é pulada);
#   - mexe SOMENTE no campo preco_produto — nenhum outro campo, nem os "selos de nuvem"
#     (campos_automaticos_ml): esses selos contam o que veio do ML NA CRIAÇÃO da devolução, e um preço
#     completado depois não faz parte dessa história;
#   - cada empresa é gravada numa transação só (ou entra tudo daquela empresa, ou nada);
#   - guarda um arquivo com os IDs alterados (e o valor anterior, sempre vazio) para você poder desfazer.
#
# * [EXPLICAÇÃO] → cota do ML: o app é o MESMO do Sistema Interno V2 (18.000 chamadas/hora divididas).
#   Aqui é 1 chamada por devolução sem preço (algumas dezenas), com o espaçador padrão de 0,4 s entre
#   chamadas (é uma varredura em lote, então fica com a proteção ligada).
#
# Rodar da raiz do projeto, com o ambiente virtual ativo:
#   python scripts_exploracao_ML/preencher_precos_faltantes.py                      (simulação, as 2 empresas)
#   python scripts_exploracao_ML/preencher_precos_faltantes.py --conta SV           (simulação, só uma empresa)
#   python scripts_exploracao_ML/preencher_precos_faltantes.py --pedido 2000018229470186   (simula 1 pedido)
#   python scripts_exploracao_ML/preencher_precos_faltantes.py --limite 3           (teste curto: só 3 por empresa)
#   python scripts_exploracao_ML/preencher_precos_faltantes.py --aplicar            (simula, mostra e pede GRAVAR)
#
# Saídas:
#   scripts_exploracao_ML/logs/preencher_precos_faltantes_relatorio.txt       (o que aparece na tela)
#   scripts_exploracao_ML/preencher_precos_faltantes.json                     (plano da simulação)
#   scripts_exploracao_ML/preencher_precos_faltantes_aplicado_AAAAMMDD_HHMMSS.json   (só com --aplicar: o que foi gravado)

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

# ─── Prepara o Django (mesmo bootstrap dos outros scripts de exploração) ─
_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projeto_sistema_devolucao_mb_sv.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from api_mercado_livre.core.estrutura_api.cliente_api import ErroAPI, ErroAutenticacaoAPI, chamar_api  # noqa: E402
from devolucoes.models import Devolucao  # noqa: E402

BANCOS = [("MB", "magazine"), ("SV", "samvale")]
PASTA_DO_SCRIPT = Path(__file__).resolve().parent
PASTA_LOGS = PASTA_DO_SCRIPT / "logs"
CAMINHO_RELATORIO = PASTA_LOGS / "preencher_precos_faltantes_relatorio.txt"
CAMINHO_PLANO_JSON = PASTA_DO_SCRIPT / "preencher_precos_faltantes.json"
PLATAFORMA_ML = Devolucao.PLATAFORMA_MERCADO_LIVRE
PRECO_MAXIMO = Decimal("99999999.99")  # preco_produto = DecimalField(max_digits=10, decimal_places=2)

try:  # Windows: garante acento no terminal e no arquivo
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

console = Console(record=True, width=max(shutil.get_terminal_size((130, 40)).columns, 130))


# ─────────────────────────── Funções de apoio ───────────────────────────

def _normalizar_sku(valor):
    return str(valor or "").strip().casefold()


def brl(valor):
    if valor is None:
        return "—"
    texto = f"{Decimal(valor):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def curto(texto, limite):
    texto = (texto or "").strip()
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _resultado(conta, devolucao, status, motivo, **extra):
    base = {
        "conta": conta,
        "id": devolucao.id,
        "pedido": devolucao.numero_pedido,
        "produto": devolucao.produto.nome,
        "sku_cadastrado": devolucao.produto.sku or "",
        "plataforma": devolucao.nome_plataforma,
        "status": status,  # "preenche" | "pulou" | "erro"
        "motivo": motivo,
        "preco": None,
        "quantidade": None,
        "sku_do_pedido": "",
        "sku_confere": None,
        "itens_no_pedido": None,
    }
    base.update(extra)
    return base


def consultar_preco(conta, devolucao):
    """Decide o que fazer com UMA devolução sem preço. Só faz GET na API; não toca no banco."""
    if devolucao.nome_plataforma != PLATAFORMA_ML:
        return _resultado(conta, devolucao, "pulou", f"plataforma {devolucao.nome_plataforma} (só o Mercado Livre tem API aqui)")

    pedido = (devolucao.numero_pedido or "").strip()
    if not pedido.isdigit():
        return _resultado(conta, devolucao, "pulou", "número do pedido fora do padrão do Mercado Livre (só dígitos)")

    try:
        resposta = chamar_api(
            "GET", f"/orders/{pedido}",
            pasta_logs=PASTA_LOGS, conta=conta, nome_log="preencher_precos_faltantes",
        )
    except ErroAutenticacaoAPI as erro:
        return _resultado(conta, devolucao, "erro", f"autenticação recusada pela API: {curto(str(erro), 120)}")
    except ErroAPI as erro:
        texto = str(erro)
        if "Erro 404" in texto:
            return _resultado(conta, devolucao, "erro", "pedido não encontrado na API (404) — pode ser Pack ID ou pedido muito antigo")
        return _resultado(conta, devolucao, "erro", f"erro na API: {curto(texto, 120)}")
    except Exception as erro:  # rede caiu, JSON ilegível etc.: não derruba o lote inteiro
        return _resultado(conta, devolucao, "erro", f"falha inesperada: {curto(repr(erro), 120)}")

    if resposta.status_code == 206:
        return _resultado(conta, devolucao, "erro", "a API devolveu resposta parcial (206) — não usada")

    try:
        itens = resposta.json().get("order_items") or []
    except Exception:
        return _resultado(conta, devolucao, "erro", "resposta da API ilegível (não é JSON)")

    if not itens:
        return _resultado(conta, devolucao, "pulou", "o pedido não tem order_items na API", itens_no_pedido=0)

    sku_cadastrado = _normalizar_sku(devolucao.produto.sku)
    if len(itens) == 1:
        escolhido = itens[0]
    else:
        # Pedido com vários produtos: só aceita se exatamente 1 deles tem o SKU do produto cadastrado.
        candidatos = [i for i in itens if sku_cadastrado and _normalizar_sku((i.get("item") or {}).get("seller_sku")) == sku_cadastrado]
        if len(candidatos) != 1:
            return _resultado(
                conta, devolucao, "pulou",
                f"pedido com {len(itens)} produtos e {'nenhum' if not candidatos else 'mais de um'} bate com o SKU cadastrado"
                + ("" if sku_cadastrado else " (o produto cadastrado não tem SKU)"),
                itens_no_pedido=len(itens),
            )
        escolhido = candidatos[0]

    sku_do_pedido = (escolhido.get("item") or {}).get("seller_sku") or ""
    sku_confere = None
    if sku_cadastrado and sku_do_pedido:
        sku_confere = _normalizar_sku(sku_do_pedido) == sku_cadastrado
    extras = {
        "quantidade": escolhido.get("quantity"),
        "sku_do_pedido": sku_do_pedido,
        "sku_confere": sku_confere,
        "itens_no_pedido": len(itens),
    }

    moeda = escolhido.get("currency_id")
    if moeda and moeda != "BRL":
        return _resultado(conta, devolucao, "pulou", f"moeda {moeda} (esperado BRL)", **extras)

    bruto = escolhido.get("unit_price")
    try:
        preco = Decimal(str(bruto)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return _resultado(conta, devolucao, "pulou", f"a API não trouxe unit_price utilizável (veio {bruto!r})", **extras)
    if preco <= 0 or preco > PRECO_MAXIMO:
        return _resultado(conta, devolucao, "pulou", f"unit_price fora do esperado ({preco})", **extras)

    return _resultado(conta, devolucao, "preenche", "ok", preco=preco, **extras)


def planejar(conta, alias, pedido, limite):
    """Simulação de uma empresa: devolve 1 resultado por devolução sem preço."""
    consulta = Devolucao.objects.using(alias).select_related("produto").filter(preco_produto__isnull=True).order_by("id")
    if pedido:
        consulta = consulta.filter(numero_pedido=pedido)
    devolucoes = list(consulta)
    if limite:
        devolucoes = devolucoes[:limite]
    resultados = []
    for indice, devolucao in enumerate(devolucoes, start=1):
        console.print(f"[dim]{conta}: consultando {indice}/{len(devolucoes)} — pedido {devolucao.numero_pedido}[/dim]")
        resultados.append(consultar_preco(conta, devolucao))
    return resultados


def gravar(conta, alias, resultados):
    """Grava os preços (só onde ainda está vazio). Devolve (gravados, nao_gravados). 1 transação por empresa."""
    gravados, nao_gravados = [], []
    a_gravar = [r for r in resultados if r["status"] == "preenche"]
    with transaction.atomic(using=alias):
        for r in a_gravar:
            # preco_produto__isnull=True no próprio UPDATE: se alguém preencheu no meio tempo, não sobrescreve.
            linhas = Devolucao.objects.using(alias).filter(pk=r["id"], preco_produto__isnull=True).update(preco_produto=r["preco"])
            if linhas:
                gravados.append({
                    "conta": conta, "id": r["id"], "pedido": r["pedido"],
                    "preco_gravado": str(r["preco"]), "valor_anterior": None,
                    "gravado_em": datetime.now().isoformat(timespec="seconds"),
                })
            else:
                nao_gravados.append({"conta": conta, "id": r["id"], "pedido": r["pedido"], "motivo": "já estava preenchida (alguém digitou no meio tempo)"})
    return gravados, nao_gravados


def confirmar_gravacao(quantidade):
    """Pede para o usuário digitar GRAVAR. Fora de um terminal interativo, nunca grava."""
    if not sys.stdin or not sys.stdin.isatty():
        console.print("[red]Sem terminal interativo para confirmar — nada foi gravado.[/red]")
        return False
    resposta = input(f"\nGravar {quantidade} preço(s) no banco? Digite GRAVAR para confirmar (qualquer outra coisa cancela): ")
    return resposta.strip() == "GRAVAR"


# ─────────────────────────── Saída na tela ───────────────────────────

def mostrar_resultados(resultados):
    preenche = [r for r in resultados if r["status"] == "preenche"]
    outros = [r for r in resultados if r["status"] != "preenche"]

    resumo = Table(title="Resumo da simulação", box=box.SIMPLE_HEAVY, title_justify="left")
    for coluna in ("Empresa", "Sem preço", "Vai preencher", "Pulou", "Erro", "Soma que seria gravada"):
        resumo.add_column(coluna, justify="left" if coluna == "Empresa" else "right")
    contas = sorted({r["conta"] for r in resultados})
    for conta in contas + (["Total"] if len(contas) > 1 else []):
        lista = resultados if conta == "Total" else [r for r in resultados if r["conta"] == conta]
        soma = sum((r["preco"] for r in lista if r["status"] == "preenche"), Decimal("0"))
        resumo.add_row(conta, str(len(lista)), str(sum(1 for r in lista if r["status"] == "preenche")),
                       str(sum(1 for r in lista if r["status"] == "pulou")), str(sum(1 for r in lista if r["status"] == "erro")), brl(soma))
    console.print(resumo)

    if preenche:
        tabela = Table(title="VAI PREENCHER (nada é gravado sem --aplicar)", box=box.SIMPLE_HEAVY, title_justify="left")
        for coluna in ("Emp.", "ID", "Pedido", "Produto", "Itens no pedido", "Qtd", "SKU confere?", "Preço"):
            tabela.add_column(coluna, justify="right" if coluna in ("ID", "Itens no pedido", "Qtd", "Preço") else "left", overflow="fold")
        for r in preenche:
            confere = "sim" if r["sku_confere"] is True else ("NÃO" if r["sku_confere"] is False else "sem SKU p/ comparar")
            tabela.add_row(r["conta"], str(r["id"]), r["pedido"], curto(r["produto"], 34), str(r["itens_no_pedido"]),
                           str(r["quantidade"] if r["quantidade"] is not None else "—"), confere, brl(r["preco"]))
        console.print(tabela)
        divergentes = [r for r in preenche if r["sku_confere"] is False]
        if divergentes:
            console.print(f"[yellow]Atenção: em {len(divergentes)} caso(s) o SKU do pedido é diferente do SKU do produto cadastrado "
                          f"(pedidos: {', '.join(r['pedido'] for r in divergentes)}). O preço é o do pedido, mas vale conferir se a devolução "
                          f"está com o produto certo.[/yellow]")

    if outros:
        tabela = Table(title="PULOU / ERRO (continuam sem preço — a Ana digita)", box=box.SIMPLE_HEAVY, title_justify="left")
        for coluna in ("Emp.", "ID", "Pedido", "Produto", "Situação", "Motivo"):
            tabela.add_column(coluna, overflow="fold")
        for r in outros:
            tabela.add_row(r["conta"], str(r["id"]), r["pedido"], curto(r["produto"], 30), r["status"], r["motivo"])
        console.print(tabela)


# ─────────────────────────── Programa principal ───────────────────────────

def principal():
    analisador = argparse.ArgumentParser(description="Preenche o preço do produto das devoluções que estão sem ele, pela API do ML (simulação por padrão).")
    analisador.add_argument("--conta", choices=["MB", "SV"], help="Só uma empresa (padrão: as duas).")
    analisador.add_argument("--pedido", help="Só a devolução desse número de pedido.")
    analisador.add_argument("--limite", type=int, help="Máximo de devoluções por empresa (para um teste curto).")
    analisador.add_argument("--aplicar", action="store_true", help="Depois da simulação, grava (pede para digitar GRAVAR).")
    args = analisador.parse_args()

    bancos = [(c, a) for c, a in BANCOS if not args.conta or c == args.conta]
    console.print(f"[bold]Preencher preços faltantes pela API do ML[/bold]  ({'SIMULAÇÃO + gravação com confirmação' if args.aplicar else 'só SIMULAÇÃO, nada é gravado'})")

    resultados_por_conta = {}
    for conta, alias in bancos:
        resultados_por_conta[conta] = planejar(conta, alias, args.pedido, args.limite)
    todos = [r for lista in resultados_por_conta.values() for r in lista]

    console.print()
    if not todos:
        console.print("Nenhuma devolução sem preço encontrada (com esses filtros). Nada a fazer.")
    else:
        mostrar_resultados(todos)

    # ─── Plano em JSON (sempre) ───
    def _serializar(valor):
        if isinstance(valor, Decimal):
            return str(valor)
        raise TypeError(f"Tipo não serializável: {type(valor)}")
    with open(CAMINHO_PLANO_JSON, "w", encoding="utf-8") as arquivo:
        json.dump({"gerado_em": datetime.now().isoformat(timespec="seconds"), "aplicado": False, "resultados": todos},
                  arquivo, ensure_ascii=False, indent=2, default=_serializar)

    # ─── Gravação (só com --aplicar e confirmação) ───
    a_gravar = [r for r in todos if r["status"] == "preenche"]
    if args.aplicar and a_gravar:
        if confirmar_gravacao(len(a_gravar)):
            gravados, nao_gravados = [], []
            for conta, alias in bancos:
                g, n = gravar(conta, alias, resultados_por_conta[conta])
                gravados += g
                nao_gravados += n
            carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho_aplicado = PASTA_DO_SCRIPT / f"preencher_precos_faltantes_aplicado_{carimbo}.json"
            with open(caminho_aplicado, "w", encoding="utf-8") as arquivo:
                json.dump({"gravado_em": datetime.now().isoformat(timespec="seconds"), "gravados": gravados, "nao_gravados": nao_gravados},
                          arquivo, ensure_ascii=False, indent=2)
            console.print(f"\n[green]Gravados: {len(gravados)}[/green] · não gravados (já preenchidos no meio tempo): {len(nao_gravados)}")
            console.print(f"Lista dos IDs alterados (para desfazer, se precisar): {caminho_aplicado}")
        else:
            console.print("\nCancelado: nada foi gravado.")
    elif args.aplicar:
        console.print("\nNada para gravar.")
    elif a_gravar:
        console.print(f"\nSimulação concluída: {len(a_gravar)} preço(s) seriam gravados. Se a lista 'VAI PREENCHER' estiver certa, rode de novo com --aplicar.")

    CAMINHO_RELATORIO.parent.mkdir(parents=True, exist_ok=True)
    console.save_text(str(CAMINHO_RELATORIO), clear=False)
    console.print(f"\nRelatório salvo em: {CAMINHO_RELATORIO}\nPlano (JSON) em: {CAMINHO_PLANO_JSON}")


if __name__ == "__main__":
    principal()
