# scripts_exploracao_ML/testar_visoes_prontas_analise.py
#
# Função Objetivo: Descobrir, com dado REAL (os 2 bancos, MB e SV), quantos casos cada "visão pronta"
# da tela Análise pegaria hoje — ANTES de desenhar qualquer tela. Cada visão é uma pergunta que a Ana
# provavelmente faz ao abrir a Análise:
#
#   1. Esperando conferência há mais tempo        (o que chegou e ainda não conferi, e há quantos dias?)
#   2. Mediações para eu agir                     (prazo vencendo ou mensagem nova do ML)
#   3. Conferidas com problema e sem mediação     (dinheiro que pode estar ficando na mesa)
#   4. Encerradas com a conta incompleta          (falta preencher reembolso, valor ou preço)
#   5. Dinheiro em jogo e dinheiro recuperado     (R$ nas mediações abertas; taxa de reembolso nas decididas)
#   6. Resultado por mês                          (quantas, destino, reembolsadas, R$)
#   7. Prontas para imprimir
#
# Além das visões, o relatório mostra:
#   - QUALIDADE DOS DADOS: quanto de cada campo está realmente preenchido. Uma visão que depende de um
#     campo quase sempre vazio (ex.: "prazo de resposta", que é digitado à mão) não serve, por melhor
#     que seja a ideia.
#   - CALIBRAGEM da visão 3: de todos os casos já conferidos COM evidência de problema, quantos
#     acabaram em mediação? Se a Ana medeia quase todos, um caso conferido-com-problema-sem-mediação é
#     esquecimento. Se medeia poucos, é só uma decisão dela e a visão vira ruído.
#   - CONCENTRAÇÃO por marca e por produto: ajuda a decidir se "agrupar por marca/produto" vale a pena
#     ou se a lista ordenada já basta.
#
# Só leitura: SELECT no banco. NÃO chama a API do Mercado Livre e NÃO grava nada (nem no banco, nem
# no sistema). As regras abaixo são as MESMAS que as telas Devoluções/Análise já usam
# (Devolucao.status_fluxo, tem_evidencia_mediacao e mensagem_nao_lida em devolucoes/views.py,
# status_prazo_resposta e reclamacao_dentro_do_prazo no model), pra o número do script ser o número
# que a tela mostraria.
#
# * [EXPLICAÇÃO] → "dias na etapa": só existe data para 3 etapas (Aguardando = recebido por nós,
#   Mediação Aberta = abertura, Mediação Encerrada = encerramento). Para "Conferidos" NÃO existe data
#   de conferência no banco: o script usa o cadastro como aproximação e avisa no relatório.
#
# Rodar da raiz do projeto, com o ambiente virtual ativo:
#   python scripts_exploracao_ML/testar_visoes_prontas_analise.py
#   python scripts_exploracao_ML/testar_visoes_prontas_analise.py --conta SV
#   python scripts_exploracao_ML/testar_visoes_prontas_analise.py --detalhes 15       (mais linhas nas listas)
#   python scripts_exploracao_ML/testar_visoes_prontas_analise.py --hoje 2026-10-04   (simula outra data de referência)
#
# Saídas:
#   scripts_exploracao_ML/logs/testar_visoes_prontas_analise_relatorio.txt   (o que aparece na tela)
#   scripts_exploracao_ML/testar_visoes_prontas_analise.json                 (todos os casos de cada visão)

import argparse
import json
import os
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
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

from django.utils import timezone  # noqa: E402

from devolucoes.models import ClaimMercadoLivre, ConferenciaPeca, Devolucao, FotoObservacaoGeral  # noqa: E402

# ==== CONFIGURA AQUI ANTES DE RODAR ====
# Um caso "parado" a partir de quantos dias? (usado só pra contar nas visões 1 e 2)
DIAS_PARADO = 7
# Faixas de "dias esperando" mostradas na visão 1 (limite superior de cada faixa; a última é aberta).
FAIXAS_DIAS = [2, 7, 14, 30]
# Quantas marcas / produtos mostrar na tabela de concentração.
TOPO_CONCENTRACAO = 8
# ========================================

BANCOS = [("MB", "magazine"), ("SV", "samvale")]
PASTA_DO_SCRIPT = Path(__file__).resolve().parent
CAMINHO_RELATORIO = PASTA_DO_SCRIPT / "logs" / "testar_visoes_prontas_analise_relatorio.txt"
CAMINHO_JSON = PASTA_DO_SCRIPT / "testar_visoes_prontas_analise.json"

ETAPA_AGUARDANDO = Devolucao.STATUS_AGUARDANDO_CONFERENCIA
ETAPA_CONFERIDO = Devolucao.STATUS_CONFERIDO
ETAPA_ABERTA = Devolucao.STATUS_MEDIACAO_ABERTA
ETAPA_ENCERRADA = Devolucao.STATUS_MEDIACAO_ENCERRADA
ETAPA_IMPRESSO = Devolucao.STATUS_IMPRESSO
NOME_DA_ETAPA = dict(Devolucao.STATUS_CHOICES)

try:  # Windows: garante acento no terminal e no arquivo
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

console = Console(record=True, width=max(shutil.get_terminal_size((130, 40)).columns, 130))


# ─────────────────────────── Funções de apoio ───────────────────────────

def _dia_local(valor):
    # data-e-hora -> dia no fuso de São Paulo (mesma regra da tela: _dia_do_calendario em views.py)
    if valor is None:
        return None
    if isinstance(valor, datetime):
        if timezone.is_naive(valor):
            valor = timezone.make_aware(valor)
        return timezone.localtime(valor).date()
    return valor


def brl(valor):
    if valor is None:
        return "—"
    texto = f"{Decimal(valor):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def fracao(parte, total):
    if not total:
        return "—"
    return f"{parte} de {total} ({round(100 * parte / total)}%)"


def curto(texto, limite):
    texto = (texto or "").strip()
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def dmy(valor):
    return valor.strftime("%d/%m/%y") if valor else "—"


def soma(lista, campo):
    total = Decimal("0")
    for caso in lista:
        if caso[campo] is not None:
            total += caso[campo]
    return total


# ─────────────────────────── Leitura do banco ───────────────────────────

def carregar_casos(conta, alias, hoje):
    """1 dicionário por devolução, já com tudo que as visões precisam. Só SELECT."""
    devolucoes = list(Devolucao.objects.using(alias).select_related("produto__marca").order_by("criado_em"))

    pecas_por_devolucao = defaultdict(list)
    for peca in ConferenciaPeca.objects.using(alias).only(
        "devolucao_id", "quantidade_recebida", "quantidade_esperada", "anotacao"
    ):
        pecas_por_devolucao[peca.devolucao_id].append(peca)

    ids_com_foto_observacao = set(
        FotoObservacaoGeral.objects.using(alias).values_list("devolucao_id", flat=True).distinct()
    )

    ids_de_claim = [d.claim_id for d in devolucoes if d.claim_id]
    claims = {c.claim_id: c for c in ClaimMercadoLivre.objects.using(alias).filter(claim_id__in=ids_de_claim)}

    return [
        montar_caso(conta, d, pecas_por_devolucao.get(d.id, []), d.id in ids_com_foto_observacao,
                    claims.get(d.claim_id), hoje)
        for d in devolucoes
    ]


def montar_caso(conta, d, pecas, tem_foto_observacao, claim, hoje):
    etapa = d.status_fluxo
    produto = d.produto
    criado = _dia_local(d.criado_em)
    recebido = d.data_recebimento_por_nos
    abertura = d.data_abertura_mediacao
    fim = d.data_finalizacao_mediacao
    impresso = _dia_local(d.relatorio_impresso_em)
    prazo = d.prazo_resposta

    # Evidência de problema — MESMA regra de devolucoes_pendentes (views.py): peça com problema, foto de
    # observação geral ou observação geral em texto.
    pecas_com_problema = sum(1 for p in pecas if p.eh_evidencia_de_problema)
    evidencia = bool(pecas_com_problema or tem_foto_observacao or d.observacao_geral)

    # Reclamação dentro/fora dos 7 dias — mesma conta do model (dias_ate_reclamacao).
    dias_ate_reclamacao = d.dias_ate_reclamacao
    if dias_ate_reclamacao is None:
        rec7 = None
    else:
        rec7 = "dentro" if dias_ate_reclamacao <= 7 else "fora"

    # Prazo de resposta — mesma regra de status_prazo_resposta, só que contando a partir da data de
    # referência do script (--hoje) em vez de date.today().
    if prazo is None:
        dias_ate_prazo, status_prazo = None, None
    else:
        dias_ate_prazo = (prazo - hoje).days
        if dias_ate_prazo < 0:
            status_prazo = "vencido"
        elif dias_ate_prazo == 0:
            status_prazo = "hoje"
        elif dias_ate_prazo <= 2:
            status_prazo = "proximo"
        else:
            status_prazo = "ok"

    # Mensagem nova — mesma regra da lista Devoluções (mensagem_nao_lida) / tela Mediações ML.
    msg_nova = bool(
        etapa == ETAPA_ABERTA and claim and claim.ultima_mensagem_de and claim.ultima_mensagem_de != "voce"
        and (
            not d.mediacao_visualizada_em
            or (claim.ultima_mensagem_em and claim.ultima_mensagem_em > d.mediacao_visualizada_em)
        )
    )

    # Dias na etapa (ver nota no cabeçalho: "Conferidos" usa o cadastro como aproximação).
    if etapa == ETAPA_AGUARDANDO:
        base_da_etapa = recebido or criado
    elif etapa == ETAPA_CONFERIDO:
        base_da_etapa = criado
    elif etapa == ETAPA_ABERTA:
        base_da_etapa = abertura
    elif etapa == ETAPA_ENCERRADA:
        base_da_etapa = fim
    else:
        base_da_etapa = None

    decidida = fim is not None  # mediação com data de encerramento
    teve_mediacao = abertura is not None

    # O que falta preencher para a conta fechar (só faz sentido em mediação já decidida).
    falta = []
    if decidida:
        if d.reembolsado is None:
            falta.append("reembolsado? (sim/não)")
        elif d.reembolsado and d.valor_reembolsado is None:
            falta.append("valor reembolsado")
        if d.preco_produto is None:
            falta.append("preço do produto")

    return {
        "conta": conta,
        "id": d.id,
        "pedido": d.numero_pedido,
        "cliente": d.nome_cliente,
        "produto": produto.nome,
        "marca": produto.marca.nome,
        "plataforma": d.nome_plataforma,
        "tipo_venda": d.tipo_venda,
        "etapa": etapa,
        "destino": d.destino_produto or "",
        "criado": criado,
        "recebido_por_nos": recebido,
        "abertura": abertura,
        "fim": fim,
        "impresso": impresso,
        "prazo": prazo,
        "status_prazo": status_prazo,
        "dias_ate_prazo": dias_ate_prazo,
        "msg_nova": msg_nova,
        "claim_id": d.claim_id or "",
        "mediacao_atualizada_em": _dia_local(d.mediacao_atualizada_em),
        "evidencia": evidencia,
        "pecas_com_problema": pecas_com_problema,
        "rec7": rec7,
        "dias_ate_reclamacao": dias_ate_reclamacao,
        "teve_mediacao": teve_mediacao,
        "decidida": decidida,
        "reembolsado": d.reembolsado,
        "preco": d.preco_produto,
        "valor": d.valor_reembolsado,
        "diferenca": d.diferenca_reembolso,
        "anotacao_mediacao": bool(d.anotacao_mediacao),
        "dias_na_etapa": (hoje - base_da_etapa).days if base_da_etapa else None,
        "dias_desde_recebimento": (hoje - recebido).days if recebido else None,
        "dias_desde_cadastro": (hoje - criado).days if criado else None,
        "dias_desde_abertura": (hoje - abertura).days if abertura else None,
        "falta_na_conta": falta,
    }


# ─────────────────────────── Saída na tela ───────────────────────────

def mostrar_tabela(titulo, colunas, linhas, direita=()):
    tabela = Table(title=titulo, box=box.SIMPLE_HEAVY, title_justify="left", show_lines=False)
    for indice, nome in enumerate(colunas):
        tabela.add_column(nome, justify="right" if indice in direita else "left", overflow="fold")
    for linha in linhas:
        tabela.add_row(*[str(c) for c in linha])
    console.print(tabela)


def por_empresa(contas, todos, definicoes, titulo, primeira_coluna="Pergunta"):
    """Tabela com 1 coluna por empresa + Total. definicoes = [(rótulo, função(lista_de_casos) -> texto)]."""
    colunas = [primeira_coluna, *contas] + (["Total"] if len(contas) > 1 else [])
    linhas = []
    for rotulo, funcao in definicoes:
        linha = [rotulo]
        for conta in contas:
            linha.append(funcao([c for c in todos if c["conta"] == conta]))
        if len(contas) > 1:
            linha.append(funcao(todos))
        linhas.append(linha)
    mostrar_tabela(titulo, colunas, linhas, direita=tuple(range(1, len(colunas))))


def titulo_da_visao(texto):
    console.print()
    console.rule(f"[bold]{texto}[/bold]", align="left")


# ─────────────────────────── Programa principal ───────────────────────────

def principal():
    analisador = argparse.ArgumentParser(description="Quantos casos cada visão pronta da Análise pegaria hoje (só leitura).")
    analisador.add_argument("--conta", choices=["MB", "SV"], help="Só uma empresa (padrão: as duas).")
    analisador.add_argument("--hoje", help="Data de referência AAAA-MM-DD (padrão: hoje).")
    analisador.add_argument("--detalhes", type=int, default=10, help="Linhas de exemplo em cada lista (padrão: 10).")
    args = analisador.parse_args()

    hoje = date.fromisoformat(args.hoje) if args.hoje else timezone.localdate()
    bancos = [(c, a) for c, a in BANCOS if not args.conta or c == args.conta]
    contas = [c for c, _ in bancos]
    limite = max(args.detalhes, 1)

    todos = []
    for conta, alias in bancos:
        todos.extend(carregar_casos(conta, alias, hoje))

    console.print(f"[bold]Visões prontas da Análise — teste com dado real[/bold]  (referência: {hoje.strftime('%d/%m/%Y')}, só leitura)")
    if not todos:
        console.print("Nenhuma devolução encontrada nos bancos consultados.")
        return

    # ─── Casos separados por etapa (usados em várias visões) ───
    aguardando = [c for c in todos if c["etapa"] == ETAPA_AGUARDANDO]
    conferidos = [c for c in todos if c["etapa"] == ETAPA_CONFERIDO]
    abertas = [c for c in todos if c["etapa"] == ETAPA_ABERTA]
    encerradas = [c for c in todos if c["etapa"] == ETAPA_ENCERRADA]
    impressos = [c for c in todos if c["etapa"] == ETAPA_IMPRESSO]
    ja_conferidas = [c for c in todos if c["etapa"] != ETAPA_AGUARDANDO]
    decididas = [c for c in todos if c["decidida"]]

    abertas_para_agir = [c for c in abertas if c["status_prazo"] in ("vencido", "hoje", "proximo") or c["msg_nova"]]
    candidatas_v3 = [c for c in conferidos if c["evidencia"] and not c["teve_mediacao"]]
    encerradas_incompletas = [c for c in encerradas if c["falta_na_conta"]]
    prontas_imprimir = conferidos + encerradas
    mes_atual = hoje.strftime("%Y-%m")
    do_mes = [c for c in todos if c["criado"] and c["criado"].strftime("%Y-%m") == mes_atual]

    # Identidade de cada caso (as tabelas por empresa recortam listas; o id(c) acha o mesmo caso nelas).
    ids_agir = {id(c) for c in abertas_para_agir}
    ids_v3 = {id(c) for c in candidatas_v3}
    ids_incompletas = {id(c) for c in encerradas_incompletas}
    ids_imprimir = {id(c) for c in prontas_imprimir}
    ids_do_mes = {id(c) for c in do_mes}
    ids_encerradas = {id(c) for c in encerradas}

    def classe(n):
        return "vazia hoje" if n == 0 else ("bom tamanho" if n <= 15 else "lista grande")

    # ─── 0. Panorama ───
    titulo_da_visao("0. Panorama: quantas devoluções existem e em que etapa estão")
    definicoes = [(NOME_DA_ETAPA[e], (lambda e: lambda L: sum(1 for c in L if c["etapa"] == e))(e))
                  for e in (ETAPA_AGUARDANDO, ETAPA_CONFERIDO, ETAPA_ABERTA, ETAPA_ENCERRADA, ETAPA_IMPRESSO)]
    definicoes.append(("TOTAL", lambda L: len(L)))
    por_empresa(contas, todos, definicoes, "Devoluções por etapa", "Etapa")

    # ─── Resumo: quantos casos cada visão pega ───
    titulo_da_visao("RESUMO: quantos casos cada visão pega hoje")
    resumo_definicoes = [
        (f"1. Esperando conferência (e há mais de {DIAS_PARADO} dias)",
         lambda L: f"{sum(1 for c in L if c['etapa'] == ETAPA_AGUARDANDO)}  ({sum(1 for c in L if c['etapa'] == ETAPA_AGUARDANDO and (c['dias_na_etapa'] or 0) > DIAS_PARADO)} parados)"),
        ("2. Mediações para eu agir (prazo ou mensagem nova)",
         lambda L: f"{sum(1 for c in L if id(c) in ids_agir)} de {sum(1 for c in L if c['etapa'] == ETAPA_ABERTA)} abertas"),
        ("3. Conferidas COM problema e SEM mediação",
         lambda L: f"{sum(1 for c in L if id(c) in ids_v3)} de {sum(1 for c in L if c['etapa'] == ETAPA_CONFERIDO)} conferidas"),
        ("4. Encerradas com a conta incompleta",
         lambda L: f"{sum(1 for c in L if id(c) in ids_incompletas)} de {sum(1 for c in L if c['etapa'] == ETAPA_ENCERRADA)} encerradas"),
        ("5. Dinheiro em jogo (preço nas mediações abertas)",
         lambda L: brl(soma([c for c in L if c['etapa'] == ETAPA_ABERTA], 'preco'))),
        (f"6. Devoluções cadastradas neste mês ({mes_atual})",
         lambda L: str(sum(1 for c in L if id(c) in ids_do_mes))),
        ("7. Prontas para imprimir (conferidas + encerradas)",
         lambda L: str(sum(1 for c in L if id(c) in ids_imprimir))),
    ]
    por_empresa(contas, todos, resumo_definicoes, "Quantos casos cada visão pega", "Visão")
    totais_de_leitura = [
        ("1. Esperando conferência", len(aguardando)),
        ("2. Mediações para agir", len(abertas_para_agir)),
        ("3. Conferidas com problema sem mediação", len(candidatas_v3)),
        ("4. Encerradas com conta incompleta", len(encerradas_incompletas)),
        ("7. Prontas para imprimir", len(prontas_imprimir)),
    ]
    console.print("Leitura rápida (considerando as empresas selecionadas juntas): "
                  + " · ".join(f"{nome}: {classe(n)}" for nome, n in totais_de_leitura))

    # ─── QUALIDADE DOS DADOS ───
    titulo_da_visao("QUALIDADE DOS DADOS: o campo que a visão precisa está preenchido de verdade?")
    qualidade = [
        ("Preço do produto (todas as devoluções)",
         lambda L: fracao(sum(1 for c in L if c["preco"] is not None), len(L))),
        ("Destino do produto (já conferidas)",
         lambda L: fracao(sum(1 for c in L if c["etapa"] != ETAPA_AGUARDANDO and c["destino"]), sum(1 for c in L if c["etapa"] != ETAPA_AGUARDANDO))),
        ("Com evidência de problema (já conferidas)",
         lambda L: fracao(sum(1 for c in L if c["etapa"] != ETAPA_AGUARDANDO and c["evidencia"]), sum(1 for c in L if c["etapa"] != ETAPA_AGUARDANDO))),
        ("Prazo de resposta (mediações abertas) — digitado à mão",
         lambda L: fracao(sum(1 for c in L if c["etapa"] == ETAPA_ABERTA and c["prazo"]), sum(1 for c in L if c["etapa"] == ETAPA_ABERTA))),
        ("ID da reclamação (mediações abertas)",
         lambda L: fracao(sum(1 for c in L if c["etapa"] == ETAPA_ABERTA and c["claim_id"]), sum(1 for c in L if c["etapa"] == ETAPA_ABERTA))),
        ("Mensagens buscadas ao menos 1 vez (abertas) — sem isso 'mensagem nova' fica cega",
         lambda L: fracao(sum(1 for c in L if c["etapa"] == ETAPA_ABERTA and c["mediacao_atualizada_em"]), sum(1 for c in L if c["etapa"] == ETAPA_ABERTA))),
        ("Reembolsado? sim/não (mediações decididas)",
         lambda L: fracao(sum(1 for c in L if c["decidida"] and c["reembolsado"] is not None), sum(1 for c in L if c["decidida"]))),
        ("Valor reembolsado (decididas com reembolso = sim)",
         lambda L: fracao(sum(1 for c in L if c["decidida"] and c["reembolsado"] and c["valor"] is not None), sum(1 for c in L if c["decidida"] and c["reembolsado"]))),
        ("Anotação da mediação (decididas)",
         lambda L: fracao(sum(1 for c in L if c["decidida"] and c["anotacao_mediacao"]), sum(1 for c in L if c["decidida"]))),
    ]
    por_empresa(contas, todos, qualidade, "Campos preenchidos", "Campo")

    # ─── VISÃO 1 ───
    titulo_da_visao("VISÃO 1 — Esperando conferência há mais tempo")
    faixas = []
    anterior = -1
    for limite_faixa in FAIXAS_DIAS:
        faixas.append((f"{anterior + 1} a {limite_faixa} dias", anterior + 1, limite_faixa))
        anterior = limite_faixa
    faixas.append((f"mais de {FAIXAS_DIAS[-1]} dias", FAIXAS_DIAS[-1] + 1, 10 ** 6))
    def na_faixa(L, minimo, maximo):
        return sum(1 for c in L if c["etapa"] == ETAPA_AGUARDANDO and c["dias_na_etapa"] is not None and minimo <= c["dias_na_etapa"] <= maximo)
    por_empresa(contas, todos, [(nome, (lambda mi, ma: lambda L: str(na_faixa(L, mi, ma)))(mi, ma)) for nome, mi, ma in faixas],
                "Aguardando conferência, por dias desde que a devolução chegou ('Recebido por nós')", "Faixa")
    # Atraso entre a chegada do pacote ('Recebido por nós') e o cadastro no sistema: diz se a data de
    # recebimento e a de cadastro contam a mesma história (atraso ~0) ou não.
    atrasos_cadastro = [c["dias_desde_recebimento"] - c["dias_desde_cadastro"] for c in aguardando
                        if c["dias_desde_cadastro"] is not None and c["dias_desde_recebimento"] is not None]
    if atrasos_cadastro:
        console.print(f"Atraso entre a chegada do pacote ('Recebido por nós') e o cadastro no sistema, nas que aguardam: "
                      f"mediana {statistics.median(atrasos_cadastro):.0f} dia(s), máximo {max(atrasos_cadastro)}, mínimo {min(atrasos_cadastro)} "
                      f"(perto de 0 = tanto faz usar uma data ou outra para contar os dias).")
    mais_antigas = sorted(aguardando, key=lambda c: -(c["dias_na_etapa"] or 0))[:limite]
    mostrar_tabela(f"As {len(mais_antigas)} mais antigas", ["Emp.", "Pedido", "Cliente", "Produto", "Dias esperando", "Plataforma"],
                   [[c["conta"], c["pedido"], curto(c["cliente"], 22), curto(c["produto"], 30), c["dias_na_etapa"] if c["dias_na_etapa"] is not None else "—", c["plataforma"]]
                    for c in mais_antigas], direita=(4,))

    # ─── VISÃO 2 ───
    titulo_da_visao("VISÃO 2 — Mediações para eu agir (prazo vencendo ou mensagem nova)")
    def n_abertas(L, funcao):
        return sum(1 for c in L if c["etapa"] == ETAPA_ABERTA and funcao(c))
    por_empresa(contas, todos, [
        ("Mediações abertas (total)", lambda L: str(n_abertas(L, lambda c: True))),
        ("Prazo VENCIDO", lambda L: str(n_abertas(L, lambda c: c["status_prazo"] == "vencido"))),
        ("Prazo vence HOJE", lambda L: str(n_abertas(L, lambda c: c["status_prazo"] == "hoje"))),
        ("Prazo vence em 1 ou 2 dias", lambda L: str(n_abertas(L, lambda c: c["status_prazo"] == "proximo"))),
        ("Prazo ok (3+ dias)", lambda L: str(n_abertas(L, lambda c: c["status_prazo"] == "ok"))),
        ("SEM prazo registrado", lambda L: str(n_abertas(L, lambda c: c["status_prazo"] is None))),
        ("Com mensagem nova do ML/cliente", lambda L: str(n_abertas(L, lambda c: c["msg_nova"]))),
        (f"Abertas há mais de {DIAS_PARADO} dias", lambda L: str(n_abertas(L, lambda c: (c["dias_desde_abertura"] or 0) > DIAS_PARADO))),
        ("PARA AGIR (prazo vencido/hoje/1-2 dias OU mensagem nova)", lambda L: str(sum(1 for c in L if id(c) in ids_agir))),
    ], "Mediações abertas", "Situação")
    ordem_prazo = {"vencido": 0, "hoje": 1, "proximo": 2, "ok": 3, None: 4}
    a_agir = sorted(abertas, key=lambda c: (ordem_prazo[c["status_prazo"]], not c["msg_nova"], -(c["dias_desde_abertura"] or 0)))[:limite]
    mostrar_tabela(f"As {len(a_agir)} primeiras da fila (prazo mais urgente primeiro)",
                   ["Emp.", "Pedido", "Cliente", "Prazo", "Situação do prazo", "Msg nova", "Aberta há (dias)"],
                   [[c["conta"], c["pedido"], curto(c["cliente"], 22), dmy(c["prazo"]), c["status_prazo"] or "sem prazo",
                     "sim" if c["msg_nova"] else "—", c["dias_desde_abertura"] if c["dias_desde_abertura"] is not None else "—"]
                    for c in a_agir], direita=(6,))

    # ─── VISÃO 3 ───
    titulo_da_visao("VISÃO 3 — Conferidas COM problema e SEM mediação")
    console.print("Antes da lista, a CALIBRAGEM: dos casos já conferidos (qualquer etapa depois de 'Aguardando'), quantos acabaram em mediação?")
    def grupo(L, evidencia, rec7):
        return [c for c in L if c["etapa"] != ETAPA_AGUARDANDO and c["evidencia"] == evidencia and c["rec7"] == rec7]
    def linha_calibragem(evidencia, rec7):
        return lambda L: fracao(sum(1 for c in grupo(L, evidencia, rec7) if c["teve_mediacao"]), len(grupo(L, evidencia, rec7)))
    por_empresa(contas, todos, [
        ("COM evidência · reclamou FORA dos 7 dias", linha_calibragem(True, "fora")),
        ("COM evidência · reclamou DENTRO dos 7 dias", linha_calibragem(True, "dentro")),
        ("COM evidência · sem dado de reclamação", linha_calibragem(True, None)),
        ("SEM evidência · reclamou FORA dos 7 dias", linha_calibragem(False, "fora")),
        ("SEM evidência · reclamou DENTRO dos 7 dias", linha_calibragem(False, "dentro")),
        ("SEM evidência · sem dado de reclamação", linha_calibragem(False, None)),
    ], "Casos já conferidos que tiveram mediação (quantos de quantos, por grupo)", "Grupo")
    console.print("Como ler: se 'COM evidência' tem % ALTO de mediação, um caso conferido com evidência e sem mediação é provável esquecimento "
                  "(a visão é útil). Se for BAIXO, a Ana só media em certos casos e a visão vira ruído.")
    por_empresa(contas, todos, [
        ("Candidatas hoje (conferidas + evidência + sem mediação)", lambda L: str(sum(1 for c in L if id(c) in ids_v3))),
        ("  · reclamou FORA dos 7 dias", lambda L: str(sum(1 for c in L if id(c) in ids_v3 and c["rec7"] == "fora"))),
        ("  · reclamou DENTRO dos 7 dias", lambda L: str(sum(1 for c in L if id(c) in ids_v3 and c["rec7"] == "dentro"))),
        ("  · destino Troca", lambda L: str(sum(1 for c in L if id(c) in ids_v3 and c["destino"] == "troca"))),
        ("  · destino Venda como usado", lambda L: str(sum(1 for c in L if id(c) in ids_v3 and c["destino"] == "usado"))),
        ("Preço dos produtos dessas candidatas", lambda L: brl(soma([c for c in L if id(c) in ids_v3], "preco"))),
        ("  · candidatas sem preço informado", lambda L: str(sum(1 for c in L if id(c) in ids_v3 and c["preco"] is None))),
    ], "Candidatas da visão 3", "Item")
    console.print("Aviso: 'Conferidos' não tem data de conferência no banco — a coluna 'Dias desde o cadastro' é só aproximação.")
    lista_v3 = sorted(candidatas_v3, key=lambda c: -(c["dias_desde_cadastro"] or 0))[:limite]
    mostrar_tabela(f"As {len(lista_v3)} candidatas mais antigas", ["Emp.", "Pedido", "Produto", "Marca", "Dias desde o cadastro", "7 dias", "Destino", "Peças c/ problema", "Preço"],
                   [[c["conta"], c["pedido"], curto(c["produto"], 28), curto(c["marca"], 14), c["dias_desde_cadastro"] if c["dias_desde_cadastro"] is not None else "—",
                     c["rec7"] or "?", c["destino"] or "—", c["pecas_com_problema"], brl(c["preco"])] for c in lista_v3], direita=(4, 7, 8))

    # ─── VISÃO 4 ───
    titulo_da_visao("VISÃO 4 — Encerradas com a conta incompleta")
    def n_falta(L, texto):
        return sum(1 for c in L if id(c) in ids_encerradas and texto in c["falta_na_conta"])
    por_empresa(contas, todos, [
        ("Mediações encerradas (total)", lambda L: str(sum(1 for c in L if id(c) in ids_encerradas))),
        ("Com a conta incompleta", lambda L: str(sum(1 for c in L if id(c) in ids_incompletas))),
        ("  · falta 'reembolsado? (sim/não)'", lambda L: str(n_falta(L, "reembolsado? (sim/não)"))),
        ("  · reembolsado = sim, mas falta o valor", lambda L: str(n_falta(L, "valor reembolsado"))),
        ("  · falta o preço do produto", lambda L: str(n_falta(L, "preço do produto"))),
        ("Histórico: decididas que já foram impressas e ficaram incompletas",
         lambda L: fracao(sum(1 for c in L if c["etapa"] == ETAPA_IMPRESSO and c["decidida"] and c["falta_na_conta"]), sum(1 for c in L if c["etapa"] == ETAPA_IMPRESSO and c["decidida"]))),
    ], "Contas das mediações encerradas", "Item")
    lista_v4 = sorted(encerradas_incompletas, key=lambda c: -(c["dias_na_etapa"] or 0))[:limite]
    mostrar_tabela(f"As {len(lista_v4)} mais antigas", ["Emp.", "Pedido", "Cliente", "Encerrada em", "Dias parada", "O que falta"],
                   [[c["conta"], c["pedido"], curto(c["cliente"], 22), dmy(c["fim"]), c["dias_na_etapa"] if c["dias_na_etapa"] is not None else "—", ", ".join(c["falta_na_conta"])]
                    for c in lista_v4], direita=(4,))

    # ─── VISÃO 5 ───
    titulo_da_visao("VISÃO 5 — Dinheiro em jogo e dinheiro recuperado")
    def decididas_de(L):
        return [c for c in L if c["decidida"]]
    def sucesso(L):
        d = decididas_de(L)
        return fracao(sum(1 for c in d if c["reembolsado"] is True), len(d))
    por_empresa(contas, todos, [
        ("EM JOGO: mediações abertas", lambda L: str(sum(1 for c in L if c["etapa"] == ETAPA_ABERTA))),
        ("EM JOGO: soma do preço dos produtos", lambda L: brl(soma([c for c in L if c["etapa"] == ETAPA_ABERTA], "preco"))),
        ("  · abertas sem preço informado", lambda L: str(sum(1 for c in L if c["etapa"] == ETAPA_ABERTA and c["preco"] is None))),
        ("DECIDIDAS: mediações com data de encerramento", lambda L: str(len(decididas_de(L)))),
        ("  · reembolsadas (sim)", sucesso),
        ("  · não reembolsadas (não)", lambda L: str(sum(1 for c in decididas_de(L) if c["reembolsado"] is False))),
        ("  · sem a informação sim/não", lambda L: str(sum(1 for c in decididas_de(L) if c["reembolsado"] is None))),
        ("RECUPERADO: soma do valor reembolsado", lambda L: brl(soma(decididas_de(L), "valor"))),
        ("Soma do preço das decididas", lambda L: brl(soma(decididas_de(L), "preco"))),
        ("Diferença (preço − reembolsado), só onde os 2 estão preenchidos", lambda L: brl(soma([c for c in decididas_de(L) if c["diferenca"] is not None], "diferenca"))),
        ("  · quantas decididas entram nessa conta", lambda L: str(sum(1 for c in decididas_de(L) if c["diferenca"] is not None))),
    ], "Em jogo × recuperado", "Item")
    duracoes = [(c["fim"] - c["abertura"]).days for c in decididas if c["abertura"] and c["fim"]]
    if duracoes:
        console.print(f"Duração das mediações decididas (abertura → encerramento): mediana {statistics.median(duracoes):.0f} dia(s), "
                      f"média {statistics.mean(duracoes):.1f}, mínima {min(duracoes)}, máxima {max(duracoes)}  ({len(duracoes)} casos).")

    # ─── VISÃO 6 ───
    titulo_da_visao("VISÃO 6 — Resultado por mês (pelo mês do cadastro da devolução)")
    por_mes = defaultdict(list)
    for c in todos:
        por_mes[c["criado"].strftime("%Y-%m") if c["criado"] else "sem data"].append(c)
    linhas_mes = []
    for mes in sorted(por_mes, reverse=True)[:12]:
        L = por_mes[mes]
        dec = [c for c in L if c["decidida"]]
        linhas_mes.append([
            mes, len(L), sum(1 for c in L if c["destino"] == "troca"), sum(1 for c in L if c["destino"] == "usado"),
            sum(1 for c in L if c["teve_mediacao"]), sum(1 for c in dec if c["reembolsado"] is True),
            brl(soma(L, "preco")), brl(soma(dec, "valor")),
        ])
    mostrar_tabela("Últimos meses (as empresas selecionadas juntas)",
                   ["Mês", "Cadastradas", "Troca", "Usado", "Com mediação", "Reembolsadas", "Preço dos produtos", "Valor reembolsado"],
                   linhas_mes, direita=(1, 2, 3, 4, 5, 6, 7))

    # ─── VISÃO 7 ───
    titulo_da_visao("VISÃO 7 — Prontas para imprimir")
    por_empresa(contas, todos, [
        ("Conferidas (podem ir direto para Impressos)", lambda L: str(sum(1 for c in L if c["etapa"] == ETAPA_CONFERIDO))),
        ("Mediações encerradas (aguardando impressão)", lambda L: str(sum(1 for c in L if c["etapa"] == ETAPA_ENCERRADA))),
        ("Total pronto para imprimir", lambda L: str(sum(1 for c in L if id(c) in ids_imprimir))),
    ], "Aguardando impressão", "Item")

    # ─── Concentração ───
    titulo_da_visao("CONCENTRAÇÃO — agrupar por marca ou produto vale a pena?")
    for rotulo, chave in (("marca", "marca"), ("produto", "produto")):
        contagem = Counter(c[chave] for c in todos)
        total = len(todos)
        acumulado = 0
        linhas_topo = []
        for nome, n in contagem.most_common(TOPO_CONCENTRACAO):
            acumulado += n
            linhas_topo.append([curto(nome, 50), n, f"{round(100 * n / total)}%", f"{round(100 * acumulado / total)}%"])
        mostrar_tabela(f"Mais devolvidos por {rotulo} (de {len(contagem)} {rotulo}s diferentes, {total} devoluções)",
                       [rotulo.capitalize(), "Devoluções", "% do total", "% acumulado"], linhas_topo, direita=(1, 2, 3))

    console.print()
    console.print("[bold]Como usar este relatório:[/bold] 1) olhe o RESUMO; 2) confira a QUALIDADE DOS DADOS de cada campo que a visão usa; "
                  "3) na visão 3, leia a CALIBRAGEM antes da lista; 4) as listas de exemplo servem para você reconhecer casos reais.")

    # ─── Grava relatório e JSON ───
    CAMINHO_RELATORIO.parent.mkdir(parents=True, exist_ok=True)
    console.save_text(str(CAMINHO_RELATORIO), clear=False)

    def enxuto(c):
        return {k: v for k, v in c.items()}
    saida = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "data_de_referencia": hoje.isoformat(),
        "contas": contas,
        "total_devolucoes": len(todos),
        "visao_1_aguardando": [enxuto(c) for c in sorted(aguardando, key=lambda c: -(c["dias_na_etapa"] or 0))],
        "visao_2_mediacoes_abertas": [enxuto(c) for c in a_agir_completa(abertas, ordem_prazo)],
        "visao_3_conferidas_com_problema_sem_mediacao": [enxuto(c) for c in candidatas_v3],
        "visao_4_encerradas_conta_incompleta": [enxuto(c) for c in encerradas_incompletas],
        "visao_5_em_jogo_abertas": [enxuto(c) for c in abertas],
        "visao_5_decididas": [enxuto(c) for c in decididas],
        "visao_7_prontas_para_imprimir": [enxuto(c) for c in prontas_imprimir],
    }
    with open(CAMINHO_JSON, "w", encoding="utf-8") as arquivo:
        json.dump(saida, arquivo, ensure_ascii=False, indent=2, default=_serializar)
    console.print(f"\nRelatório salvo em: {CAMINHO_RELATORIO}\nDetalhes (todos os casos) em: {CAMINHO_JSON}")


def a_agir_completa(abertas, ordem_prazo):
    return sorted(abertas, key=lambda c: (ordem_prazo[c["status_prazo"]], not c["msg_nova"], -(c["dias_desde_abertura"] or 0)))


def _serializar(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(f"Tipo não serializável: {type(valor)}")


if __name__ == "__main__":
    principal()
