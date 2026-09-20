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
# EXTENSÃO 2 (pedido de Matheus, 20/09/2026): pra cada reclamação, também
# busca GET /post-purchase/v1/claims/$ID/messages e classifica cada
# mensagem em ML / Você / Cliente -- MESMA lógica já validada em produção
# (views.py::_construir_mensagens_mediacao) e no rascunho
# varredura_respostas_mediacao.py:
#   sender_role == "mediator"                  -> ML
#   sender_role == papel desta conta no claim   -> Você (nosso lado)
#   qualquer outro                              -> Cliente (contraparte)
# O papel desta conta no claim (respondent/complainant) já é conhecido
# desde a busca inicial (foi filtrado por players.role) -- não precisa de
# nenhuma chamada extra a /claims/$ID só pra descobrir isso.
#
# Faz mais 1 chamada à API por reclamação (agora até 3x a base: search +
# /returns + /messages) -- ainda protegido pelo mesmo espaçador de
# chamar_api(), mas o tempo total do script deve crescer bastante -- é
# justamente o que essa cronometragem serve pra medir.
#
# Só leitura. Não toca no banco nem grava arquivo -- só imprime na tela.
#
# COMO USAR:
#   python scripts_exploracao_ML/buscar_mediacoes_abertas_recentes.py

import sys
import time
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


def buscar_mensagens_da_reclamacao(conta, claim_id):
    """Retorna a lista de mensagens (bruta, como vem da API) ou None se não
    deu pra buscar. Aqui não existe 'vazio esperado' via 404 como em
    tem_devolucao_fisica() -- uma reclamação sem mensagem nenhuma ainda
    retorna 200 com lista vazia, então qualquer erro aqui é sempre
    incerteza real, nunca deve ser tratado como '0 mensagens'."""
    try:
        resposta = chamar_api(
            "GET", f"/post-purchase/v1/claims/{claim_id}/messages",
            pasta_logs=PASTA_LOGS, conta=conta, nome_log=NOME_LOG,
        )
        return resposta.json()
    except (ErroAPI, ErroAutenticacaoAPI) as erro:
        console.print(f"  [dim yellow]Aviso: não deu pra buscar mensagens do claim {claim_id} ({escape(str(erro))})[/dim yellow]")
        return None


def classificar_mensagens(mensagens, meu_papel):
    """Classifica cada mensagem em quem mandou -- MESMA lógica já validada
    em produção (views.py::_construir_mensagens_mediacao) e no rascunho
    varredura_respostas_mediacao.py:
      sender_role == "mediator"                   -> ML
      sender_role == meu_papel (nessa reclamação)  -> Você (nosso lado)
      qualquer outro                               -> Cliente (contraparte)
    meu_papel vem de qual busca (players.role=respondent OU
    players.role=complainant) encontrou essa reclamação -- não precisa de
    chamada extra pra descobrir, o papel já é conhecido desde a busca."""
    contagem = {"ml": 0, "voce": 0, "cliente": 0}
    for m in mensagens:
        sender = m.get("sender_role")
        if sender == "mediator":
            contagem["ml"] += 1
        elif meu_papel is not None and sender == meu_papel:
            contagem["voce"] += 1
        else:
            contagem["cliente"] += 1
    return contagem


def main():
    inicio_geral = time.monotonic()
    agora = datetime.now(FUSO_HORARIO_EXIBICAO)
    inicio_formatado = formatar_data_para_filtro(agora - timedelta(days=MESES_ATRAS * 30))
    fim_formatado = formatar_data_para_filtro(agora)

    todas = []
    ids_ja_vistos = set()
    tempo_busca_por_conta = {}

    for conta in CONTAS:
        console.print(f"[bold]Conta {conta}[/bold] — buscando reclamações abertas dos últimos {MESES_ATRAS} meses...")
        inicio_busca_conta = time.monotonic()
        try:
            user_id = buscar_user_id(conta)
            claims_da_conta = []
            for papel in ("respondent", "complainant"):
                for c in buscar_claims_abertas(conta, user_id, papel, inicio_formatado, fim_formatado):
                    claims_da_conta.append((c, papel))
        except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
            console.print(f"  [bold red]Erro:[/bold red] {escape(str(erro))}")
            continue
        tempo_busca_por_conta[conta] = time.monotonic() - inicio_busca_conta

        novas = 0
        for c, papel_encontrado in claims_da_conta:
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
                # meu_papel vem de qual busca achou essa reclamação
                # (players.role=respondent OU players.role=complainant) --
                # já sabido com certeza, sem precisar de chamada extra a
                # /claims/$ID só pra descobrir o papel (usado por
                # classificar_mensagens() mais abaixo).
                "meu_papel": papel_encontrado,
            })
        console.print(f"  {novas} reclamação(ões) aberta(s) encontrada(s).")

    if not todas:
        console.print("\nNenhuma reclamação aberta encontrada nas 2 contas, no período.")
        console.print(f"[dim]Tempo total do script: {time.monotonic() - inicio_geral:.2f}s[/dim]")
        return

    console.print()
    nao_verificados = 0
    tempo_verificacao_por_conta = {}
    for item in track(todas, description="Verificando devolução física de cada uma..."):
        inicio_item = time.monotonic()
        resultado = tem_devolucao_fisica(item["conta"], item["claim_id"])
        item["tempo_verificacao"] = time.monotonic() - inicio_item
        tempo_verificacao_por_conta[item["conta"]] = tempo_verificacao_por_conta.get(item["conta"], 0.0) + item["tempo_verificacao"]
        item["tem_devolucao"] = resultado
        if resultado is None:
            nao_verificados += 1
        item["combinacao"] = classificar(item["stage"], resultado)

    console.print()
    nao_verificadas_msgs = 0
    tempo_busca_msgs_por_conta = {}
    tempo_classificacao_msgs_por_conta = {}
    total_msgs_ml = 0
    total_msgs_voce = 0
    total_msgs_cliente = 0
    for item in track(todas, description="Buscando e classificando mensagens de cada uma..."):
        inicio_busca_msg = time.monotonic()
        mensagens = buscar_mensagens_da_reclamacao(item["conta"], item["claim_id"])
        item["tempo_busca_mensagens"] = time.monotonic() - inicio_busca_msg
        tempo_busca_msgs_por_conta[item["conta"]] = tempo_busca_msgs_por_conta.get(item["conta"], 0.0) + item["tempo_busca_mensagens"]

        inicio_classificacao_msg = time.monotonic()
        if mensagens is None:
            item["qtd_mensagens"] = None
            item["msgs_ml"] = None
            item["msgs_voce"] = None
            item["msgs_cliente"] = None
            nao_verificadas_msgs += 1
        else:
            contagem_msgs = classificar_mensagens(mensagens, item["meu_papel"])
            item["qtd_mensagens"] = len(mensagens)
            item["msgs_ml"] = contagem_msgs["ml"]
            item["msgs_voce"] = contagem_msgs["voce"]
            item["msgs_cliente"] = contagem_msgs["cliente"]
            total_msgs_ml += contagem_msgs["ml"]
            total_msgs_voce += contagem_msgs["voce"]
            total_msgs_cliente += contagem_msgs["cliente"]
        item["tempo_classificacao_mensagens"] = time.monotonic() - inicio_classificacao_msg
        tempo_classificacao_msgs_por_conta[item["conta"]] = tempo_classificacao_msgs_por_conta.get(item["conta"], 0.0) + item["tempo_classificacao_mensagens"]

    tabela = Table(title=f"Reclamações abertas — últimos {MESES_ATRAS} meses", box=box.SIMPLE)
    tabela.add_column("Conta")
    tabela.add_column("Pedido")
    tabela.add_column("Claim ID")
    tabela.add_column("Type (bruto)")
    tabela.add_column("Stage")
    tabela.add_column("Devolução?")
    tabela.add_column("Combinação")
    tabela.add_column("Aberta em")
    tabela.add_column("Tempo Devolução (s)", justify="right")
    for item in sorted(todas, key=lambda x: x["data_abertura"] or "", reverse=True):
        devolucao_txt = "sim" if item["tem_devolucao"] else ("não confirmado" if item["tem_devolucao"] is None else "não")
        tabela.add_row(
            item["conta"], str(item["pedido"]), str(item["claim_id"]),
            item["tipo"], item["stage"] or "—", devolucao_txt, item["combinacao"],
            formatar_data_exibicao(item["data_abertura"]), f"{item['tempo_verificacao']:.2f}",
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
    # classificar() pode gerar combinações fora das 4 esperadas (variantes
    # "(devolução não verificada)", quando tem_devolucao_fisica() não
    # conseguiu confirmar) -- nunca deixar essas caírem fora da tabela-resumo
    # silenciosamente, senão a soma das linhas visíveis não bate com o TOTAL
    # sem nenhuma explicação.
    extras = sorted(chave for chave in contagem if chave not in ordem)
    for chave in extras:
        tabela_resumo.add_row(chave, str(contagem.get(chave, 0)))
    tabela_resumo.add_row("[bold]TOTAL[/bold]", f"[bold]{len(todas)}[/bold]")

    console.print()
    console.print(tabela_resumo)
    if nao_verificados:
        console.print(f"\n[dim yellow]{nao_verificados} reclamação(ões) não tiveram a devolução confirmada por erro na API — "
                      f"aparecem acima com o sufixo '(devolução não verificada)' na combinação, e NÃO foram contadas "
                      f"como 'sem devolução' (ver avisos durante a execução).[/dim yellow]")

    tabela_mensagens = Table(title="Mensagens por reclamação — quem é quem", box=box.SIMPLE)
    tabela_mensagens.add_column("Conta")
    tabela_mensagens.add_column("Claim ID")
    tabela_mensagens.add_column("Qtd Mensagens", justify="right")
    tabela_mensagens.add_column("ML", justify="right")
    tabela_mensagens.add_column("Você", justify="right")
    tabela_mensagens.add_column("Cliente", justify="right")
    tabela_mensagens.add_column("Tempo Busca (s)", justify="right")
    tabela_mensagens.add_column("Tempo Classif. (s)", justify="right")
    for item in sorted(todas, key=lambda x: x["data_abertura"] or "", reverse=True):
        qtd_txt = "não confirmado" if item["qtd_mensagens"] is None else str(item["qtd_mensagens"])
        ml_txt = "—" if item["msgs_ml"] is None else str(item["msgs_ml"])
        voce_txt = "—" if item["msgs_voce"] is None else str(item["msgs_voce"])
        cliente_txt = "—" if item["msgs_cliente"] is None else str(item["msgs_cliente"])
        tabela_mensagens.add_row(
            item["conta"], str(item["claim_id"]), qtd_txt, ml_txt, voce_txt, cliente_txt,
            f"{item['tempo_busca_mensagens']:.2f}", f"{item['tempo_classificacao_mensagens']:.2f}",
        )
    console.print()
    console.print(tabela_mensagens)
    if nao_verificadas_msgs:
        console.print(f"\n[dim yellow]{nao_verificadas_msgs} reclamação(ões) não tiveram as mensagens confirmadas por erro na API — "
                      f"aparecem acima como 'não confirmado' (ver avisos durante a execução).[/dim yellow]")

    tabela_resumo_msgs = Table(title="Resumo de mensagens — quem é quem", box=box.SIMPLE)
    tabela_resumo_msgs.add_column("Categoria")
    tabela_resumo_msgs.add_column("Quantidade", justify="right")
    tabela_resumo_msgs.add_row("Mensagens do Mercado Livre (mediador)", str(total_msgs_ml))
    tabela_resumo_msgs.add_row("Mensagens suas (vendedor)", str(total_msgs_voce))
    tabela_resumo_msgs.add_row("Mensagens do cliente", str(total_msgs_cliente))
    tabela_resumo_msgs.add_row("[bold]TOTAL[/bold]", f"[bold]{total_msgs_ml + total_msgs_voce + total_msgs_cliente}[/bold]")
    console.print()
    console.print(tabela_resumo_msgs)

    tabela_tempo = Table(title="Tempo gasto por conta", box=box.SIMPLE)
    tabela_tempo.add_column("Conta")
    tabela_tempo.add_column("Busca de reclamações (s)", justify="right")
    tabela_tempo.add_column("Verificação de devolução (s)", justify="right")
    tabela_tempo.add_column("Busca de mensagens (s)", justify="right")
    tabela_tempo.add_column("Classificação de mensagens (s)", justify="right")
    tabela_tempo.add_column("Total da conta (s)", justify="right")
    for conta in CONTAS:
        tempo_busca = tempo_busca_por_conta.get(conta, 0.0)
        tempo_verificacao = tempo_verificacao_por_conta.get(conta, 0.0)
        tempo_busca_msgs = tempo_busca_msgs_por_conta.get(conta, 0.0)
        tempo_classificacao_msgs = tempo_classificacao_msgs_por_conta.get(conta, 0.0)
        total_conta = tempo_busca + tempo_verificacao + tempo_busca_msgs + tempo_classificacao_msgs
        tabela_tempo.add_row(
            conta, f"{tempo_busca:.2f}", f"{tempo_verificacao:.2f}",
            f"{tempo_busca_msgs:.2f}", f"{tempo_classificacao_msgs:.2f}", f"{total_conta:.2f}",
        )

    console.print()
    console.print(tabela_tempo)
    console.print(f"\n[bold]Tempo total do script:[/bold] {time.monotonic() - inicio_geral:.2f}s")


if __name__ == "__main__":
    try:
        main()
    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        console.print(f"[bold red]Erro ao chamar a API:[/bold red] {escape(str(erro))}")
        sys.exit(1)