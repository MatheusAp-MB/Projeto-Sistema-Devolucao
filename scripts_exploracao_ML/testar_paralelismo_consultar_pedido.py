# scripts_exploracao_ML/testar_paralelismo_consultar_pedido.py
#
# Objetivo: testar, ANTES de mexer em qualquer arquivo do sistema, se vale a
# pena fazer várias chamadas à API do ML ao mesmo tempo na tela "Consultar
# Pedido" (hoje ela faz ~11 chamadas uma depois da outra, esperando cada uma
# terminar). Mesmo método já validado no Sistema Interno V2 (frete, comissão,
# buscar_mlbs...): isolar e medir primeiro, aplicar só depois.
#
# Só leitura: TODAS as chamadas são GET. Nada é gravado no banco, nada é
# enviado pro ML, nenhum arquivo do sistema é alterado. As 2 mudanças que o
# script "simula" (conexão reaproveitada e espaçamento menor) existem só na
# memória deste processo e são desfeitas no final (ou se você apertar Ctrl+C).
#
# São 3 testes, rodados em ordem (cada um pode ser ligado/desligado lá embaixo):
#
#   TESTE 1 — Conexão reaproveitada (pool). Hoje cada chamada abre uma conexão
#     nova com o ML (handshake TLS a cada vez). Faz as MESMAS chamadas, sem pool
#     e com pool, alternando a ordem, e mostra quanto cada chamada economiza.
#
#   TESTE 2 — Quantas chamadas ao mesmo tempo o ML aguenta. Dois grupos
#     separados, porque as reclamações (post-purchase) podem ter um limite
#     diferente das vendas: "vendas" (pedido, envio, anúncio) e "reclamações"
#     (reclamação, devolução, mensagens). Testa 1, 2, 4 e 8 chamadas
#     simultâneas, com o espaçador de 0,4 s DESLIGADO, contando os 429 ("você
#     passou do limite"). FREIO DE SEGURANÇA: se aparecer 429 num nível, aquele
#     grupo para ali e não sobe pro nível seguinte.
#
#   TESTE 3 — A tela inteira. Reproduz as chamadas exatas de view_consultar_
#     pedido para o pedido de teste, em vários cenários (como é hoje; só com
#     pool; em 3 "ondas" paralelas com espaçador de 0,4 s / 0,15 s / sem
#     espaçador), repetindo cada um e alternando a ordem. Compara o TEMPO e
#     também o CONTEÚDO recebido (tem que ser idêntico em todos os cenários).
#     Os cenários mais agressivos só rodam se o Teste 2 não achou nenhum 429.
#
# Volume total: até ~400 chamadas (a varredura de 20/09 fez 539). O limite do ML é
# por APLICATIVO (Client ID): rode com a Ana fora do sistema e sem coleta em
# massa do Sistema Interno V2 rodando ao mesmo tempo.
#
# No final, o relatório também é salvo em
# scripts_exploracao_ML/logs/testar_paralelismo_consultar_pedido_relatorio.txt
#
# COMO USAR:
#   python scripts_exploracao_ML/testar_paralelismo_consultar_pedido.py

import hashlib
import json
import logging
import os
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.auth.gerenciador_token import FalhaAutenticacao, obter_token_valido
from api_mercado_livre.core.estrutura_api import cliente_api
from api_mercado_livre.core.estrutura_api.cliente_api import (
    chamar_api, ErroAPI, ErroAutenticacaoAPI, _configurar_logger,
)

# ==== CONFIGURA AQUI ANTES DE RODAR ====
CONTA = "SV"                          # conta do pedido de teste (MB ou SV)
NUMERO_PEDIDO = "2000018229470186"    # pedido de teste (conta SV, claim 5576006769)

RODAR_TESTE_1_POOL = True
RODAR_TESTE_2_LIMITE_SIMULTANEO = True
RODAR_TESTE_3_TELA_COMPLETA = True

CONFIRMAR_ANTES_DE_COMECAR = True     # pede um Enter antes de começar (lembrete: Ana fora do sistema)

# --- Teste 1 ---
T1_CHAMADAS_POR_RODADA = 10           # chamadas seguidas a /orders/{pedido} em cada rodada
T1_RODADAS = 2                        # cada rodada testa "sem pool" e "com pool" (ordem alterna)

# --- Teste 2 ---
T2_NIVEIS_DE_THREADS = [1, 2, 4, 8]   # chamadas simultâneas testadas (sobe só se não houver 429)
T2_CHAMADAS_POR_NIVEL = 24
T2_PAUSA_ENTRE_NIVEIS_SEGUNDOS = 10
T2_MESES_ATRAS = 6                    # janela da busca de reclamações abertas pra montar a amostra
T2_QTD_RECLAMACOES_NA_AMOSTRA = 8

# --- Teste 3 ---
T3_REPETICOES = 3                     # cada cenário roda isso de vezes (ordem alternada)
T3_PAUSA_ENTRE_CENARIOS_SEGUNDOS = 5
T3_MAX_THREADS = 6                    # a maior "onda" da tela tem ~6 chamadas independentes
T3_RODAR_CENARIOS_ARRISCADOS = True   # cenários com espaçador reduzido/desligado

# --- Segurança ---
LIMITE_DE_429_PARA_ABORTAR = 5        # total de avisos de 429 que faz o script parar sozinho
MAX_TENTATIVAS = 2                    # tentativas por chamada (baixo de propósito: o 429 aparece rápido)
POOL_TAMANHO = 50                     # mesmo valor usado no Sistema Interno V2
# ========================================

FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
HEADER_FORMATO_NOVO = {"x-format-new": "true"}                 # igual a views.py (só no /history)
ATRIBUTOS_ITEMS = "id,status,permalink,thumbnail,pictures"     # igual a views.py (_buscar_dados_dos_anuncios)
PASTA_LOGS = Path(__file__).resolve().parent / "logs"
NOME_LOG = "testar_paralelismo_consultar_pedido"
ARQUIVO_RELATORIO = PASTA_LOGS / "testar_paralelismo_consultar_pedido_relatorio.txt"

console = Console(record=True)


# ───────────────────────── Peças de apoio ─────────────────────────

class FreioDeSeguranca(Exception):
    """Levantada na thread principal quando o script decide parar sozinho."""


PARAR = threading.Event()   # ligado se a autenticação falhar — não adianta continuar


class Contador429(logging.Handler):
    """Conta quantas vezes o chamar_api() avisou um 429. O 429 nunca vira
    exceção (é retry automático com warning), então só dá pra contar
    escutando o log — mesmo método do teste de paralelismo do V2. Só conta
    WARNING que COMEÇA com "429 em": um id de pedido que por acaso contenha
    "429" nunca é contado por engano."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.total = 0

    def emit(self, record):
        if record.levelno == logging.WARNING and record.getMessage().startswith("429 em"):
            self.total += 1


CONTADOR_429 = Contador429()


def verificar_freio():
    if PARAR.is_set():
        raise FreioDeSeguranca("a autenticação falhou — não adianta continuar.")
    if CONTADOR_429.total >= LIMITE_DE_429_PARA_ABORTAR:
        raise FreioDeSeguranca(
            f"{CONTADOR_429.total} avisos de 429 (limite configurado: {LIMITE_DE_429_PARA_ABORTAR}) "
            f"— parei pra não gastar a cota do aplicativo."
        )


def fmt_s(valor):
    return f"{valor:.2f}".replace(".", ",") + " s"


def fmt_ms(valor_em_segundos):
    return f"{valor_em_segundos * 1000:.0f} ms"


def formatar_data_para_filtro(instante):
    # igual ao cronometrar_refresh_individual.py (formato que a busca de claims aceita)
    texto = instante.isoformat(timespec="milliseconds")
    return texto[:-6] + texto[-6:].replace(":", "")


# ── Pool de conexão e espaçador: mudanças SÓ na memória deste processo ──

# * Desde 04/10/2026 o cliente_api tem 1 ponto único de transporte,
#   _enviar_requisicao(), que já usa uma Session persistente (pool) — "com pool"
#   passou a ser o jeito REAL do sistema. Pra este script continuar comparando
#   "sem pool × com pool" (agora: "antes × depois"), ele troca essa função, só na
#   memória: por uma que usa requests.request() solto (1 conexão nova por chamada,
#   como era antes) ou por uma com Session NOVA (o handshake da 1ª chamada entra
#   na medida). Se o cliente_api ainda for o antigo (sem _enviar_requisicao), o
#   script troca requests.request(), como na versão original.
_TEM_TRANSPORTE_NOVO = hasattr(cliente_api, "_enviar_requisicao")
_requests_solto = requests.request                                    # 1 conexão nova por chamada
_transporte_real = getattr(cliente_api, "_enviar_requisicao", None)   # o do sistema (com pool); None no cliente_api antigo
_sessao_ativa = None


def _instalar_transporte(funcao):
    if _TEM_TRANSPORTE_NOVO:
        cliente_api._enviar_requisicao = funcao
    else:
        requests.request = funcao


def ligar_pool():
    """Passa a usar uma Session NOVA com pool — a mesma troca que o Sistema
    Interno V2 fez em chamar_api() em 29/09/2026. Só na memória deste processo:
    nenhum arquivo é tocado."""
    global _sessao_ativa
    if _sessao_ativa is not None:
        return
    sessao = requests.Session()
    sessao.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=POOL_TAMANHO, max_retries=0))
    _sessao_ativa = sessao

    def request_com_pool(metodo, url, **kwargs):
        return sessao.request(metodo, url, **kwargs)

    _instalar_transporte(request_com_pool)


def desligar_pool():
    """Volta pro 'sem pool': 1 conexão nova por chamada (o jeito de antes do pool)."""
    global _sessao_ativa
    if _sessao_ativa is not None:
        _sessao_ativa.close()
        _sessao_ativa = None
    _instalar_transporte(_requests_solto)


def restaurar_transporte_original():
    """Devolve o transporte REAL do sistema (com pool, no cliente_api novo). Roda no final."""
    desligar_pool()
    if _TEM_TRANSPORTE_NOVO:
        cliente_api._enviar_requisicao = _transporte_real
    else:
        requests.request = _requests_solto


def definir_intervalo_espacador(intervalo_segundos):
    """Muda, só na memória, o intervalo mínimo do EspacadorChamadas que o
    chamar_api() usa (protecao.py). O arquivo não é alterado."""
    cliente_api._espacador._intervalo_minimo = intervalo_segundos


# ── Uma chamada, com tempo medido e erro sempre contido ──

@dataclass
class Resultado:
    rotulo: str
    situacao: str            # "ok", "404" (não encontrado — normal em /returns) ou "erro"
    segundos: float
    impressao: str = None    # "impressão digital" do JSON recebido (pra comparar conteúdo)
    corpo: object = None
    texto_erro: str = ""


def _impressao_digital(corpo):
    texto = json.dumps(corpo, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(texto.encode("utf-8")).hexdigest()[:10]


def chamar(rotulo, endpoint, params=None, headers=None, espaca=True):
    """1 GET via chamar_api(), com o tempo medido. NUNCA levanta exceção pra
    quem chamou (inclusive quando roda dentro de uma thread): o erro de 1
    chamada vira um Resultado com situacao "erro" e as outras seguem — mesma
    regra do V2 (erro de 1 item não derruba o resto)."""
    if PARAR.is_set():
        return Resultado(rotulo, "erro", 0.0, texto_erro="abortado (autenticação falhou)")
    inicio = time.perf_counter()
    corpo = None
    situacao = "ok"
    texto = ""
    try:
        resposta = chamar_api(
            "GET", endpoint, pasta_logs=PASTA_LOGS, conta=CONTA, params=params, headers_extra=headers,
            nome_log=NOME_LOG, max_tentativas=MAX_TENTATIVAS, espacador_ativo=espaca,
        )
        corpo = resposta.json()
    except ErroAPI as erro:
        texto = str(erro)
        situacao = "404" if texto.startswith("Erro 404 ") else "erro"
    except (ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        PARAR.set()
        texto = f"autenticação: {erro}"
        situacao = "erro"
    except Exception as erro:  # noqa: BLE001 — contido de propósito, ver docstring
        texto = f"{type(erro).__name__}: {erro}"
        situacao = "erro"
    segundos = time.perf_counter() - inicio
    impressao = _impressao_digital(corpo) if situacao == "ok" else None
    return Resultado(rotulo, situacao, segundos, impressao, corpo, texto[:200])


def tabela(titulo, colunas):
    t = Table(title=titulo, box=box.SIMPLE)
    for nome, alinhamento in colunas:
        t.add_column(nome, justify=alinhamento)
    return t


# ───────────────────────── TESTE 1 — pool de conexão ─────────────────────────

def teste_1_pool():
    console.rule("[bold]TESTE 1 — Conexão reaproveitada (pool)[/bold]")
    console.print(
        f"{T1_RODADAS} rodada(s) × 2 condições × {T1_CHAMADAS_POR_RODADA} chamadas seguidas a "
        f"/orders/{NUMERO_PEDIDO}, SEM espaçador (mede só a latência real). A ordem alterna entre "
        f"as rodadas pra um lado não ganhar vantagem por vir primeiro.\n"
    )
    tempos = {False: [], True: []}
    primeiras_com_pool = []
    for rodada in range(T1_RODADAS):
        ordem = (False, True) if rodada % 2 == 0 else (True, False)
        for com_pool in ordem:
            if com_pool:
                ligar_pool()      # Session NOVA a cada rodada: a 1ª chamada paga o handshake
            else:
                desligar_pool()
            for i in range(T1_CHAMADAS_POR_RODADA):
                r = chamar("t1", f"/orders/{NUMERO_PEDIDO}", espaca=False)
                verificar_freio()
                if r.situacao == "ok":
                    tempos[com_pool].append(r.segundos)
                    if com_pool and i == 0:
                        primeiras_com_pool.append(r.segundos)
            desligar_pool()
            time.sleep(2)

    t = tabela("Latência por chamada (a mesma consulta, só o transporte muda)", [
        ("Condição", "left"), ("Chamadas", "right"), ("Média", "right"),
        ("Mediana", "right"), ("Mais rápida", "right"), ("Mais lenta", "right"),
    ])
    for com_pool, nome in ((False, "Como é hoje (conexão nova a cada chamada)"), (True, "Com pool (conexão reaproveitada)")):
        lista = tempos[com_pool]
        if lista:
            t.add_row(nome, str(len(lista)), fmt_ms(statistics.mean(lista)), fmt_ms(statistics.median(lista)),
                      fmt_ms(min(lista)), fmt_ms(max(lista)))
        else:
            t.add_row(nome, "0", "—", "—", "—", "—")
    console.print(t)
    if tempos[False] and tempos[True]:
        media_sem = statistics.mean(tempos[False])
        media_com = statistics.mean(tempos[True])
        economia = media_sem - media_com
        console.print(
            f"Economia média por chamada: [bold]{fmt_ms(economia)}[/bold] "
            f"({economia / media_sem * 100:.0f}% mais rápida com pool). "
            f"Na tela (~11 chamadas): ≈ {fmt_s(economia * 11)} a menos, só por isso."
        )
        if primeiras_com_pool:
            console.print(
                f"[dim]Com pool, a 1ª chamada de cada rodada (que ainda abre a conexão) levou em média "
                f"{fmt_ms(statistics.mean(primeiras_com_pool))}; as seguintes reaproveitam a conexão.[/dim]"
            )
    console.print()


# ───────────────────────── TESTE 2 — limite de chamadas simultâneas ─────────────────────────

ACHOU_429_NO_TESTE_2 = False


def montar_amostra_teste_2():
    """Acha reclamações abertas reais da conta (mesma busca validada em
    cronometrar_refresh_individual.py) e, delas, os pedidos/envios/anúncios,
    pra ter alvos DIFERENTES nos 2 grupos (o V2 também usou combinações
    reais e distintas). Essa parte de descoberta NÃO é cronometrada."""
    console.print("[dim]Montando a amostra (não cronometrada)...[/dim]")
    user_id = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG).json()["id"]
    agora = datetime.now(FUSO_HORARIO)
    inicio = formatar_data_para_filtro(agora - timedelta(days=T2_MESES_ATRAS * 30))
    fim = formatar_data_para_filtro(agora)

    vistos = set()
    claims = []
    for papel in ("respondent", "complainant"):
        try:
            resposta = chamar_api(
                "GET", "/post-purchase/v1/claims/search", pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
                params={
                    "players.user_id": user_id, "players.role": papel, "status": "opened",
                    "range": f"date_created:after:{inicio},before:{fim}",
                    "sort": "date_created:desc", "limit": 50, "offset": 0,
                },
            )
        except (ErroAPI, ErroAutenticacaoAPI) as erro:
            console.print(f"  [yellow]Busca de reclamações ({papel}) falhou: {escape(str(erro))}[/yellow]")
            continue
        for c in resposta.json().get("data", []):
            if c.get("id") not in vistos:
                vistos.add(c.get("id"))
                claims.append(c)

    sorteadas = random.Random(7).sample(claims, k=min(T2_QTD_RECLAMACOES_NA_AMOSTRA, len(claims)))
    console.print(f"  {len(claims)} reclamação(ões) aberta(s) na conta {CONTA}; {len(sorteadas)} na amostra.")

    especificacoes_reclamacoes = []
    especificacoes_vendas = []
    for c in sorteadas:
        cid = c["id"]
        especificacoes_reclamacoes += [
            ("claim", f"/post-purchase/v1/claims/{cid}", None, None),
            ("returns", f"/post-purchase/v2/claims/{cid}/returns", None, None),
            ("messages", f"/post-purchase/v1/claims/{cid}/messages", None, None),
        ]
        if c.get("resource") == "order" and c.get("resource_id"):
            oid = c["resource_id"]
            pre = chamar("pre_pedido", f"/orders/{oid}")      # espaçador ligado: descoberta, não é medida
            if pre.situacao != "ok":
                continue
            pedido = pre.corpo
            especificacoes_vendas.append(("orders", f"/orders/{oid}", None, None))
            sid = (pedido.get("shipping") or {}).get("id")
            if sid:
                especificacoes_vendas += [
                    ("ship_hist", f"/shipments/{sid}/history", None, HEADER_FORMATO_NOVO),
                    ("ship_det", f"/shipments/{sid}", None, None),
                ]
            mlbs = []
            for item_bruto in pedido.get("order_items") or []:
                mlb = (item_bruto.get("item") or {}).get("id")
                if mlb and mlb not in mlbs:
                    mlbs.append(mlb)
            if mlbs:
                especificacoes_vendas.append(("items", "/items", {"ids": ",".join(mlbs), "attributes": ATRIBUTOS_ITEMS}, None))
    verificar_freio()

    random.Random(11).shuffle(especificacoes_vendas)        # mistura os tipos; mesma ordem em todos os níveis
    random.Random(11).shuffle(especificacoes_reclamacoes)
    return especificacoes_vendas, especificacoes_reclamacoes


def rodar_nivel(especificacoes, threads, quantidade):
    sequencia = [especificacoes[i % len(especificacoes)] for i in range(quantidade)]
    antes_429 = CONTADOR_429.total
    resultados = []
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futuros = [executor.submit(chamar, f"t2:{e[0]}", e[1], e[2], e[3], False) for e in sequencia]
        for futuro in as_completed(futuros):      # só a thread principal junta os resultados
            resultados.append(futuro.result())
    total = time.perf_counter() - inicio
    return {
        "threads": threads, "total": total, "chamadas": len(resultados),
        "por_segundo": len(resultados) / total if total else 0,
        "latencia_media": statistics.mean(r.segundos for r in resultados),
        "ok": sum(1 for r in resultados if r.situacao == "ok"),
        "nao_encontrado": sum(1 for r in resultados if r.situacao == "404"),
        "erros": sum(1 for r in resultados if r.situacao == "erro"),
        "n_429": CONTADOR_429.total - antes_429,
    }


def teste_2_limite_simultaneo():
    global ACHOU_429_NO_TESTE_2
    console.rule("[bold]TESTE 2 — Quantas chamadas ao mesmo tempo o ML aguenta[/bold]")
    console.print(
        f"Níveis: {T2_NIVEIS_DE_THREADS} chamadas simultâneas, {T2_CHAMADAS_POR_NIVEL} chamadas por nível, "
        f"espaçador DESLIGADO, pool LIGADO (é como ficará depois da mudança). Se aparecer 429 num nível, "
        f"o grupo para ali.\n"
    )
    ligar_pool()
    especificacoes_vendas, especificacoes_reclamacoes = montar_amostra_teste_2()
    familias = [
        ("Vendas (pedido, envio, anúncio)", especificacoes_vendas),
        ("Reclamações (reclamação, devolução, mensagens)", especificacoes_reclamacoes),
    ]
    resumo = {}
    for nome, especificacoes in familias:
        if not especificacoes:
            console.print(f"[yellow]{nome}: sem alvos na amostra — grupo pulado.[/yellow]\n")
            continue
        t = tabela(f"{nome} — {len(especificacoes)} alvo(s) distintos na amostra", [
            ("Simultâneas", "right"), ("Tempo total", "right"), ("Chamadas/s", "right"),
            ("Latência média", "right"), ("OK", "right"), ("404", "right"), ("Erros", "right"), ("429", "right"),
        ])
        maior_nivel_sem_429 = None
        parou_em = None
        for indice, threads in enumerate(T2_NIVEIS_DE_THREADS):
            if indice > 0:
                time.sleep(T2_PAUSA_ENTRE_NIVEIS_SEGUNDOS)
            r = rodar_nivel(especificacoes, threads, T2_CHAMADAS_POR_NIVEL)
            t.add_row(
                str(threads), fmt_s(r["total"]), f"{r['por_segundo']:.1f}".replace(".", ","),
                fmt_ms(r["latencia_media"]), str(r["ok"]), str(r["nao_encontrado"]), str(r["erros"]), str(r["n_429"]),
            )
            if PARAR.is_set():
                break
            if r["n_429"] > 0:
                ACHOU_429_NO_TESTE_2 = True
                parou_em = threads
                break
            maior_nivel_sem_429 = threads
        console.print(t)
        resumo[nome] = (maior_nivel_sem_429, parou_em)
        if parou_em is not None:
            console.print(f"[bold yellow]{nome}: apareceu 429 com {parou_em} simultâneas — parei este grupo ali.[/bold yellow]\n")
        else:
            console.print(f"[green]{nome}: nenhum 429 até {maior_nivel_sem_429} simultâneas.[/green]\n")
        verificar_freio()    # só DEPOIS de mostrar a tabela do grupo: o freio global nunca engole um resultado
    desligar_pool()
    console.print(
        "[dim]404 em /returns é normal (reclamação sem devolução física). Em 'Erros' entram timeouts e falhas "
        "reais; um 429 que esgotou as tentativas também vira erro.[/dim]\n"
    )
    return resumo


# ───────────────────────── TESTE 3 — a tela inteira ─────────────────────────

@dataclass(frozen=True)
class Cenario:
    nome: str
    paralelo: bool
    pool: bool
    intervalo_espacador: float          # None = espaçador desligado
    usa_users_me: bool
    arriscado: bool = False


CENARIOS = [
    Cenario("1. Hoje (sequencial)", False, False, 0.4, True),
    Cenario("2. Seq. + pool, sem /users/me", False, True, 0.4, False),
    Cenario("3. Ondas, espaç. 0,4 s", True, True, 0.4, False),
    Cenario("4. Ondas, espaç. 0,15 s", True, True, 0.15, False, arriscado=True),
    Cenario("5. Ondas, sem espaçador", True, True, None, False, arriscado=True),
]


@dataclass
class Execucao:
    cenario: Cenario
    segundos: float
    resultados: dict
    escolhida: object
    segundos_ondas: list = field(default_factory=list)
    candidatas_antes: tuple = ()    # reclamações que vieram ANTES da escolhida e cujo /returns falhou
    n_429: int = 0

    def dados_chave(self):
        """Rótulo → (situação, impressão) só das chamadas que o caminho
        sequencial da tela faria. Ignora as chamadas ESPECULATIVAS do modo
        paralelo (ex.: /returns de uma reclamação depois da escolhida) e o
        /users/me (que só existe no cenário 'como é hoje')."""
        escolhida = str(self.escolhida)
        chave = {}
        for rotulo, r in self.resultados.items():
            prefixo, _, valor = rotulo.partition(":")
            if prefixo == "users_me":
                continue
            if prefixo in ("claim", "messages") and valor != escolhida:
                continue
            if prefixo == "returns" and valor != escolhida and valor not in self.candidatas_antes:
                continue
            chave[rotulo] = (r.situacao, r.impressao)
        return chave


def _ordenar_claims(claims):
    # mesma ordem de view_consultar_pedido: return/fulfillment primeiro (sort estável)
    return sorted(claims, key=lambda c: 0 if c.get("type") in ("return", "fulfillment") else 1)


def _claims_do_pedido(r_claims):
    if r_claims is None or r_claims.situacao != "ok":
        return []
    return (r_claims.corpo or {}).get("data") or []


def _mlbs_do_pedido(pedido):
    mlbs = []
    for item_bruto in (pedido or {}).get("order_items") or []:
        mlb = (item_bruto.get("item") or {}).get("id")
        if mlb and mlb not in mlbs:
            mlbs.append(mlb)
    return mlbs


def rodar_sequencial(cen):
    """Replica a ORDEM e as chamadas de view_consultar_pedido, uma de cada vez."""
    espaca = cen.intervalo_espacador is not None
    res = {}

    def g(rotulo, endpoint, params=None, headers=None):
        r = chamar(rotulo, endpoint, params, headers, espaca)
        res[rotulo] = r
        return r

    inicio = time.perf_counter()
    r_pedido = g("orders", f"/orders/{NUMERO_PEDIDO}")
    r_claims = g("claims_search", "/post-purchase/v1/claims/search", {"order_id": NUMERO_PEDIDO})
    pedido = r_pedido.corpo if r_pedido.situacao == "ok" else {}
    claims_ordem = _ordenar_claims(_claims_do_pedido(r_claims))

    devolucao = None
    escolhida = None
    antes = []
    for candidata in claims_ordem:
        cid = candidata["id"]
        r_ret = g(f"returns:{cid}", f"/post-purchase/v2/claims/{cid}/returns")
        if r_ret.situacao != "ok":
            antes.append(str(cid))
            continue
        devolucao = r_ret.corpo
        g(f"claim:{cid}", f"/post-purchase/v1/claims/{cid}")
        escolhida = cid
        break
    if devolucao is None and claims_ordem:
        escolhida = claims_ordem[0]["id"]
        g(f"claim:{escolhida}", f"/post-purchase/v1/claims/{escolhida}")
        devolucao = {}

    mlbs = _mlbs_do_pedido(pedido)
    if mlbs:
        g("items", "/items", {"ids": ",".join(mlbs), "attributes": ATRIBUTOS_ITEMS})
    sid_ida = (pedido.get("shipping") or {}).get("id")
    if sid_ida:
        g(f"ida_hist:{sid_ida}", f"/shipments/{sid_ida}/history", None, HEADER_FORMATO_NOVO)
        g(f"ida_det:{sid_ida}", f"/shipments/{sid_ida}")
    for envio in ((devolucao or {}).get("shipments") or []):
        sid = envio.get("shipment_id")
        if not sid:
            continue
        g(f"volta_hist:{sid}", f"/shipments/{sid}/history", None, HEADER_FORMATO_NOVO)
        g(f"volta_det:{sid}", f"/shipments/{sid}")
    if cen.usa_users_me:
        g("users_me", "/users/me")
    if escolhida is not None:
        g(f"messages:{escolhida}", f"/post-purchase/v1/claims/{escolhida}/messages")

    return Execucao(cen, time.perf_counter() - inicio, res, escolhida, candidatas_antes=tuple(antes))


def rodar_em_ondas(cen):
    """As MESMAS chamadas, agrupadas em ondas pela dependência entre elas:
       onda 1: pedido  ∥ busca de reclamações
       onda 2: /returns (de todas as candidatas) ∥ anúncios ∥ envio de ida (histórico + detalhe)
               ∥ reclamação e mensagens da 1ª candidata (palpite que costuma acertar)
       onda 3: envios de volta (histórico + detalhe) (+ reclamação/mensagens da escolhida, se o palpite errou)
    Só a thread principal junta os resultados (as_completed); cada chamada
    isolada devolve um Resultado, mesmo quando falha."""
    espaca = cen.intervalo_espacador is not None
    res = {}
    segundos_ondas = []

    def onda(executor, tarefas):
        if not tarefas:
            return
        inicio_onda = time.perf_counter()
        futuros = [executor.submit(chamar, t[0], t[1], t[2], t[3], espaca) for t in tarefas]
        for futuro in as_completed(futuros):
            r = futuro.result()
            res[r.rotulo] = r
        segundos_ondas.append(time.perf_counter() - inicio_onda)

    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=T3_MAX_THREADS) as executor:
        onda(executor, [
            ("orders", f"/orders/{NUMERO_PEDIDO}", None, None),
            ("claims_search", "/post-purchase/v1/claims/search", {"order_id": NUMERO_PEDIDO}, None),
        ])
        pedido = res["orders"].corpo if res["orders"].situacao == "ok" else {}
        claims_ordem = _ordenar_claims(_claims_do_pedido(res.get("claims_search")))
        primeira = claims_ordem[0]["id"] if claims_ordem else None

        tarefas2 = [(f"returns:{c['id']}", f"/post-purchase/v2/claims/{c['id']}/returns", None, None) for c in claims_ordem]
        if primeira is not None:
            tarefas2.append((f"claim:{primeira}", f"/post-purchase/v1/claims/{primeira}", None, None))
            tarefas2.append((f"messages:{primeira}", f"/post-purchase/v1/claims/{primeira}/messages", None, None))
        mlbs = _mlbs_do_pedido(pedido)
        if mlbs:
            tarefas2.append(("items", "/items", {"ids": ",".join(mlbs), "attributes": ATRIBUTOS_ITEMS}, None))
        sid_ida = (pedido.get("shipping") or {}).get("id")
        if sid_ida:
            tarefas2.append((f"ida_hist:{sid_ida}", f"/shipments/{sid_ida}/history", None, HEADER_FORMATO_NOVO))
            tarefas2.append((f"ida_det:{sid_ida}", f"/shipments/{sid_ida}", None, None))
        onda(executor, tarefas2)

        # Escolha da claim: a 1ª (na ordem da tela) cujo /returns deu certo — igual ao sequencial.
        devolucao = None
        escolhida = None
        antes = []
        for candidata in claims_ordem:
            r_ret = res.get(f"returns:{candidata['id']}")
            if r_ret is not None and r_ret.situacao == "ok":
                devolucao = r_ret.corpo
                escolhida = candidata["id"]
                break
            antes.append(str(candidata["id"]))
        if devolucao is None and claims_ordem:
            escolhida = primeira
            devolucao = {}

        tarefas3 = []
        if escolhida is not None and escolhida != primeira:
            tarefas3.append((f"claim:{escolhida}", f"/post-purchase/v1/claims/{escolhida}", None, None))
            tarefas3.append((f"messages:{escolhida}", f"/post-purchase/v1/claims/{escolhida}/messages", None, None))
        for envio in ((devolucao or {}).get("shipments") or []):
            sid = envio.get("shipment_id")
            if not sid:
                continue
            tarefas3.append((f"volta_hist:{sid}", f"/shipments/{sid}/history", None, HEADER_FORMATO_NOVO))
            tarefas3.append((f"volta_det:{sid}", f"/shipments/{sid}", None, None))
        onda(executor, tarefas3)

    return Execucao(cen, time.perf_counter() - inicio, res, escolhida, segundos_ondas, candidatas_antes=tuple(antes))


def preparar_ambiente(cen):
    if cen.pool:
        ligar_pool()
    else:
        desligar_pool()
    if cen.intervalo_espacador is not None:
        definir_intervalo_espacador(cen.intervalo_espacador)


def teste_3_tela_completa():
    console.rule("[bold]TESTE 3 — A tela inteira: um de cada vez × em ondas[/bold]")
    ativos = [c for c in CENARIOS if T3_RODAR_CENARIOS_ARRISCADOS or not c.arriscado]
    pulados = set()
    if ACHOU_429_NO_TESTE_2:
        pulados = {c.nome for c in ativos if c.arriscado}
        console.print("[bold yellow]O Teste 2 achou 429 — os cenários com espaçador reduzido/desligado NÃO serão rodados.[/bold yellow]\n")
    console.print(
        f"Pedido {NUMERO_PEDIDO} (conta {CONTA}). {len(ativos)} cenário(s) × {T3_REPETICOES} repetição(ões), "
        f"ordem alternada a cada repetição. Cada cenário refaz TODAS as chamadas da tela.\n"
    )

    execucoes = {c.nome: [] for c in ativos}
    for repeticao in range(T3_REPETICOES):
        deslocamento = repeticao % len(ativos)
        ordem = ativos[deslocamento:] + ativos[:deslocamento]
        for cen in ordem:
            if cen.nome in pulados:
                continue
            preparar_ambiente(cen)
            antes_429 = CONTADOR_429.total
            execucao = rodar_em_ondas(cen) if cen.paralelo else rodar_sequencial(cen)
            execucao.n_429 = CONTADOR_429.total - antes_429
            execucoes[cen.nome].append(execucao)
            console.print(
                f"  rep {repeticao + 1}/{T3_REPETICOES} · {cen.nome}: {fmt_s(execucao.segundos)} "
                f"({len(execucao.resultados)} chamadas, 429: {execucao.n_429})"
            )
            verificar_freio()
            if execucao.n_429 > 0:
                for outro in ativos:
                    if outro.paralelo and (outro.intervalo_espacador or 0) <= (cen.intervalo_espacador or 0):
                        pulados.add(outro.nome)
                console.print(f"  [yellow]429 em '{cen.nome}': cenários igualmente ou mais agressivos saem das próximas rodadas.[/yellow]")
            time.sleep(T3_PAUSA_ENTRE_CENARIOS_SEGUNDOS)
    desligar_pool()
    console.print()
    relatorio_teste_3(ativos, execucoes)


def relatorio_teste_3(ativos, execucoes):
    base_nome = ativos[0].nome
    base_execucoes = [e for e in execucoes[base_nome] if e.resultados.get("orders") and e.resultados["orders"].situacao == "ok"]
    if not base_execucoes:
        console.print("[bold red]O cenário 'como é hoje' não conseguiu nem buscar o pedido — sem base pra comparar.[/bold red]")
        for nome, lista in execucoes.items():
            for e in lista[:1]:
                erro = e.resultados.get("orders")
                console.print(f"  {nome}: {escape(erro.texto_erro) if erro else 'sem resultado'}")
        return
    dados_base = base_execucoes[0].dados_chave()
    media_base = statistics.mean(e.segundos for e in base_execucoes)

    t = tabela("Tempo da tela inteira por cenário", [
        ("Cenário", "left"), ("Rodadas", "right"), ("Média", "right"), ("Menor–maior (s)", "right"),
        ("Chamadas", "right"), ("429", "right"), ("Ganho", "right"), ("Mesmo dado?", "left"),
    ])
    for cen in ativos:
        lista = execucoes[cen.nome]
        if not lista:
            t.add_row(cen.nome, "0", "—", "—", "—", "—", "—", "[yellow]não rodou[/yellow]")
            continue
        tempos = [e.segundos for e in lista]
        media = statistics.mean(tempos)
        divergentes = []
        for e in lista:
            dados = e.dados_chave()
            for rotulo in sorted(set(dados) | set(dados_base)):
                if dados.get(rotulo) != dados_base.get(rotulo):
                    divergentes.append(rotulo)
        identico = "[green]sim[/green]" if not divergentes else "[red]NÃO: " + escape(", ".join(sorted(set(divergentes))[:3])) + "[/red]"
        t.add_row(
            cen.nome, str(len(lista)), fmt_s(media), f"{min(tempos):.2f}–{max(tempos):.2f}".replace(".", ","),
            f"{statistics.mean(len(e.resultados) for e in lista):.0f}", str(sum(e.n_429 for e in lista)),
            "—" if cen.nome == base_nome else f"{media_base / media:.1f}x".replace(".", ","), identico,
        )
    console.print(t)

    # Onde o tempo vai hoje (cenário 1) — média por tipo de chamada
    por_tipo = {}
    for e in base_execucoes:
        for rotulo, r in e.resultados.items():
            por_tipo.setdefault(rotulo.partition(":")[0], []).append(r.segundos)
    t2 = tabela("Onde o tempo vai hoje (média por tipo de chamada; inclui a espera do espaçador)", [
        ("Tipo de chamada", "left"), ("Qtd/rodada", "right"), ("Média", "right"),
    ])
    for tipo, lista in sorted(por_tipo.items(), key=lambda kv: -statistics.mean(kv[1])):
        t2.add_row(tipo, f"{len(lista) / len(base_execucoes):.1f}".replace(".", ","), fmt_ms(statistics.mean(lista)))
    console.print(t2)

    # Tempo de cada onda nos cenários paralelos
    t3 = tabela("Tempo de cada onda (cenários em ondas)", [
        ("Cenário", "left"), ("Onda 1", "right"), ("Onda 2", "right"), ("Onda 3", "right"),
    ])
    for cen in ativos:
        if not cen.paralelo or not execucoes[cen.nome]:
            continue
        colunas = []
        for indice in range(3):
            valores = [e.segundos_ondas[indice] for e in execucoes[cen.nome] if len(e.segundos_ondas) > indice]
            colunas.append(fmt_s(statistics.mean(valores)) if valores else "—")
        t3.add_row(cen.nome, *colunas)
    console.print(t3)

    # O /users/me pode sair? O USER_ID do .env tem que bater com o do ML.
    id_ml = None
    for e in base_execucoes:
        r = e.resultados.get("users_me")
        if r is not None and r.situacao == "ok":
            id_ml = (r.corpo or {}).get("id")
            break
    id_env = os.getenv(f"{CONTA}_USER_ID")
    if id_ml is None:
        console.print("[yellow]Não consegui ler /users/me — não deu pra conferir o USER_ID do .env.[/yellow]")
    elif id_env is None:
        console.print(f"[yellow]{CONTA}_USER_ID não foi encontrado no ambiente/.env — não dá pra confirmar se /users/me pode sair da tela.[/yellow]")
    elif str(id_env) == str(id_ml):
        console.print(f"[green]{CONTA}_USER_ID do .env bate com /users/me ({id_ml}) — dá pra tirar essa chamada da tela.[/green]")
    else:
        console.print(f"[bold red]{CONTA}_USER_ID do .env ({id_env}) NÃO bate com /users/me ({id_ml}) — não tirar a chamada antes de resolver isso.[/bold red]")

    # Leitura rápida
    console.print("\n[bold]Leitura rápida[/bold]")
    for cen in ativos[1:]:
        lista = execucoes[cen.nome]
        if lista:
            media = statistics.mean(e.segundos for e in lista)
            ganho = f"{media_base / media:.1f}x".replace(".", ",")
            console.print(f"  • {cen.nome}: {fmt_s(media)} (hoje: {fmt_s(media_base)}) → {ganho}")
    console.print()


# ───────────────────────── Principal ─────────────────────────

def main():
    inicio_geral = time.perf_counter()
    console.print("[bold]Teste de paralelismo — tela Consultar Pedido[/bold]")
    console.print(
        f"Conta {CONTA} · pedido {NUMERO_PEDIDO} · só leitura (GET) · limite de segurança: "
        f"{LIMITE_DE_429_PARA_ABORTAR} avisos de 429\n"
    )
    if CONFIRMAR_ANTES_DE_COMECAR:
        console.print(
            "[bold yellow]Antes de começar:[/bold yellow] a Ana está FORA do sistema e não há coleta em massa do "
            "Sistema Interno V2 rodando? (o limite do ML é por aplicativo, os dois dividiriam a mesma cota)"
        )
        input("Enter para começar (Ctrl+C cancela)... ")

    PASTA_LOGS.mkdir(parents=True, exist_ok=True)
    # Pré-aquece o logger ANTES de criar threads (se 2 threads criassem o logger
    # ao mesmo tempo, os handlers poderiam duplicar) e engancha o contador de 429.
    logger = _configurar_logger(PASTA_LOGS, NOME_LOG)
    logger.addHandler(CONTADOR_429)
    intervalo_original = cliente_api._espacador._intervalo_minimo

    try:
        obter_token_valido(CONTA)    # aquece o token ANTES das threads (renovação concorrente é um risco)
        chamar("aquecimento", "/users/me", espaca=False)   # DNS/primeira conexão: não entra em nenhuma medida
        verificar_freio()
        if RODAR_TESTE_1_POOL:
            teste_1_pool()
        if RODAR_TESTE_2_LIMITE_SIMULTANEO:
            teste_2_limite_simultaneo()
        if RODAR_TESTE_3_TELA_COMPLETA:
            teste_3_tela_completa()
        console.rule("[bold]Fim[/bold]")
        console.print(
            f"Duração total: {fmt_s(time.perf_counter() - inicio_geral)} · avisos de 429 no total: {CONTADOR_429.total}\n"
            f"Log detalhado de cada chamada: {PASTA_LOGS / (NOME_LOG + '.log')}"
        )
    except FreioDeSeguranca as motivo:
        console.print(f"\n[bold yellow]Parei por segurança:[/bold yellow] {escape(str(motivo))}")
        console.print(
            "[dim]O que já foi medido está acima. Pra repetir: espere alguns minutos e rode de novo, "
            "ou desligue os testes que já terminaram (RODAR_TESTE_... lá em cima).[/dim]"
        )
    except FalhaAutenticacao as erro:
        console.print(f"\n[bold red]Falha de autenticação:[/bold red] {escape(str(erro))}")
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Interrompido (Ctrl+C) — desfazendo as mudanças em memória.[/bold yellow]")
    except Exception:  # noqa: BLE001 — qualquer erro inesperado: mostra, desfaz as mudanças e salva o relatório
        console.print("\n[bold red]Erro inesperado no script:[/bold red]")
        console.print_exception()
    finally:
        restaurar_transporte_original()
        definir_intervalo_espacador(intervalo_original)
        logger.removeHandler(CONTADOR_429)
        try:
            console.save_text(str(ARQUIVO_RELATORIO))
            print(f"\nRelatório salvo em: {ARQUIVO_RELATORIO}")
        except OSError as erro:
            print(f"\nNão consegui salvar o relatório: {erro}")


if __name__ == "__main__":
    main()
