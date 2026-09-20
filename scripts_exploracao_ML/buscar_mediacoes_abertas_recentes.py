# scripts_exploracao_ML/buscar_mediacoes_abertas_recentes.py
#
# Objetivo: listar reclamações ABERTAS (status=opened) das 2 contas
# (MB e SV) via GET /post-purchase/v1/claims/search, restrito aos últimos
# MESES_ATRAS meses -- sem precisar saber nenhum pedido de antemão.
#
# Busca nos 2 papéis (respondent E complainant) -- não só respondent --
# porque reclamações do tipo cancel_sale podem inverter esses papéis
# (achado do vault: "Tipo cancel_sale Fecha Com Resolution Null E
# Inverte Complainant E Respondent").
#
# EXTENSÃO (pedido de Matheus, 20/09/2026): pra cada reclamação
# encontrada, também chama GET /post-purchase/v2/claims/$ID/returns pra
# saber se ela tem devolução física associada -- e classifica cada uma
# em 1 das 4 combinações possíveis de 2 fatos binários independentes
# ("está em mediação" = stage == dispute; "tem devolução física" =
# /returns responde com sucesso, sem 404):
#
#   Reclamação                          -- não é mediação, sem devolução
#   Reclamação + Mediação               -- é mediação, sem devolução
#   Reclamação + Devolução              -- não é mediação, com devolução
#   Reclamação + Mediação + Devolução   -- é mediação, com devolução
#
# "type" (mediations/return/etc.) NÃO decide nada aqui de propósito --
# achado confirmado (vault + código já existente do projeto): o campo
# que diz se virou mediação de verdade é "stage" (dispute), não "type".
# "type" continua sendo mostrado na tabela só como referência/contexto.
#
# Faz o dobro de chamadas à API da versão anterior (1 /returns a mais
# por reclamação já encontrada) -- ainda seguro graças ao espaçador
# proativo já embutido em chamar_api() (protecao.py, 0,4s por conta).
#
# Só leitura. Não toca no banco nem grava arquivo -- só imprime na tela.
#
# COMO USAR:
#   python scripts_exploracao_ML/buscar_mediacoes_abertas_recentes.py

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.progress import track
from rich.table import Table

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI
from api_mercado_livre.core.auth.gerenciador_token import FalhaAutenticacao

# ==== CONFIGURA AQUI ANTES DE RODAR ====
CONTAS = ["MB", "SV"]
MESES_ATRAS = 6
LIMITE_POR_PAGINA = 100   # máximo aceito pela API (confirmado em buscar_reclamacoes_candidatas.py)
MAX_PAGINAS = 10          # teto de segurança por conta/papel — 10 x 100 = 1000, bem acima do esperado pra "opened"
# ========================================

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
NOME_LOG = "buscar_mediacoes_abertas_recentes"
FUSO_HORARIO_EXIBICAO = ZoneInfo("America/Sao_Paulo")

console = Console()

TRADUCAO_TIPO = {
    "mediations": "mediations",
    "return": "return",
    "returns": "returns",
    "fulfillment": "fulfillment",
    "cancel_sale": "cancel_sale",
    "cancel_purchase": "cancel_purchase",
    "change": "change",
    "service": "service",
    "ml_case": "ml_case",
}


def formatar_data_para_filtro(instante):
    texto = instante.isoformat(timespec="milliseconds")
    return texto[:-6] + texto[-6:].replace(":", "")


def formatar_data_exibicao(valor_iso):
    if not valor_iso:
        return "—"
    try:
        instante = datetime.fromisoformat(valor_iso)
    except ValueError:
        return valor_iso
    instante = instante.astimezone(FUSO_HORARIO_EXIBICAO)
    return instante.strftime("%d/%m/%Y %H:%M")


def buscar_user_id(conta):
    resposta = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG)
    return resposta.json()["id"]


def buscar_claims_abertas(conta, user_id, papel, inicio_formatado, fim_formatado):
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


def tem_devolucao_fisica(conta, claim_id):
    """True/False = confirmado via /returns. None = não deu pra confirmar
    (erro que não foi um 404 limpo) -- tratado como 'sem devolução' na
    classificação final, mas contado à parte pra não mascarar o erro."""
    try:
        chamar_api(
            "GET", f"/post-purchase/v2/claims/{claim_id}/returns",
            pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG,
        )
        return True
    except ErroAPI as erro:
        if str(erro).startswith("Erro 404 "):
            return False
        console.print(f"  [dim yellow]Aviso: não deu pra confirmar devolução do claim {claim_id} ({escape(str(erro))})[/dim yellow]")
        return None
    except ErroAutenticacaoAPI as erro:
        console.print(f"  [dim yellow]Aviso: não deu pra confirmar devolução do claim {claim_id} ({escape(str(erro))})[/dim yellow]")
        return None


def classificar(stage, tem_devolucao):
    """
    tem_devolucao vem de tem_devolucao_fisica() e pode ser True (confirmado
    via /returns), False (confirmado sem devolução, 404) ou None (não deu
    pra confirmar -- ex: erro que não foi um 404 limpo, esgotou tentativas).

    None NUNCA é tratado como equivalente a False aqui -- isso mascararia
    um erro de API como se fosse uma reclamação confirmada sem devolução.
    Quando não verificado, a combinação recebe o sufixo "(devolução não
    verificada)" em vez de cair automaticamente no "sem devolução".
    """
    eh_mediacao = stage == "dispute"

    if tem_devolucao is None:
        base = "Reclamação + Mediação" if eh_mediacao else "Reclamação"
        return base + " (devolução não verificada)"

    if eh_mediacao and tem_devolucao:
        return "Reclamação + Mediação + Devolução"
    if eh_mediacao:
        return "Reclamação + Mediação"
    if tem_devolucao:
        return "Reclamação + Devolução"
    return "Reclamação"


def main():
    agora = datetime.now(FUSO_HORARIO_EXIBICAO)
    inicio_formatado = formatar_data_para_filtro(agora - timedelta(days=MESES_ATRAS * 30))
    fim_formatado = formatar_data_para_filtro(agora)

    todas = []
    ids_ja_vistos = set()

    for conta in CONTAS:
        console.print(f"[bold]Conta {conta}[/bold] — buscando reclamações abertas dos últimos {MESES_ATRAS} meses...")
        try:
            user_id = buscar_user_id(conta)
            claims_da_conta = []
            for papel in ("respondent", "complainant"):
                claims_da_conta += buscar_claims_abertas(conta, user_id, papel, inicio_formatado, fim_formatado)
        except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
            console.print(f"  [bold red]Erro:[/bold red] {escape(str(erro))}")
            continue

        novas = 0
        for c in claims_da_conta:
            if c.get("id") in ids_ja_vistos:
                continue
            ids_ja_vistos.add(c.get("id"))
            novas += 1
            todas.append({
                "conta": conta,
                "claim_id": c.get("id"),
                "pedido": c.get("resource_id"),
                "tipo": TRADUCAO_TIPO.get(c.get("type"), c.get("type")),
                "stage": c.get("stage"),
                "data_abertura": c.get("date_created"),
            })
        console.print(f"  {novas} reclamação(ões) aberta(s) encontrada(s).")

    if not todas:
        console.print("\nNenhuma reclamação aberta encontrada nas 2 contas, no período.")
        return

    console.print()
    nao_verificados = 0
    for item in track(todas, description="Verificando devolução física de cada uma..."):
        resultado = tem_devolucao_fisica(item["conta"], item["claim_id"])
        item["tem_devolucao"] = resultado
        if resultado is None:
            nao_verificados += 1
        item["combinacao"] = classificar(item["stage"], resultado)

    tabela = Table(title=f"Reclamações abertas — últimos {MESES_ATRAS} meses", box=box.SIMPLE)
    tabela.add_column("Conta")
    tabela.add_column("Pedido")
    tabela.add_column("Claim ID")
    tabela.add_column("Type (bruto)")
    tabela.add_column("Stage")
    tabela.add_column("Devolução?")
    tabela.add_column("Combinação")
    tabela.add_column("Aberta em")
    for item in sorted(todas, key=lambda x: x["data_abertura"] or "", reverse=True):
        devolucao_txt = "sim" if item["tem_devolucao"] else ("não confirmado" if item["tem_devolucao"] is None else "não")
        tabela.add_row(
            item["conta"], str(item["pedido"]), str(item["claim_id"]),
            item["tipo"], item["stage"] or "—", devolucao_txt, item["combinacao"],
            formatar_data_exibicao(item["data_abertura"]),
        )
    console.print()
    console.print(tabela)

    contagem = {}
    for item in todas:
        contagem[item["combinacao"]] = contagem.get(item["combinacao"], 0) + 1

    ordem = [
        "Reclamação",
        "Reclamação + Mediação",
        "Reclamação + Devolução",
        "Reclamação + Mediação + Devolução",
    ]
    tabela_resumo = Table(title="Resumo por combinação", box=box.SIMPLE)
    tabela_resumo.add_column("Combinação")
    tabela_resumo.add_column("Quantidade", justify="right")
    for chave in ordem:
        tabela_resumo.add_row(chave, str(contagem.get(chave, 0)))
    tabela_resumo.add_row("[bold]TOTAL[/bold]", f"[bold]{len(todas)}[/bold]")

    console.print()
    console.print(tabela_resumo)
    if nao_verificados:
        console.print(f"\n[dim yellow]{nao_verificados} reclamação(ões) não tiveram a devolução confirmada por erro na API — "
                      f"contadas acima como 'sem devolução' (ver avisos durante a execução).[/dim yellow]")


if __name__ == "__main__":
    try:
        main()
    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        console.print(f"[bold red]Erro ao chamar a API:[/bold red] {escape(str(erro))}")
        sys.exit(1)