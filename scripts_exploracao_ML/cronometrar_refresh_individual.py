# scripts_exploracao_ML/cronometrar_refresh_individual.py
#
# Objetivo: medir o tempo de UMA busca de mensagens ISOLADA (não em lote),
# simulando o que a tela precisaria fazer quando Ana abre o chat de 1 item
# que já está em "Em Acompanhamento" -- nesse caso não é preciso reconferir
# devolução nem reclassificar a combinação (já são sabidos, o item já está
# persistido), só buscar as mensagens atualizadas da reclamação.
#
# Por que isso é diferente da média já medida em
# buscar_mediacoes_abertas_recentes.py (~0,80s/item): aquela média vem de
# 141 chamadas em sequência rápida (mesmo respeitando o espaçador de 0,4s
# de chamar_api()) -- pode estar se beneficiando de reuso de conexão HTTP,
# token "quente", etc. Uma chamada avulsa, de verdade isolada (o padrão
# real: Ana abre 1 chat, faz outra coisa, abre outro chat minutos depois)
# pode ter uma latência bem diferente. Esse script cronometra SÓ essa
# chamada isolada, uma por vez, com uma pausa real entre elas.
#
# Amostra: pega uma quantidade pequena de reclamações abertas reais (MB +
# SV, mesma busca já validada de buscar_mediacoes_abertas_recentes.py) e,
# pra cada uma, espera PAUSA_ENTRE_CHAMADAS_SEGUNDOS antes de cronometrar
# SÓ a chamada de mensagens -- nunca em lote apertado. A busca da amostra
# em si NÃO é cronometrada, só serve pra achar claim_ids reais.
#
# Só leitura. Não toca no banco nem grava arquivo -- só imprime na tela.
#
# COMO USAR:
#   python scripts_exploracao_ML/cronometrar_refresh_individual.py

import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI
from api_mercado_livre.core.auth.gerenciador_token import FalhaAutenticacao

# ==== CONFIGURA AQUI ANTES DE RODAR ====
CONTAS = ["MB", "SV"]
MESES_ATRAS = 6                        # mesma janela usada pra achar candidatos reais
AMOSTRA_POR_CONTA = 5                  # quantas reclamações de cada conta entram no teste
PAUSA_ENTRE_CHAMADAS_SEGUNDOS = 5.0    # espera antes de CADA chamada isolada -- bem maior
                                        # que o espaçador interno de chamar_api() (0,4s),
                                        # de propósito: é o que separa "isolado" de "em lote"
LIMITE_POR_PAGINA = 100
MAX_PAGINAS = 10
# ========================================

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
NOME_LOG = "cronometrar_refresh_individual"
FUSO_HORARIO_EXIBICAO = ZoneInfo("America/Sao_Paulo")

console = Console()


def formatar_data_para_filtro(instante):
    texto = instante.isoformat(timespec="milliseconds")
    return texto[:-6] + texto[-6:].replace(":", "")


def buscar_user_id(conta):
    resposta = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG)
    return resposta.json()["id"]


def buscar_claims_abertas(conta, user_id, papel, inicio_formatado, fim_formatado):
    """Idêntica à versão já validada em buscar_mediacoes_abertas_recentes.py
    -- serve aqui só pra montar a amostra de claims reais pra testar, o
    resultado da busca em si não é cronometrado (só a busca de mensagens é)."""
    claims = []
    offset = 0
    for _ in range(MAX_PAGINAS):
        resposta = chamar_api(
            "GET", "/post-purchase/v1/claims/search",
            pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG,
            params={
                "players.user_id": user_id,
                "players.role": papel,
                "status": "opened",
                "range": f"date_created:after:{inicio_formatado},before:{fim_formatado}",
                "sort": "date_created:desc",
                "limit": LIMITE_POR_PAGINA,
                "offset": offset,
            },
        )
        pagina = resposta.json()
        dados = pagina.get("data", [])
        claims.extend(dados)
        total = (pagina.get("paging") or {}).get("total", 0)
        offset += LIMITE_POR_PAGINA
        if offset >= total or not dados:
            break
    return claims


def buscar_mensagens_da_reclamacao(conta, claim_id):
    """Idêntica à versão já validada em buscar_mediacoes_abertas_recentes.py.
    Retorna a lista de mensagens (bruta, como vem da API) ou None se não
    deu pra buscar -- erro aqui é sempre incerteza real, nunca '0 mensagens'."""
    try:
        resposta = chamar_api(
            "GET", f"/post-purchase/v1/claims/{claim_id}/messages",
            pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG,
        )
        return resposta.json()
    except (ErroAPI, ErroAutenticacaoAPI) as erro:
        console.print(f"  [dim yellow]Aviso: não deu pra buscar mensagens do claim {claim_id} ({escape(str(erro))})[/dim yellow]")
        return None


def montar_amostra():
    """Busca reclamações abertas reais nas 2 contas (mesma lógica já
    validada) e sorteia até AMOSTRA_POR_CONTA de cada uma -- só pra ter
    claim_ids reais pra cronometrar, sem cronometrar essa parte."""
    amostra = []
    agora = datetime.now(FUSO_HORARIO_EXIBICAO)
    inicio_formatado = formatar_data_para_filtro(agora - timedelta(days=MESES_ATRAS * 30))
    fim_formatado = formatar_data_para_filtro(agora)

    for conta in CONTAS:
        console.print(f"[bold]Conta {conta}[/bold] — buscando candidatas pra amostra...")
        try:
            user_id = buscar_user_id(conta)
            ids_ja_vistos = set()
            claims_da_conta = []
            for papel in ("respondent", "complainant"):
                for c in buscar_claims_abertas(conta, user_id, papel, inicio_formatado, fim_formatado):
                    claim_id = c.get("id")
                    if claim_id in ids_ja_vistos:
                        continue
                    ids_ja_vistos.add(claim_id)
                    claims_da_conta.append(claim_id)
        except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
            console.print(f"  [bold red]Erro:[/bold red] {escape(str(erro))}")
            continue

        if not claims_da_conta:
            console.print(f"  [yellow]Nenhuma reclamação aberta encontrada em {conta} -- fora da amostra.[/yellow]")
            continue

        sorteadas = random.sample(claims_da_conta, k=min(AMOSTRA_POR_CONTA, len(claims_da_conta)))
        console.print(f"  {len(claims_da_conta)} encontrada(s), {len(sorteadas)} sorteada(s) pra amostra.")
        for claim_id in sorteadas:
            amostra.append((conta, claim_id))

    random.shuffle(amostra)  # embaralha MB/SV -- só pra não agrupar tudo de uma conta seguido
    return amostra


def main():
    inicio_geral = time.monotonic()
    console.print("[bold]Cronometragem isolada do refresh de 1 chat[/bold]")
    console.print(f"Pausa entre cada chamada isolada: {PAUSA_ENTRE_CHAMADAS_SEGUNDOS:.1f}s "
                  f"(bem acima do espaçador interno de 0,4s usado no lote)\n")

    amostra = montar_amostra()

    if not amostra:
        console.print("\n[yellow]Nenhuma reclamação aberta encontrada em nenhuma das 2 contas -- nada pra cronometrar.[/yellow]")
        return

    console.print(f"\n[bold]Amostra final: {len(amostra)} reclamação(ões)[/bold] -- cronometrando 1 por vez, isoladas.\n")

    resultados = []
    nao_confirmadas = 0
    for indice, (conta, claim_id) in enumerate(amostra, start=1):
        console.print(f"[dim]({indice}/{len(amostra)}) esperando {PAUSA_ENTRE_CHAMADAS_SEGUNDOS:.1f}s "
                      f"antes de abrir o chat do claim {claim_id} ({conta})...[/dim]")
        time.sleep(PAUSA_ENTRE_CHAMADAS_SEGUNDOS)

        inicio = time.monotonic()
        mensagens = buscar_mensagens_da_reclamacao(conta, claim_id)
        tempo = time.monotonic() - inicio

        if mensagens is None:
            nao_confirmadas += 1
            console.print(f"  [yellow]-> erro após {tempo:.2f}s (não entra na média)[/yellow]")
        else:
            qtd = len(mensagens)
            console.print(f"  -> {tempo:.2f}s ({qtd} mensagem(ns))")
            resultados.append({"conta": conta, "claim_id": claim_id, "tempo": tempo, "qtd_mensagens": qtd})

    if not resultados:
        console.print("\n[bold red]Nenhuma chamada teve sucesso -- sem dado pra tabela.[/bold red]")
        return

    tabela = Table(title="Refresh isolado de 1 chat — tempo por chamada", box=box.SIMPLE)
    tabela.add_column("Ordem", justify="right")
    tabela.add_column("Conta")
    tabela.add_column("Claim ID")
    tabela.add_column("Qtd Mensagens", justify="right")
    tabela.add_column("Tempo (s)", justify="right")
    for indice, r in enumerate(resultados, start=1):
        tabela.add_row(str(indice), r["conta"], str(r["claim_id"]), str(r["qtd_mensagens"]), f"{r['tempo']:.2f}")
    console.print()
    console.print(tabela)

    tempos = [r["tempo"] for r in resultados]
    tabela_resumo = Table(title="Resumo", box=box.SIMPLE)
    tabela_resumo.add_column("Métrica")
    tabela_resumo.add_column("Valor", justify="right")
    tabela_resumo.add_row("Chamadas com sucesso", str(len(resultados)))
    tabela_resumo.add_row("Mínimo (s)", f"{min(tempos):.2f}")
    tabela_resumo.add_row("Máximo (s)", f"{max(tempos):.2f}")
    tabela_resumo.add_row("Média (s)", f"{sum(tempos) / len(tempos):.2f}")
    if nao_confirmadas:
        tabela_resumo.add_row("Erros (não entraram na média)", str(nao_confirmadas))
    console.print()
    console.print(tabela_resumo)

    for conta in CONTAS:
        tempos_conta = [r["tempo"] for r in resultados if r["conta"] == conta]
        if tempos_conta:
            console.print(f"\n[dim]{conta}: {len(tempos_conta)} chamada(s), "
                          f"média {sum(tempos_conta) / len(tempos_conta):.2f}s, "
                          f"mín {min(tempos_conta):.2f}s, máx {max(tempos_conta):.2f}s[/dim]")

    console.print(f"\n[dim]Tempo total do script (incluindo as pausas de {PAUSA_ENTRE_CHAMADAS_SEGUNDOS:.1f}s): "
                  f"{time.monotonic() - inicio_geral:.2f}s[/dim]")


if __name__ == "__main__":
    try:
        main()
    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        console.print(f"[bold red]Erro ao chamar a API:[/bold red] {escape(str(erro))}")
        sys.exit(1)