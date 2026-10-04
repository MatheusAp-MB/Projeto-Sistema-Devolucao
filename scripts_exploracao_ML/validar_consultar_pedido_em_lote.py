# scripts_exploracao_ML/validar_consultar_pedido_em_lote.py
#
# Função Objetivo: Provar, com dado real, se a tela Consultar Pedido está pronta para TODAS as
# devoluções que a Ana já cadastrou (os 2 bancos, MB e SV). Roda a view REAL
# (integracao_mercado_livre.views.view_consultar_pedido — a mesma que a Ana usa, com as 3 ondas
# paralelas) uma devolução de cada vez e confere, para cada uma:
#
#   1. A tela abre sem erro?  (exceção na view, falha ao montar o HTML, mensagem de erro na tela)
#   2. O resultado é ESTÁVEL?  Cada devolução é consultada N vezes (padrão 2) e o resultado precisa
#      ser idêntico — se mudar de uma vez para outra, as threads das ondas paralelas estão
#      disputando alguma coisa.
#   3. A tela bate com o que a Ana cadastrou?  Datas, claim, tipo de venda, nome do cliente, preço
#      e SKU. (Divergência NÃO quer dizer erro da tela: pode ser digitação da Ana ou o ML
#      divergindo dela — a lista serve para você olhar caso a caso.)
#   4. Os blocos vieram completos?  Foto do anúncio, histórico de envio, devolução física,
#      conversa da mediação.
#   5. Houve 429 ou erro de HTTP inesperado?  (O 404 de /returns, que o ML devolve quando a claim
#      não tem devolução, é esperado e não conta.)
#   6. Quanto tempo leva, e onde?  Chamadas ao ML, banco de dados e montagem do HTML.
#   7. Se a Ana CRIASSE a devolução agora pelo botão "Criar devolução", o formulário viria preenchido
#      certo?  O script segue o botão até a view REAL da Nova devolução, lê os campos do HTML que ela
#      devolveria (o que o navegador mostraria) e compara cada um com o cadastro: igual, parecido,
#      diferente, vazio, formato ilegível. Também simula a busca de produto por SKU que a página dispara
#      sozinha e confere em qual aba (Aguardando Conferência / Mediações Abertas / Encerradas) a
#      devolução nasceria. O relatório ainda mostra, campo a campo, o que é automático e o que é manual.
#      Desde 04/10/2026 o formulário também confere: (a) o PRODUTO que o botão já marca sozinho quando o
#      SKU do anúncio é igual ao SKU do produto cadastrado, ou o EAN do anúncio é igual ao código de
#      barras (e mostra quantas vezes o ML trouxe o EAN); (b) as FOTOS DO CLIENTE que o botão leva do
#      chat da reclamação. As datas de abertura e de finalização da mediação são MANUAIS (o botão não
#      leva nenhuma): toda devolução nova nasce em "Aguardando Conferência".
#
# Só leitura: SELECT no banco e GET na API do ML. Nada é gravado no banco. A simulação do formulário
# (item 7) não faz POST, não salva nada e não faz chamadas extras ao ML: reaproveita o que a consulta
# já trouxe; só a busca de produto lê (SELECT) a tabela de produtos. A ÚNICA exceção é a opção
# --baixar-fotos: ela baixa de verdade (GET) cada foto do cliente que o botão levaria, do jeito que a
# Nova devolução fará ao salvar, só para provar que o ML entrega — nada é guardado em disco nem no banco.
#
# Cota do ML: o app é o MESMO do Sistema Interno V2 (cota de 18.000 chamadas/hora dividida entre
# os dois). Cada consulta faz ~10 chamadas; o script avisa a estimativa antes de começar.
# Os tempos aqui são com as conexões "quentes" (as consultas saem uma atrás da outra); na vida
# real a Ana costuma pegar conexões frias, o que soma ~0,5 s a mais por consulta.
#
# Rodar da raiz do projeto, com o ambiente virtual ativo:
#   python scripts_exploracao_ML/validar_consultar_pedido_em_lote.py --listar          (só mostra o plano, sem chamar a API)
#   python scripts_exploracao_ML/validar_consultar_pedido_em_lote.py --pedido 2000018229470186
#   python scripts_exploracao_ML/validar_consultar_pedido_em_lote.py --limite 5        (teste curto)
#   python scripts_exploracao_ML/validar_consultar_pedido_em_lote.py                   (todas as devoluções)
#   python scripts_exploracao_ML/validar_consultar_pedido_em_lote.py --conta SV --repeticoes 1
#   python scripts_exploracao_ML/validar_consultar_pedido_em_lote.py --sem-formulario  (pula o item 7)
#   python scripts_exploracao_ML/validar_consultar_pedido_em_lote.py --pedido 2000018229470186 --repeticoes 1 --baixar-fotos
#
# Saídas:
#   scripts_exploracao_ML/logs/validar_consultar_pedido_em_lote_relatorio.txt   (o que aparece na tela)
#   scripts_exploracao_ML/validacao_consultar_pedido_em_lote.json               (detalhe de cada devolução)

import argparse
import json
import os
import re
import statistics
import sys
import threading
import time
import traceback
import unicodedata
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

# ─── Prepara o Django (mesmo bootstrap dos outros scripts de exploração) ─
_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projeto_sistema_devolucao_mb_sv.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import AnonymousUser  # noqa: E402
from django.db import connections  # noqa: E402
from django.http import HttpResponse  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.utils import timezone  # noqa: E402
from rich import box  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.markup import escape  # noqa: E402
from rich.table import Table  # noqa: E402

from api_mercado_livre.core.estrutura_api import cliente_api  # noqa: E402
from core import imagens as imagens_do_sistema  # noqa: E402
from core.empresa import definir_empresa_ativa  # noqa: E402
from devolucoes import views as views_devolucoes  # noqa: E402
from devolucoes.models import Devolucao, FotoReclamacaoCliente  # noqa: E402
from integracao_mercado_livre import views as views_ml  # noqa: E402

# ─── Configurações ────────────────────────────────────────────────────────
PASTA_DO_SCRIPT = Path(__file__).resolve().parent
PASTA_LOGS = PASTA_DO_SCRIPT / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
ARQUIVO_RELATORIO = PASTA_LOGS / "validar_consultar_pedido_em_lote_relatorio.txt"
ARQUIVO_JSON = PASTA_DO_SCRIPT / "validacao_consultar_pedido_em_lote.json"

URL_CONSULTAR_PEDIDO = "/mercado-livre/consultar-pedido/"
BANCO_POR_CONTA = {"MB": "magazine", "SV": "samvale"}
EMPRESA_POR_CONTA = {conta: empresa for empresa, conta in views_ml.CONTA_POR_EMPRESA.items()}

REPETICOES_PADRAO = 2
PAUSA_PADRAO_SEGUNDOS = 1.0
CHAMADAS_POR_CONSULTA = 10  # medido no api.log real em 04/10/2026 (1 pedido, 1 claim)
COTA_DO_APP_POR_HORA = 18000

# Devoluções criadas a partir desta data podem ter vindo PRÉ-PREENCHIDAS pelo botão
# "Criar devolução" da própria Consultar Pedido (ponte de 18/09/2026) — nesses casos, "bater
# com o cadastro" é esperado e prova menos.
DATA_INICIO_PONTE = date(2026, 9, 18)

# Pares (ponto da linha do tempo da tela, campo do cadastro da Ana, apelido pra mensagem).
PARES_DE_DATAS = [
    ("Venda", "data_venda", "venda"),
    ("Recebido (cliente)", "data_recebimento_cliente", "recebido pelo cliente"),
    ("Reclamação aberta", "data_reclamacao_cliente", "reclamação aberta"),
    ("Recebido (nós)", "data_recebimento_por_nos", "recebido por nós"),
    ("Mediação aberta", "data_abertura_mediacao", "mediação aberta"),
    ("Mediação encerrada", "data_finalizacao_mediacao", "mediação encerrada"),
]

# 404 em /returns é a resposta normal do ML para "essa claim não tem devolução física".
PADRAO_404_ESPERADO = re.compile(r"/post-purchase/v2/claims/\{id\}/returns$")
MAXIMO_ITENS_POR_CASO_NA_TELA = 8

console = Console(record=True)


# ─── Utilitários pequenos ─────────────────────────────────────────────────

def _rotular_endpoint(url):
    """Tira o domínio e troca todo ID longo por {id}, para agrupar chamadas do mesmo tipo."""
    caminho = re.sub(r"^https?://[^/]+", "", str(url))
    return re.sub(r"/\d{6,}", "/{id}", caminho)


def _sem_acentos(texto):
    decomposto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(letra for letra in decomposto if not unicodedata.combining(letra))


def _normalizar_nome(texto):
    return " ".join(_sem_acentos(texto).casefold().split())


def _dia_br(valor):
    return valor.strftime("%d/%m/%Y") if valor else None


def _segundos(valor):
    return "—" if valor is None else f"{valor:.2f}".replace(".", ",")


def _media(valores):
    valores = [valor for valor in valores if valor is not None]
    return statistics.fmean(valores) if valores else None


def _percentil(valores, fracao):
    valores = sorted(valor for valor in valores if valor is not None)
    if not valores:
        return None
    posicao = min(len(valores) - 1, max(0, int(round(fracao * (len(valores) - 1)))))
    return valores[posicao]


def _resumir_texto(texto, limite=140):
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


# ─── Espiões: o que mede, sem mudar nada no sistema ─────────────────────────

class Instrumentos:
    """Liga, enquanto o script roda, 2 'espiões' que só observam (nada do sistema é alterado
    em disco; ao sair, os originais são recolocados):

      * um em cliente_api._enviar_requisicao — o ÚNICO ponto que faz HTTP de verdade — que anota
        cada chamada (endereço, status, duração, thread);
      * um em views_ml.render — guarda o contexto que a view montou e mede quanto leva para
        montar o HTML (template). Se a montagem do HTML falhar, anota o erro.
    """

    def __init__(self, medir_render=True):
        self.medir_render = medir_render
        self._trava = threading.Lock()
        self._enviar_original = None
        self._render_original = None
        self.zerar()

    def zerar(self):
        with self._trava:
            self.chamadas_http = []
        self.contexto_capturado = None
        self.template_capturado = None
        self.segundos_render = None
        self.erro_render = None

    def __enter__(self):
        self._enviar_original = cliente_api._enviar_requisicao
        self._render_original = views_ml.render
        cliente_api._enviar_requisicao = self._enviar_espiao
        views_ml.render = self._render_espiao
        return self

    def __exit__(self, *_):
        cliente_api._enviar_requisicao = self._enviar_original
        views_ml.render = self._render_original

    def renderizar_de_verdade(self, request, template, contexto):
        """Monta o HTML com o render original, sem passar pelo espião (não mexe no contexto capturado nem nos tempos)."""
        return self._render_original(request, template, contexto)

    def _enviar_espiao(self, metodo, url, **kwargs):
        inicio = time.perf_counter()
        status = None
        try:
            resposta = self._enviar_original(metodo, url, **kwargs)
            status = resposta.status_code
            return resposta
        except Exception as erro:
            status = f"exceção {type(erro).__name__}"
            raise
        finally:
            fim = time.perf_counter()
            with self._trava:
                self.chamadas_http.append({
                    "endpoint": _rotular_endpoint(url),
                    "status": status,
                    "inicio": inicio,
                    "fim": fim,
                    "segundos": fim - inicio,
                    "thread": threading.current_thread().name,
                })

    def _render_espiao(self, request, template, contexto):
        self.contexto_capturado = contexto
        self.template_capturado = template
        if not self.medir_render:
            return HttpResponse("")
        inicio = time.perf_counter()
        try:
            return self._render_original(request, template, contexto)
        except Exception as erro:
            self.erro_render = f"{type(erro).__name__}: {erro}"
            return HttpResponse("", status=500)
        finally:
            self.segundos_render = time.perf_counter() - inicio


# ─── Banco: o que a Ana cadastrou (só leitura) ────────────────────────────────

def _foto_do_cadastro(devolucao):
    """Os campos do formulário 'Nova devolução' como a Ana cadastrou (as datas já estão em "datas")."""
    reembolsado = devolucao.reembolsado
    return {
        "nome_plataforma": devolucao.nome_plataforma or "",
        "tipo_venda": devolucao.tipo_venda or "",
        "numero_pedido": devolucao.numero_pedido or "",
        "numero_nota_fiscal": devolucao.numero_nota_fiscal or "",
        "nome_cliente": devolucao.nome_cliente or "",
        "preco_produto": float(devolucao.preco_produto) if devolucao.preco_produto is not None else None,
        "reembolsado": "sim" if reembolsado is True else "nao" if reembolsado is False else "",
        "valor_reembolsado": float(devolucao.valor_reembolsado) if devolucao.valor_reembolsado is not None else None,
        "anotacao_mediacao": devolucao.anotacao_mediacao or "",
        "motivo_reclamacao": devolucao.motivo_reclamacao or "",
    }


def carregar_devolucoes(contas, pedido_unico=None, limite=None):
    devolucoes = []
    for conta in contas:
        consulta = (
            Devolucao.objects.using(BANCO_POR_CONTA[conta])
            .select_related("produto").order_by("id")
        )
        # Fotos do cliente que a Ana já anexou, por devolução (1 SELECT por conta; sempre no banco da conta certa).
        fotos_por_devolucao = Counter(
            FotoReclamacaoCliente.objects.using(BANCO_POR_CONTA[conta]).values_list("devolucao_id", flat=True)
        )
        if pedido_unico:
            consulta = consulta.filter(numero_pedido=pedido_unico)
        for devolucao in consulta:
            criado_em = devolucao.criado_em
            if criado_em is not None and timezone.is_aware(criado_em):
                criado_em = timezone.localtime(criado_em)
            devolucoes.append({
                "conta": conta,
                "empresa": EMPRESA_POR_CONTA[conta],
                "id": devolucao.id,
                "numero_pedido": devolucao.numero_pedido,
                "claim_id": devolucao.claim_id or None,
                "tipo_venda": devolucao.tipo_venda,
                "nome_cliente": devolucao.nome_cliente,
                "preco_produto": float(devolucao.preco_produto) if devolucao.preco_produto is not None else None,
                "produto_id": devolucao.produto_id,
                "produto_sku": devolucao.produto.sku if devolucao.produto else None,
                "produto_nome": devolucao.produto.nome if devolucao.produto else None,
                "fotos_cliente_cadastradas": fotos_por_devolucao.get(devolucao.id, 0),
                "criada_pela_ponte": bool(criado_em and criado_em.date() >= DATA_INICIO_PONTE),
                "datas": {campo: getattr(devolucao, campo) for _, campo, _ in PARES_DE_DATAS},
                "_cadastro": _foto_do_cadastro(devolucao),
            })
    if limite:
        devolucoes = devolucoes[:limite]
    return devolucoes


# ─── 1 consulta = 1 execução da view real ────────────────────────────────────

def executar_consulta(instrumentos, fabrica_de_requisicoes, devolucao):
    instrumentos.zerar()
    definir_empresa_ativa(devolucao["empresa"])  # o que o EmpresaMiddleware faz numa requisição real
    requisicao = fabrica_de_requisicoes.get(
        URL_CONSULTAR_PEDIDO, {"numero_pedido": devolucao["numero_pedido"]}, HTTP_HOST="127.0.0.1",
    )
    requisicao.user = AnonymousUser()

    excecao = None
    inicio = time.perf_counter()
    with ExitStack() as pilha:
        # Só o banco da empresa da devolução (o mesmo que o EmpresaRouter usa na view real);
        # abrir captura nos outros bancos forçaria uma conexão desnecessária com cada um.
        capturas = [pilha.enter_context(CaptureQueriesContext(connections[BANCO_POR_CONTA[devolucao["conta"]]]))]
        try:
            views_ml.view_consultar_pedido(requisicao)
        except Exception:
            excecao = traceback.format_exc()
    segundos_total = time.perf_counter() - inicio

    consultas_banco = [consulta for captura in capturas for consulta in captura.captured_queries]
    segundos_banco = sum(float(consulta.get("time", 0) or 0) for consulta in consultas_banco)
    return {
        "segundos_total": segundos_total,
        "segundos_render": instrumentos.segundos_render,
        "erro_render": instrumentos.erro_render,
        "excecao": excecao,
        "segundos_banco": segundos_banco,
        "consultas_banco": len(consultas_banco),
        "chamadas_http": list(instrumentos.chamadas_http),
        "contexto": instrumentos.contexto_capturado,
        "template": instrumentos.template_capturado,
    }


# ─── Análise de 1 execução ─────────────────────────────────────────────────

def resumir_http(chamadas):
    """Contagens e tempos das chamadas ao ML de uma execução."""
    n_429 = sum(1 for chamada in chamadas if chamada["status"] == 429)
    inesperadas = []
    for chamada in chamadas:
        status = chamada["status"]
        if status == 200 or status == 429:
            continue
        if status == 404 and PADRAO_404_ESPERADO.search(chamada["endpoint"]):
            continue
        inesperadas.append(f"{status} em {chamada['endpoint']}")
    janela = None
    soma = sum(chamada["segundos"] for chamada in chamadas)
    if chamadas:
        janela = max(chamada["fim"] for chamada in chamadas) - min(chamada["inicio"] for chamada in chamadas)
    return {
        "chamadas": len(chamadas),
        "n_429": n_429,
        "inesperadas": inesperadas,
        "janela_segundos": janela,
        "soma_segundos": soma,
        "threads_usadas": len({chamada["thread"] for chamada in chamadas}),
    }


def comparar_com_cadastro(contexto, devolucao):
    """Lista o que a TELA mostra e o CADASTRO da Ana diz diferente. Divergência não é erro
    da tela: pode ser digitação da Ana, ou o ML que mudou — serve para olhar caso a caso."""
    divergencias = []

    # ----- datas da linha do tempo -----
    datas_da_tela = {passo.get("rotulo"): passo for passo in (contexto.get("datas_do_caso") or [])}
    for rotulo, campo, apelido in PARES_DE_DATAS:
        passo = datas_da_tela.get(rotulo)
        if passo is None:
            divergencias.append({"tipo": f"data:{rotulo}", "texto": f"a tela não trouxe o ponto '{rotulo}' da linha do tempo"})
            continue
        na_tela = passo.get("data")
        no_cadastro = _dia_br(devolucao["datas"].get(campo))
        if na_tela == no_cadastro:
            continue
        if no_cadastro and not na_tela:
            divergencias.append({"tipo": f"data:{rotulo}", "texto": (
                f"{apelido}: a tela está sem data ({passo.get('sem_registro')}), o cadastro tem {no_cadastro}")})
        elif na_tela and not no_cadastro:
            divergencias.append({"tipo": f"data:{rotulo}", "texto": f"{apelido}: a tela tem {na_tela}, o cadastro está vazio"})
        else:
            divergencias.append({"tipo": f"data:{rotulo}", "texto": f"{apelido}: a tela diz {na_tela}, o cadastro diz {no_cadastro}"})

    # ----- claim -----
    if devolucao["claim_id"] and str(contexto.get("claim_id") or "") != str(devolucao["claim_id"]):
        divergencias.append({"tipo": "claim", "texto": (
            f"claim: a tela usou {contexto.get('claim_id')}, o cadastro guarda {devolucao['claim_id']}")})

    # ----- tipo de venda (FULL / comum) -----
    sugerido = contexto.get("tipo_venda_sugerido") or ""
    if not sugerido:
        divergencias.append({"tipo": "tipo_venda", "texto": f"tipo de venda: a tela não sugeriu nenhum, o cadastro diz '{devolucao['tipo_venda']}'"})
    elif sugerido != devolucao["tipo_venda"]:
        divergencias.append({"tipo": "tipo_venda", "texto": f"tipo de venda: a tela sugere '{sugerido}', o cadastro diz '{devolucao['tipo_venda']}'"})

    # ----- nome do cliente -----
    nome_na_tela = contexto.get("nome_comprador") or ""
    if _normalizar_nome(nome_na_tela) != _normalizar_nome(devolucao["nome_cliente"]):
        divergencias.append({"tipo": "nome", "texto": f"nome: a tela diz '{nome_na_tela}', o cadastro diz '{devolucao['nome_cliente']}'"})

    # ----- preço (só quando a tela devolve o preço de 1 item e o cadastro tem preço) -----
    preco_na_tela = contexto.get("preco_produto_input") or ""
    if preco_na_tela and devolucao["preco_produto"] is not None:
        try:
            if abs(float(preco_na_tela) - devolucao["preco_produto"]) > 0.01:
                divergencias.append({"tipo": "preco", "texto": f"preço: a tela diz {preco_na_tela}, o cadastro diz {devolucao['preco_produto']:.2f}"})
        except ValueError:
            divergencias.append({"tipo": "preco", "texto": f"preço: a tela devolveu um valor ilegível ('{preco_na_tela}')"})

    # ----- SKU do anúncio x SKU do produto cadastrado -----
    sku_cadastrado = (devolucao["produto_sku"] or "").strip().casefold()
    skus_da_tela = [str(item.get("sku") or "").strip().casefold() for item in (contexto.get("itens_pedido") or [])]
    if sku_cadastrado and skus_da_tela and sku_cadastrado not in skus_da_tela:
        divergencias.append({"tipo": "sku", "texto": (
            f"SKU: o anúncio traz {', '.join(skus_da_tela)}, o produto cadastrado tem {devolucao['produto_sku']}")})

    return divergencias


def verificar_blocos(contexto):
    """Pontos que merecem atenção na própria tela (independente do cadastro)."""
    atencoes = []
    itens = contexto.get("itens_pedido") or []
    if not itens:
        atencoes.append("a tela não trouxe nenhum item do pedido")
    sem_foto = [item.get("mlb") for item in itens if not item.get("foto_url")]
    if sem_foto:
        atencoes.append(f"item(ns) sem foto do anúncio: {', '.join(map(str, sem_foto))}")
    sem_cadastro = [item.get("sku") for item in itens if not item.get("produto_cadastrado")]
    if sem_cadastro and len(itens) == 1:
        atencoes.append("o único item do pedido não achou produto no cadastro interno")
    if contexto.get("sem_devolucao_fisica"):
        atencoes.append(f"a tela diz que não há devolução física ({_resumir_texto(contexto.get('aviso_sem_devolucao') or '—', 90)})")
    elif not contexto.get("shipments_volta"):
        atencoes.append("há devolução física, mas o envio de volta veio vazio")
    if not contexto.get("linha_tempo_ida"):
        atencoes.append("o histórico do envio de ida veio vazio")
    if contexto.get("eh_mediacao") and not contexto.get("mensagens_mediacao"):
        atencoes.append("é mediação, mas a conversa veio vazia")
    for passo in (contexto.get("datas_do_caso") or []):
        tempo_texto = json.dumps(passo.get("tempo"), ensure_ascii=False, default=str)
        if "fora de ordem" in tempo_texto or "antes da entrega" in tempo_texto:
            atencoes.append(f"datas em ordem impossível a partir de '{passo.get('rotulo')}' ({_resumir_texto(tempo_texto, 60)})")
    return atencoes


def analisar_execucao(execucao, devolucao):
    """Transforma 1 execução em: situação, erros (graves), atenções, divergências e números."""
    contexto = execucao["contexto"]
    erros, atencoes, divergencias = [], [], []

    if execucao["excecao"]:
        erros.append("EXCEÇÃO na view: " + _resumir_texto(execucao["excecao"].strip().splitlines()[-1], 200))
    if execucao["erro_render"]:
        erros.append("falha ao montar o HTML: " + _resumir_texto(execucao["erro_render"], 200))
        atencoes.append("(a falha de HTML pode ser limite do script — a Ana usa a tela de verdade com sessão e mensagens)")

    http = resumir_http(execucao["chamadas_http"])
    if http["n_429"]:
        atencoes.append(f"{http['n_429']}× 429 do Mercado Livre (o sistema esperou e tentou de novo)")
    for texto in http["inesperadas"]:
        atencoes.append("resposta HTTP inesperada: " + texto)

    if contexto is None:
        situacao = "sem_resposta"
        if not execucao["excecao"]:
            erros.append("a view terminou sem chamar render (nenhum contexto capturado)")
    elif contexto.get("erro"):
        situacao = "erro_na_tela"
        erros.append("a tela mostrou erro: " + _resumir_texto(contexto["erro"], 200))
    elif contexto.get("encontrado"):
        situacao = "detalhe"
        divergencias = comparar_com_cadastro(contexto, devolucao)
        atencoes.extend(verificar_blocos(contexto))
    elif contexto.get("lista_pedidos"):
        situacao = "lista"
        atencoes.append(f"o número caiu numa lista de desambiguação ({contexto.get('veio_de')}), não no detalhe do pedido")
    else:
        situacao = "sem_detalhe"
        erros.append("a tela não chegou ao detalhe do pedido e não explicou por quê")

    return {
        "situacao": situacao,
        "erros": erros,
        "atencoes": atencoes,
        "divergencias": divergencias,
        "http": http,
    }


def _assinatura_por_chave(contexto):
    if contexto is None:
        return None
    return {
        chave: json.dumps(valor, sort_keys=True, ensure_ascii=False, default=str)
        for chave, valor in contexto.items()
    }


def comparar_estabilidade(execucoes):
    """Compara a 1ª execução com cada uma das seguintes; devolve as chaves que mudaram."""
    base = _assinatura_por_chave(execucoes[0]["contexto"])
    if base is None:
        return []
    mudancas = []
    for numero, execucao in enumerate(execucoes[1:], start=2):
        outra = _assinatura_por_chave(execucao["contexto"])
        if outra is None:
            mudancas.append(f"a execução {numero} não gerou contexto (a 1ª gerou)")
            continue
        for chave in sorted(set(base) | set(outra)):
            if base.get(chave) != outra.get(chave):
                mudancas.append(
                    f"execução {numero}, campo '{chave}': {_resumir_texto(base.get(chave), 70)} → {_resumir_texto(outra.get(chave), 70)}"
                )
    return mudancas


# ─── Simulação do botão "Criar devolução": o formulário viria preenchido certo? ──────

# Os campos do formulário "Nova devolução": (campo, rótulo, modo, obrigatório no servidor, por quê).
#   automático = o botão "Criar devolução" da Consultar Pedido leva o valor e o formulário já abre preenchido;
#   manual     = a Ana preenche (só vem pré-preenchido o que sai direto e confiável da API do ML — decisão de
#                18/09/2026, reforçada em 03/10/2026 para abertura da mediação, valor reembolsado e motivo, e em
#                04/10/2026 para a finalização da mediação).
# O "obrigatório" copia a lista de devolucoes/views.py::nova_devolucao (POST). A cada devolução o script
# compara com os `required` do HTML e avisa se um lado for mudado sem o outro.
CAMPOS_DO_FORMULARIO = [
    ("nome_plataforma", "Plataforma", "automático", True,
     "o botão só existe na tela do Mercado Livre, então a view fixa 'Mercado Livre'"),
    ("tipo_venda", "Tipo de venda", "automático", True,
     "sugestão pelo tipo logístico do envio de ida (fulfillment = FULL, o resto = comum), mesma regra do Sistema Interno V2"),
    ("numero_pedido", "Número do pedido", "automático", True,
     "é o número que a Ana acabou de consultar"),
    ("numero_nota_fiscal", "Nota fiscal", "manual", True,
     "decisão de 18/09: só vem pré-preenchido o que sai direto e confiável da API do ML; a NF vem do ERP (a Ana digita ou usa 'Colar linha do ERP')"),
    ("nome_cliente", "Nome do cliente", "automático", True,
     "nome do comprador no pedido do ML"),
    ("preco_produto", "Preço do produto", "automático", False,
     "unit_price do 1º item do pedido (já com desconto); só quando o pedido tem 1 item (pedido da Ana, 19/09)"),
    ("data_venda", "Data da venda", "automático", True,
     "data de criação do pedido no ML"),
    ("data_recebimento_cliente", "Recebido pelo cliente", "automático", True,
     "último evento 'entregue' do envio de ida"),
    ("data_reclamacao_cliente", "Reclamação aberta", "automático", True,
     "data de criação da reclamação no ML"),
    ("data_recebimento_por_nos", "Recebido por nós", "automático", True,
     "chegada do envio de volta, no histórico da devolução física"),
    ("data_abertura_mediacao", "Mediação aberta", "manual", False,
     "é o dia em que a Ana abre a mediação, normalmente DEPOIS de cadastrar a devolução (decisão de 03/10); o botão nem leva esse campo"),
    ("data_finalizacao_mediacao", "Mediação finalizada", "manual", False,
     "decisão de 04/10: é o dia em que a mediação termina e quem marca é a Ana; se o botão levasse o date_closed do ML, "
     "a devolução já nasceria na aba 'Mediações Encerradas'; o botão nem leva esse campo"),
    ("reembolsado", "Reembolsado?", "manual", False,
     "decisão de 18/09 (só pré-preenche o que sai direto e confiável da API); depende da confirmação do ML depois, então começa em 'Ainda não sei'"),
    ("valor_reembolsado", "Valor reembolsado", "manual", False,
     "não existe campo confiável na API; a Ana digita depois que o ML confirma (decisão de 03/10)"),
    ("anotacao_mediacao", "Anotações da mediação", "manual", False,
     "texto livre da Ana"),
    ("motivo_reclamacao", "Motivo da reclamação", "manual", True,
     "vale o que o cliente escreveu, não o código padronizado do ML (decisão de 03/10)"),
]
CAMPO_PRODUTO = ("produto", "Produto", "automático", True,
                 "decisão de 04/10 ('comparar SKU com SKU ou EAN com EAN'): o botão leva o produto_id quando o SKU do anúncio "
                 "é igual ao SKU de 1 produto cadastrado, ou o EAN do anúncio é igual ao código de barras; sem batida, ou com "
                 "conflito (SKU e EAN apontando para produtos diferentes), ou em pedido de 2+ itens, vale a busca pelo SKU e a "
                 "Ana clica no candidato certo")
CAMPO_FOTOS = ("fotos_cliente", "Fotos do cliente", "automático", False,
               "decisão de 04/10 ('já temos acesso a elas'): o botão leva o claim e os nomes dos anexos que o CLIENTE mandou no "
               "chat da reclamação; a Nova devolução mostra as miniaturas (a Ana tira alguma com o X) e baixa as fotos do ML ao salvar")

CAMPOS_DE_DATA = {campo for _, campo, _ in PARES_DE_DATAS}
CAMPOS_DE_PRECO = {"preco_produto", "valor_reembolsado"}
# Quando o formulário diverge do cadastro num destes campos, a comparação da tela (comparar_com_cadastro)
# já mostra a mesma divergência; o relatório não repete a linha.
TIPO_DE_DIVERGENCIA_POR_CAMPO = {campo: f"data:{rotulo}" for rotulo, campo, _ in PARES_DE_DATAS}
TIPO_DE_DIVERGENCIA_POR_CAMPO.update({"tipo_venda": "tipo_venda", "nome_cliente": "nome", "preco_produto": "preco"})

URL_BUSCA_DE_PRODUTO = "/nova-devolucao/buscar-produto/"
MAXIMO_CANDIDATOS_DA_BUSCA = 8  # o mesmo corte de devolucoes/views.py::buscar_produtos_devolucao

ROTULO_DO_ESTADO = {
    "igual": "igual ao cadastro",
    "parecido": "parecido (nome abreviado)",
    "diferente": "diferente do cadastro",
    "falta": "vem vazio, o cadastro tem",
    "so_formulario": "vem preenchido, o cadastro está vazio",
    "vazio": "vazio nos dois",
    "ilegivel": "formato que o navegador ignoraria",
}
ROTULO_DO_ESTADO_DO_PRODUTO = {
    "automatico_certo": "marcado sozinho pelo SKU/EAN, e é o produto do cadastro",
    "automatico_errado": "marcado sozinho pelo SKU/EAN, mas NÃO é o produto do cadastro",
    "marcado_certo": "sem produto_id, mas a busca marcou sozinha (código de barras exato), e é o do cadastro",
    "marcado_errado": "sem produto_id, mas a busca marcou sozinha (código de barras exato) o produto ERRADO",
    "na_lista": "não marcou sozinho; o produto do cadastro aparece na lista (1 clique)",
    "fora_da_lista": "não marcou sozinho; o produto do cadastro não aparece na lista (busca à mão)",
    "sem_busca": "não marcou sozinho e o botão não levou SKU (busca à mão)",
}
ROTULO_DA_ORIGEM_DO_PRODUTO = {
    "sku": "o SKU do anúncio bateu com 1 produto",
    "ean": "o EAN do anúncio bateu com 1 produto (o SKU não)",
    "sku_e_ean": "SKU e EAN batem com o mesmo produto",
    "conflito": "SKU e EAN apontam para produtos DIFERENTES (ou o EAN bate com 2+): não marca nenhum",
    "nenhuma": "nem o SKU nem o EAN bateram com um produto cadastrado",
}
ROTULO_DO_ESTADO_DAS_FOTOS = {
    "igual": "mesma quantidade que o cadastro",
    "so_ml": "o chat do ML tem foto e o cadastro não (viriam sozinhas)",
    "ml_tem_mais": "o chat do ML tem mais fotos que o cadastro (viriam todas)",
    "ml_tem_menos": "o cadastro tem mais fotos que o chat do ML (a Ana anexou outras de outro lugar)",
    "so_cadastro": "o chat do ML não tem foto e o cadastro tem (a Ana anexou de outro lugar)",
    "sem_fotos": "nenhuma foto, nem no chat do ML nem no cadastro",
}

_REGEX_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REGEX_NUMERO_HTML = re.compile(r"^\d+(\.\d+)?$")


class LeitorFormulario(HTMLParser):
    """Lê o HTML da Nova devolução e guarda, por name, o que um navegador mostraria em cada campo:
    input e textarea (o texto), select (a opção marcada; se nenhuma estiver marcada, a 1ª — como o navegador).
    Também guarda o termo de busca de produto que a tela leva (data-busca-sugerida)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.campos = {}
        self.busca_sugerida = None
        self.fotos_ml = []          # nomes dos anexos do chat que a Nova devolução vai importar (um input escondido por foto)
        self.claim_id_fotos = ""
        self._select = None
        self._textarea = None

    def handle_starttag(self, tag, atributos):
        a = dict(atributos)
        if tag == "input":
            if a.get("id") == "nd_produto_busca":
                self.busca_sugerida = a.get("data-busca-sugerida") or ""
            if a.get("name") == "foto_cliente_ml":
                self.fotos_ml.append(a.get("value") or "")
                return
            if a.get("name") == "claim_id_fotos":
                self.claim_id_fotos = a.get("value") or ""
            tipo = (a.get("type") or "text").lower()
            if a.get("name") and tipo not in ("file", "submit", "button", "checkbox", "radio"):
                self.campos[a["name"]] = {"tag": "input", "tipo": tipo, "valor": a.get("value") or "",
                                          "obrigatorio": "required" in a}
        elif tag == "textarea" and a.get("name"):
            self._textarea = a["name"]
            self.campos[self._textarea] = {"tag": "textarea", "tipo": "textarea", "valor": "",
                                           "obrigatorio": "required" in a}
        elif tag == "select" and a.get("name"):
            self._select = a["name"]
            self.campos[self._select] = {"tag": "select", "tipo": "select", "valor": None, "opcoes": [],
                                         "obrigatorio": "required" in a}
        elif tag == "option" and self._select:
            valor = a.get("value") or ""
            campo = self.campos[self._select]
            campo["opcoes"].append(valor)
            if "selected" in a and campo["valor"] is None:
                campo["valor"] = valor

    def handle_endtag(self, tag):
        if tag == "textarea":
            self._textarea = None
        elif tag == "select" and self._select:
            campo = self.campos[self._select]
            if campo["valor"] is None:
                campo["valor"] = campo["opcoes"][0] if campo["opcoes"] else ""
            self._select = None

    def handle_data(self, dado):
        if self._textarea:
            self.campos[self._textarea]["valor"] += dado


def ler_formulario(html):
    leitor = LeitorFormulario()
    leitor.feed(html)
    leitor.close()
    return leitor


def extrair_link_criar_devolucao(html):
    """Acha, no HTML da Consultar Pedido, o endereço do botão 'Criar devolução' — o mesmo que o navegador seguiria."""
    for tag in re.findall(r"<a\b[^>]*>", html):
        if "topo-pedido-botao-principal" not in tag:
            continue
        achado = re.search(r'href="([^"]*)"', tag)
        if achado and "/nova-devolucao/" in achado.group(1):
            return achado.group(1).replace("&amp;", "&")
    return None


class _SemDevolucaoCadastrada:
    """Faz a view da Nova devolução enxergar o pedido como NÃO cadastrado (hoje, para um pedido que já tem
    devolução, ela redireciona para a edição em vez de abrir o formulário). Só o Devolucao.objects.filter(...)
    é trocado, e só enquanto a simulação roda; todo o resto (constantes, choices) vem do model de verdade."""

    class _Objetos:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

        def exists(self):
            return False

    objects = _Objetos()

    def __init__(self, classe_real):
        self._real = classe_real

    def __getattr__(self, nome):
        return getattr(self._real, nome)


def _etapa_pelas_datas(abertura, finalizacao):
    """A aba em que uma devolução NOVA cairia só pelas datas de mediação — mesma ordem de
    Devolucao.status_fluxo (finalizada > aberta > nenhuma). Conferência e impressão ficam de fora porque uma
    devolução recém-criada ainda não tem nenhuma das duas."""
    nomes = dict(Devolucao.STATUS_CHOICES)
    if finalizacao:
        return nomes[Devolucao.STATUS_MEDIACAO_ENCERRADA]
    if abertura:
        return nomes[Devolucao.STATUS_MEDIACAO_ABERTA]
    return nomes[Devolucao.STATUS_AGUARDANDO_CONFERENCIA]


def _data_iso_valida(texto):
    """A data de um <input type=date> (AAAA-MM-DD) ou None; qualquer outro formato o navegador ignora."""
    texto = (texto or "").strip()
    if not _REGEX_DATA_ISO.match(texto):
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _texto_do_cadastro(campo, devolucao):
    """O valor do cadastro da Ana, em texto, no formato que o formulário usaria."""
    if campo in CAMPOS_DE_DATA:
        dia = devolucao["datas"].get(campo)
        return dia.isoformat() if dia else ""
    valor = devolucao["_cadastro"].get(campo)
    if valor is None:
        return ""
    if campo in CAMPOS_DE_PRECO:
        return f"{valor:.2f}"
    return str(valor)


def _nome_cabe_no_outro(curto, longo):
    """True se cada palavra de 'curto' aparece em 'longo' (ou é a inicial de uma palavra de 'longo')."""
    palavras_do_longo = longo.split()
    for palavra in curto.split():
        inicial = palavra.strip(".")
        if not any(outra == palavra or (len(inicial) == 1 and outra.startswith(inicial)) for outra in palavras_do_longo):
            return False
    return True


def comparar_campo_do_formulario(campo, no_formulario, no_cadastro):
    """Compara 1 campo: o que o formulário mostraria x o que está no cadastro. Devolve (estado, detalhe)."""
    no_formulario = (no_formulario or "").strip()
    no_cadastro = (no_cadastro or "").strip()

    if campo in CAMPOS_DE_DATA and no_formulario and _data_iso_valida(no_formulario) is None:
        return "ilegivel", f"valor '{no_formulario}' não é AAAA-MM-DD: o navegador deixaria o campo em branco"
    if campo in CAMPOS_DE_PRECO and no_formulario and not _REGEX_NUMERO_HTML.match(no_formulario):
        return "ilegivel", f"valor '{no_formulario}' tem formato que o campo numérico ignora (precisa de ponto, sem vírgula)"

    if not no_formulario and not no_cadastro:
        return "vazio", ""
    if not no_formulario:
        return "falta", f"vem vazio; o cadastro tem '{_resumir_texto(no_cadastro, 60)}'"
    if not no_cadastro:
        return "so_formulario", f"vem '{_resumir_texto(no_formulario, 60)}'; o cadastro está vazio"

    if campo in CAMPOS_DE_DATA:
        if no_formulario == no_cadastro:
            return "igual", ""
        dias = (date.fromisoformat(no_formulario) - date.fromisoformat(no_cadastro)).days
        return "diferente", (f"vem {_dia_br(date.fromisoformat(no_formulario))}; o cadastro tem "
                             f"{_dia_br(date.fromisoformat(no_cadastro))} ({dias:+d} dia(s))")
    if campo in CAMPOS_DE_PRECO:
        if abs(float(no_formulario) - float(no_cadastro)) <= 0.01:
            return "igual", ""
        return "diferente", f"vem {no_formulario}; o cadastro tem {no_cadastro}"
    if campo == "nome_cliente":
        a, b = _normalizar_nome(no_formulario), _normalizar_nome(no_cadastro)
        if a == b:
            return "igual", ""
        if _nome_cabe_no_outro(a, b) or _nome_cabe_no_outro(b, a):
            return "parecido", f"vem '{no_formulario}'; o cadastro tem '{no_cadastro}'"
        return "diferente", f"vem '{no_formulario}'; o cadastro tem '{no_cadastro}'"
    if no_formulario == no_cadastro:
        return "igual", ""
    return "diferente", f"vem '{_resumir_texto(no_formulario, 60)}'; o cadastro tem '{_resumir_texto(no_cadastro, 60)}'"


def simular_busca_de_produto(fabrica_de_requisicoes, devolucao, termo):
    """Repete o que a JS da Nova devolução faz ao abrir com ?produto_busca=SKU: termo com 2+ caracteres dispara a
    busca (aqui, a view REAL buscar_produtos_devolucao); se vier match_exato com 1 só resultado, o produto é marcado
    sozinho; senão aparecem até 8 candidatos para a Ana clicar. Compara com o produto do cadastro."""
    termo = (termo or "").strip()
    resultado = {"termo": termo, "estado": "sem_busca", "candidatos": 0, "posicao": None, "detalhe": ""}
    if len(termo) < 2:
        resultado["detalhe"] = "o botão não levou SKU (pedido com mais de 1 item, ou anúncio sem SKU)"
        return resultado

    requisicao = fabrica_de_requisicoes.get(URL_BUSCA_DE_PRODUTO, {"q": termo}, HTTP_HOST="127.0.0.1")
    requisicao.user = AnonymousUser()
    dados = json.loads(views_devolucoes.buscar_produtos_devolucao(requisicao).content)
    candidatos = dados.get("resultados") or []
    ids = [candidato.get("id") for candidato in candidatos]
    esperado = devolucao["produto_id"]
    resultado["candidatos"] = len(candidatos)
    cortada = " (lista cortada em 8: pode haver mais)" if len(candidatos) >= MAXIMO_CANDIDATOS_DA_BUSCA else ""

    if dados.get("match_exato") and len(candidatos) == 1:
        if ids[0] == esperado:
            resultado["estado"] = "marcado_certo"
        else:
            resultado["estado"] = "marcado_errado"
            resultado["detalhe"] = (f"o SKU '{termo}' bateu com um código de barras e marcou '{_resumir_texto(candidatos[0].get('nome'), 50)}' "
                                    f"(SKU {candidatos[0].get('sku')}); o cadastro tem o SKU {devolucao['produto_sku']}")
    elif esperado in ids:
        resultado["estado"] = "na_lista"
        resultado["posicao"] = ids.index(esperado) + 1
        resultado["detalhe"] = f"{len(candidatos)} candidato(s); o do cadastro é o {resultado['posicao']}º{cortada}"
    else:
        resultado["estado"] = "fora_da_lista"
        resultado["detalhe"] = (f"a busca por '{termo}' trouxe {len(candidatos)} candidato(s) e nenhum é o produto do cadastro "
                                f"(SKU {devolucao['produto_sku']}){cortada}")
    return resultado


def _item_unico_da_tela(contexto):
    """O item do pedido quando o pedido tem 1 só (só nesse caso o botão marca produto e leva preço/SKU), senão None."""
    itens = (contexto or {}).get("itens_pedido") or []
    return itens[0] if len(itens) == 1 else None


def avaliar_produto_marcado(produto_id_do_html, devolucao, link_parametros):
    """O formulário abriu com um produto JÁ MARCADO (campo escondido produto_id): é o do cadastro da Ana?
    A escolha vem só do SKU/EAN do anúncio do ML, independente de a devolução já existir (o cadastro só entra aqui,
    na comparação)."""
    esperado = devolucao["produto_id"]
    marcado = int(produto_id_do_html) if produto_id_do_html.isdigit() else None
    origem = link_parametros.get("produto_origem", "")
    resultado = {"termo": "", "estado": "automatico_certo" if marcado == esperado else "automatico_errado",
                 "candidatos": 1, "posicao": 1, "detalhe": "", "origem_do_botao": origem}
    if marcado != esperado:
        resultado["detalhe"] = (f"o botão marcou sozinho o produto de id {produto_id_do_html} (batida por "
                                f"'{origem or 'origem não informada'}'); o cadastro da Ana tem o produto de id {esperado} "
                                f"(SKU {devolucao['produto_sku']})")
    return resultado


def baixar_anexo_do_claim(conta, claim_id, nome):
    """O MESMO GET que a Nova devolução faz ao salvar (devolucoes.views._importar_fotos_do_cliente_do_ml). Só leitura:
    devolve (tipo, bytes do arquivo) e não guarda o arquivo em lugar nenhum."""
    resposta = cliente_api.chamar_api(
        "GET", f"/post-purchase/v1/claims/{claim_id}/attachments/{nome}/download",
        pasta_logs=views_ml.PASTA_LOGS_ML, conta=conta,
    )
    tipo = (resposta.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    return tipo, resposta.content


def testar_download_das_fotos(conta, claim_id, nomes):
    """(--baixar-fotos) Baixa cada foto que o formulário vai importar e confere as mesmas regras da importação real:
    o ML precisa devolver imagem JPG/PNG/WEBP/GIF (ou HEIC, que a importação converte em JPEG com o conversor REAL do
    sistema, core.imagens), não vazia e dentro do limite de tamanho (medido depois da conversão)."""
    limite = views_devolucoes.TAMANHO_MAXIMO_FOTO_CLIENTE_ML_BYTES
    resultado = {"tentadas": 0, "ok": 0, "convertidas": 0, "falhas": []}
    for nome in nomes:
        resultado["tentadas"] += 1
        try:
            tipo, conteudo = baixar_anexo_do_claim(conta, claim_id, nome)
        except Exception as erro:
            resultado["falhas"].append({"arquivo": nome, "motivo": f"{type(erro).__name__}: {_resumir_texto(erro, 120)}"})
            continue
        convertida = False
        if imagens_do_sistema.parece_heic(conteudo[:12], tipo, nome):
            try:
                conteudo = imagens_do_sistema.converter_heic_para_jpeg(conteudo)
            except imagens_do_sistema.ConversaoHeicIndisponivel:
                resultado["falhas"].append({"arquivo": nome, "motivo":
                    "a foto é HEIC (iPhone) e o pacote pillow-heif não está instalado nesta máquina "
                    "(instale com: poetry add pillow-heif)"})
                continue
            except Exception as erro:
                resultado["falhas"].append({"arquivo": nome, "motivo":
                    f"a foto é HEIC, mas a conversão para JPEG falhou: {type(erro).__name__}: {_resumir_texto(erro, 120)}"})
                continue
            tipo, convertida = "image/jpeg", True
        tamanho = len(conteudo)
        if tipo not in views_devolucoes.EXTENSAO_POR_TIPO_DE_IMAGEM:
            motivo = f"o ML devolveu '{tipo or 'sem tipo'}', que não é uma imagem aceita (JPG/PNG/WEBP/GIF)"
        elif not tamanho:
            motivo = "o ML devolveu um arquivo vazio"
        elif tamanho > limite:
            motivo = f"o arquivo tem {tamanho / 1024 / 1024:.1f} MB e o limite é {limite // 1024 // 1024} MB"
        else:
            resultado["ok"] += 1
            resultado["convertidas"] += 1 if convertida else 0
            continue
        resultado["falhas"].append({"arquivo": nome, "motivo": motivo})
    return resultado


def avaliar_fotos_do_cliente(devolucao, contexto, leitor, formulario, baixar_fotos):
    """As fotos que o cliente mandou no chat da reclamação: o que a tela achou, o que o formulário vai importar e o que
    a Ana já tem anexado no cadastro (só quantidades). Com baixar_fotos, também testa o download de cada uma."""
    na_tela = list(contexto.get("fotos_cliente_input") or [])
    no_formulario = list(leitor.fotos_ml)
    cadastradas = devolucao.get("fotos_cliente_cadastradas") or 0
    limite = views_devolucoes.LIMITE_FOTOS_CLIENTE_ML
    fotos = {"estado": None, "detalhe": "", "na_tela": len(na_tela), "no_formulario": len(no_formulario),
             "cadastradas": cadastradas, "nomes": no_formulario, "download": None}

    if len(no_formulario) != min(len(na_tela), limite):
        motivo = f"o limite é {limite}" if len(na_tela) > limite else "nome(s) de anexo num formato que o formulário descarta"
        formulario["avisos"].append(
            f"a tela achou {len(na_tela)} foto(s) do cliente no chat da reclamação, mas o formulário só mostra {len(no_formulario)} ({motivo})")
    if no_formulario and leitor.claim_id_fotos != str(contexto.get("claim_id_input") or ""):
        formulario["erros"].append(
            f"o formulário guardou o claim '{leitor.claim_id_fotos}' para as fotos, mas a tela consultou o claim '{contexto.get('claim_id_input')}'")

    quantidade = len(no_formulario)
    if quantidade == 0 and cadastradas == 0:
        fotos["estado"] = "sem_fotos"
    elif quantidade == cadastradas:
        fotos["estado"] = "igual"
    elif cadastradas == 0:
        fotos["estado"] = "so_ml"
    elif quantidade == 0:
        fotos["estado"] = "so_cadastro"
    elif quantidade > cadastradas:
        fotos["estado"] = "ml_tem_mais"
    else:
        fotos["estado"] = "ml_tem_menos"
    fotos["detalhe"] = f"o chat do ML tem {quantidade} foto(s) do cliente; o cadastro da Ana tem {cadastradas}"

    if baixar_fotos and no_formulario:
        fotos["download"] = testar_download_das_fotos(devolucao["conta"], leitor.claim_id_fotos, no_formulario)
    return fotos


def _classificar_formulario(formulario):
    """ERRO (não abriu, ou campo ilegível) > DIFERENTE (valor errado, produto errado ou aba errada) > FALTA (campo
    automático vazio, produto fora da lista, foto que não baixaria) > OK. Campos manuais vazios são o esperado e
    nunca contam."""
    if not formulario["simulado"] and not formulario["erros"]:
        return None  # a tela não chegou ao detalhe: não havia botão para simular
    campos = formulario["campos"]
    produto = formulario["produto"] or {}
    aba = formulario["aba"] or {}
    download = ((formulario.get("fotos") or {}).get("download")) or {}
    if formulario["erros"] or any(item["estado"] == "ilegivel" for item in campos.values()):
        return "ERRO"
    automaticos = [item for item in campos.values() if item["modo"] == "automático"]
    if (any(item["estado"] == "diferente" for item in automaticos)
            or produto.get("estado") in ("marcado_errado", "automatico_errado") or aba.get("estado") == "diferente"):
        return "DIFERENTE"
    if (any(item["estado"] == "falta" for item in automaticos)
            or produto.get("estado") in ("fora_da_lista", "sem_busca") or download.get("falhas")):
        return "FALTA"
    return "OK"


def listar_problemas_do_formulario(formulario, tipos_ja_divergentes=()):
    """Frases curtas, (tipo, texto), sobre o que o formulário traria de estranho — para o relatório."""
    if not formulario:
        return []
    linhas = [("ERRO", texto) for texto in formulario["erros"]]
    for campo, item in formulario["campos"].items():
        if item["estado"] == "ilegivel":
            linhas.append(("ERRO", f"{item['rotulo']}: {item['detalhe']}"))
        elif item["modo"] == "automático" and item["estado"] == "falta":
            linhas.append(("FALTA", f"{item['rotulo']}: {item['detalhe']}"))
        elif (item["modo"] == "automático" and item["estado"] == "diferente"
              and TIPO_DE_DIVERGENCIA_POR_CAMPO.get(campo) not in tipos_ja_divergentes):
            linhas.append(("DIFERENTE", f"{item['rotulo']}: {item['detalhe']}"))
    produto = formulario["produto"] or {}
    if produto.get("estado") in ("marcado_errado", "automatico_errado"):
        linhas.append(("DIFERENTE", f"Produto: {produto['detalhe']}"))
    elif produto.get("estado") in ("fora_da_lista", "sem_busca"):
        linhas.append(("FALTA", f"Produto: {produto['detalhe']}"))
    if produto.get("origem_no_servidor") == "conflito":
        linhas.append(("AVISO", "Produto: o SKU e o EAN do anúncio apontam para produtos diferentes (ou o EAN bate com 2+): "
                                "nenhum foi marcado sozinho"))
    aba = formulario["aba"] or {}
    if aba.get("estado") == "diferente":
        linhas.append(("DIFERENTE", f"a devolução nasceria em '{aba['formulario']}': o botão está levando alguma data de mediação, "
                                    f"que deveria ser manual (o cadastro da Ana implica '{aba['cadastro']}')"))
    fotos = formulario.get("fotos") or {}
    for falha in ((fotos.get("download") or {}).get("falhas") or []):
        linhas.append(("FALTA", f"Foto do cliente '{falha['arquivo']}' não seria importada: {falha['motivo']}"))
    if fotos.get("estado") in ("ml_tem_menos", "so_cadastro"):
        linhas.append(("AVISO", f"Fotos do cliente: {fotos['detalhe']}"))
    linhas.extend(("AVISO", texto) for texto in formulario["avisos"])
    return linhas


def _simular_formulario(instrumentos, fabrica_de_requisicoes, devolucao, execucao, formulario, baixar_fotos=False):
    contexto = execucao["contexto"] if execucao else None
    if execucao and execucao.get("erro_render"):
        formulario["avisos"].append("a tela não montou o HTML (ver o ERRO acima): não há botão 'Criar devolução' para simular")
        return
    if not (contexto and contexto.get("encontrado") and execucao.get("template")):
        formulario["avisos"].append("a tela não chegou ao detalhe do pedido: não há botão 'Criar devolução' para simular")
        return
    definir_empresa_ativa(devolucao["empresa"])

    # 1) A tela Consultar Pedido como se a devolução NÃO existisse (é aí que o botão 'Criar devolução' aparece).
    #    Usa o contexto que a própria consulta já montou: nenhuma chamada nova ao Mercado Livre.
    contexto_sem_cadastro = dict(contexto, devolucao_no_sistema_id=None)
    requisicao = fabrica_de_requisicoes.get(URL_CONSULTAR_PEDIDO, {"numero_pedido": devolucao["numero_pedido"]}, HTTP_HOST="127.0.0.1")
    requisicao.user = AnonymousUser()
    html_da_tela = instrumentos.renderizar_de_verdade(requisicao, execucao["template"], contexto_sem_cadastro).content.decode("utf-8")
    link = extrair_link_criar_devolucao(html_da_tela)
    if not link:
        formulario["erros"].append("o botão 'Criar devolução' não apareceu no HTML da tela, mesmo sem devolução cadastrada")
        return
    formulario["simulado"] = True
    formulario["link_parametros"] = {nome: valores[0] for nome, valores in parse_qs(urlsplit(link).query, keep_blank_values=True).items()}

    # 2) Seguir o botão: a view REAL da Nova devolução (com o 'já existe, abrir a edição' desligado) e o HTML dela.
    requisicao_do_botao = fabrica_de_requisicoes.get(link, HTTP_HOST="127.0.0.1")
    requisicao_do_botao.user = AnonymousUser()
    with mock.patch.object(views_devolucoes, "Devolucao", _SemDevolucaoCadastrada(views_devolucoes.Devolucao)):
        try:
            resposta = views_devolucoes.nova_devolucao(requisicao_do_botao)
        except Exception as erro:
            formulario["erros"].append(f"a Nova devolução falhou ao abrir pelo botão: {type(erro).__name__}: {_resumir_texto(erro, 160)}")
            return
    if resposta.status_code != 200:
        formulario["erros"].append(f"a Nova devolução respondeu {resposta.status_code} em vez de abrir o formulário (redirecionamento?)")
        return

    # 3) O que o navegador mostraria em cada campo.
    leitor = ler_formulario(resposta.content.decode("utf-8"))
    valores_html = {nome: campo["valor"] for nome, campo in leitor.campos.items()}
    formulario["busca_sugerida"] = leitor.busca_sugerida or ""
    nomes_dos_campos = {campo for campo, _, _, _, _ in CAMPOS_DO_FORMULARIO}
    obrigatorios_do_servidor = {campo for campo, _, _, obrigatorio, _ in CAMPOS_DO_FORMULARIO if obrigatorio}
    obrigatorios_do_html = {nome for nome, campo in leitor.campos.items() if campo["obrigatorio"] and nome in nomes_dos_campos}
    if obrigatorios_do_servidor != obrigatorios_do_html:
        formulario["obrigatorios_html_ok"] = False
        formulario["avisos"].append(
            "o HTML e o servidor discordam sobre os campos obrigatórios (só no HTML: "
            f"{sorted(obrigatorios_do_html - obrigatorios_do_servidor)}; só no servidor: {sorted(obrigatorios_do_servidor - obrigatorios_do_html)})")

    for campo, rotulo, modo, _, _ in CAMPOS_DO_FORMULARIO:
        if campo not in valores_html:
            formulario["erros"].append(f"o campo '{campo}' não existe no HTML do formulário")
            continue
        no_formulario = valores_html[campo]
        no_cadastro = _texto_do_cadastro(campo, devolucao)
        estado, detalhe = comparar_campo_do_formulario(campo, no_formulario, no_cadastro)
        if leitor.campos[campo]["tag"] == "select":
            enviado = formulario["link_parametros"].get(campo, "")
            if enviado and enviado != no_formulario:
                detalhe = (detalhe + " " if detalhe else "") + f"(o botão levou '{enviado}', que não é uma opção da lista)"
        formulario["campos"][campo] = {
            "rotulo": rotulo, "modo": modo, "estado": estado, "detalhe": detalhe,
            "formulario": _resumir_texto(no_formulario, 80), "cadastro": _resumir_texto(no_cadastro, 80),
        }

    # 4) O produto: o botão marca sozinho (produto_id) quando o SKU ou o EAN do anúncio bate com 1 produto cadastrado;
    #    senão vale a busca por SKU que a JS da página dispara sozinha.
    item_da_tela = _item_unico_da_tela(contexto)
    try:
        produto_marcado = (valores_html.get("produto_id") or "").strip()
        if produto_marcado:
            formulario["produto"] = avaliar_produto_marcado(produto_marcado, devolucao, formulario["link_parametros"])
        else:
            formulario["produto"] = simular_busca_de_produto(fabrica_de_requisicoes, devolucao, formulario["busca_sugerida"])
        formulario["produto"].update({
            "item_unico": item_da_tela is not None,
            "origem_no_servidor": (item_da_tela or {}).get("produto_auto_origem"),
            "gtins_do_anuncio": list((item_da_tela or {}).get("gtins_anuncio") or []),
        })
    except Exception as erro:
        formulario["erros"].append(f"a conferência do produto falhou: {type(erro).__name__}: {_resumir_texto(erro, 160)}")

    # 5) Em que aba a devolução nasceria? (Devolucao.status_fluxo manda a devolução para 'Mediações Encerradas' assim que
    #    existe uma data de finalização — mesmo sem conferência.) Desde 04/10/2026 as duas datas de mediação são manuais:
    #    o esperado é nascer em 'Aguardando Conferência' (a Ana marca as datas depois e a devolução muda de aba).
    abertura = _data_iso_valida(valores_html.get("data_abertura_mediacao"))
    finalizacao = _data_iso_valida(valores_html.get("data_finalizacao_mediacao"))
    etapa_do_formulario = _etapa_pelas_datas(abertura, finalizacao)
    etapa_do_cadastro = _etapa_pelas_datas(devolucao["datas"].get("data_abertura_mediacao"), devolucao["datas"].get("data_finalizacao_mediacao"))
    if etapa_do_formulario == etapa_do_cadastro:
        estado_da_aba = "igual"
    elif etapa_do_formulario == _etapa_pelas_datas(None, None):
        estado_da_aba = "depois_a_ana_marca"
    else:
        estado_da_aba = "diferente"
    formulario["aba"] = {"formulario": etapa_do_formulario, "cadastro": etapa_do_cadastro, "estado": estado_da_aba}
    if finalizacao and not abertura:
        formulario["avisos"].append("o botão leva a data de finalização da mediação mas não a de abertura: a devolução ficaria 'finalizada' sem nunca ter sido 'aberta'")

    # 6) As fotos que o cliente mandou no chat da reclamação (e, com --baixar-fotos, o download de cada uma).
    formulario["fotos"] = avaliar_fotos_do_cliente(devolucao, contexto, leitor, formulario, baixar_fotos)


def simular_criar_devolucao(instrumentos, fabrica_de_requisicoes, devolucao, execucao, baixar_fotos=False):
    """Responde, para 1 devolução: 'se a Ana criasse esta devolução agora, o formulário viria preenchido certo?'.
    Só leitura: nenhum POST, nada gravado, nenhuma chamada extra ao ML (a exceção é baixar_fotos, que faz GET dos anexos)."""
    formulario = {
        "simulado": False, "resultado": None, "erros": [], "avisos": [], "link_parametros": {},
        "busca_sugerida": "", "campos": {}, "produto": None, "aba": None, "fotos": None, "obrigatorios_html_ok": True,
    }
    try:
        _simular_formulario(instrumentos, fabrica_de_requisicoes, devolucao, execucao, formulario, baixar_fotos)
    except Exception:
        formulario["erros"].append("EXCEÇÃO na simulação: " + _resumir_texto(traceback.format_exc().strip().splitlines()[-1], 200))
    formulario["resultado"] = _classificar_formulario(formulario)
    return formulario


# ─── 1 devolução = N consultas + análise ───────────────────────────────────────

def validar_devolucao(instrumentos, fabrica_de_requisicoes, devolucao, repeticoes, com_formulario=True, baixar_fotos=False):
    execucoes = [executar_consulta(instrumentos, fabrica_de_requisicoes, devolucao) for _ in range(repeticoes)]
    analises = [analisar_execucao(execucao, devolucao) for execucao in execucoes]
    instabilidade = comparar_estabilidade(execucoes) if repeticoes > 1 else []

    erros = list(dict.fromkeys(erro for analise in analises for erro in analise["erros"]))
    atencoes = list(dict.fromkeys(texto for analise in analises for texto in analise["atencoes"]))
    divergencias = analises[0]["divergencias"]
    if instabilidade:
        erros.append(f"RESULTADO INSTÁVEL entre as {repeticoes} consultas ({len(instabilidade)} diferença(s))")

    formulario = None
    if com_formulario:
        # Simula o botão "Criar devolução" com o contexto da 1ª consulta que chegou ao detalhe (sem chamar o ML de novo).
        execucao_base = next((execucao for execucao in execucoes if execucao["contexto"] is not None), None)
        formulario = simular_criar_devolucao(instrumentos, fabrica_de_requisicoes, devolucao, execucao_base, baixar_fotos)
        erros.extend("formulário 'Criar devolução': " + texto for tipo, texto in listar_problemas_do_formulario(formulario) if tipo == "ERRO")

    if erros:
        resultado = "ERRO"
    elif atencoes or divergencias or (formulario and formulario["resultado"] in ("FALTA", "DIFERENTE")):
        resultado = "ATENÇÃO"
    else:
        resultado = "OK"

    return {
        "devolucao": {chave: (valor if chave != "datas" else {campo: _dia_br(dia) for campo, dia in valor.items()})
                      for chave, valor in devolucao.items() if not chave.startswith("_")},
        "resultado": resultado,
        "situacao": analises[0]["situacao"],
        "erros": erros,
        "atencoes": atencoes,
        "divergencias": divergencias,
        "instabilidade": instabilidade,
        "formulario": formulario,
        "execucoes": [{
            "segundos_total": execucao["segundos_total"],
            "segundos_render": execucao["segundos_render"],
            "segundos_banco": execucao["segundos_banco"],
            "consultas_banco": execucao["consultas_banco"],
            "http": analise["http"],
            "chamadas_http": [{"endpoint": chamada["endpoint"], "status": chamada["status"],
                               "segundos": round(chamada["segundos"], 3), "thread": chamada["thread"]}
                              for chamada in execucao["chamadas_http"]],
        } for execucao, analise in zip(execucoes, analises)],
    }


# ─── Relatório ─────────────────────────────────────────────────────────────────

COR_DO_RESULTADO = {"OK": "green", "ATENÇÃO": "yellow", "ERRO": "bold red"}


def _linha_do_resultado(posicao, total, resultado):
    execucoes = resultado["execucoes"]
    devolucao = resultado["devolucao"]
    cor = COR_DO_RESULTADO[resultado["resultado"]]
    tempo = _media([execucao["segundos_total"] for execucao in execucoes])
    return (
        f"[{posicao:>3}/{total}] {devolucao['conta']} {devolucao['numero_pedido']}  "
        f"[{cor}]{resultado['resultado']:<8}[/{cor}] {_segundos(tempo)} s"
        f"  diverg.={len(resultado['divergencias'])}  aviso(s)={len(resultado['atencoes'])}"
        f"  form={_texto_do_formulario(resultado)}"
    )


def imprimir_tabela_geral(resultados):
    tabela = Table(title="Uma linha por devolução (médias das consultas repetidas)", box=box.SIMPLE_HEAD, header_style="bold")
    for coluna, alinhamento in [
        ("#", "right"), ("Conta", "left"), ("Pedido", "left"), ("Resultado", "left"), ("Total s", "right"),
        ("ML s", "right"), ("Banco s", "right"), ("HTML s", "right"), ("HTTP", "right"), ("429", "right"),
        ("Diverg.", "right"), ("Estável", "center"), ("Form.", "left"),
    ]:
        tabela.add_column(coluna, justify=alinhamento)
    for posicao, resultado in enumerate(resultados, start=1):
        execucoes = resultado["execucoes"]
        cor = COR_DO_RESULTADO[resultado["resultado"]]
        tabela.add_row(
            str(posicao), resultado["devolucao"]["conta"], resultado["devolucao"]["numero_pedido"],
            f"[{cor}]{resultado['resultado']}[/{cor}]",
            _segundos(_media([e["segundos_total"] for e in execucoes])),
            _segundos(_media([e["http"]["janela_segundos"] for e in execucoes])),
            _segundos(_media([e["segundos_banco"] for e in execucoes])),
            _segundos(_media([e["segundos_render"] for e in execucoes])),
            str(round(_media([e["http"]["chamadas"] for e in execucoes]) or 0)),
            str(sum(e["http"]["n_429"] for e in execucoes)),
            str(len(resultado["divergencias"])),
            "[red]não[/red]" if resultado["instabilidade"] else "[green]sim[/green]",
            _texto_do_formulario(resultado),
        )
    console.print(tabela)


def imprimir_resumo(resultados, repeticoes):
    todas = [execucao for resultado in resultados for execucao in resultado["execucoes"]]
    contagem = Counter(resultado["resultado"] for resultado in resultados)
    totais = [e["segundos_total"] for e in todas]
    janelas = [e["http"]["janela_segundos"] for e in todas]
    bancos = [e["segundos_banco"] for e in todas]
    renders = [e["segundos_render"] for e in todas]
    chamadas = sum(e["http"]["chamadas"] for e in todas)
    n_429 = sum(e["http"]["n_429"] for e in todas)
    instaveis = sum(1 for resultado in resultados if resultado["instabilidade"])

    console.rule("[bold]Resumo")
    console.print(
        f"Devoluções validadas: {len(resultados)}  (consultas feitas: {len(todas)}, {repeticoes} por devolução)\n"
        f"  [green]OK: {contagem['OK']}[/green]   [yellow]ATENÇÃO: {contagem['ATENÇÃO']}[/yellow]   [bold red]ERRO: {contagem['ERRO']}[/bold red]\n"
        f"  Resultado instável entre consultas repetidas: {instaveis}\n"
        f"  Chamadas ao ML: {chamadas}  (~{chamadas / COTA_DO_APP_POR_HORA:.1%} da cota de 1 hora)   429: {n_429}"
    )
    tabela = Table(title="Onde o tempo vai (segundos por consulta, conexões quentes)", box=box.SIMPLE_HEAD, header_style="bold")
    for coluna, alinhamento in [("Parte", "left"), ("Média", "right"), ("Mediana", "right"), ("90%", "right"), ("Máximo", "right")]:
        tabela.add_column(coluna, justify=alinhamento)
    for nome, valores in [("Consulta inteira (view + HTML)", totais), ("Chamadas ao ML (1ª a última)", janelas),
                          ("Banco de dados", bancos), ("Montar o HTML (template)", renders)]:
        validos = [valor for valor in valores if valor is not None]
        tabela.add_row(
            nome, _segundos(_media(validos)),
            _segundos(statistics.median(validos) if validos else None),
            _segundos(_percentil(validos, 0.9)), _segundos(max(validos) if validos else None),
        )
    console.print(tabela)

    por_endpoint = defaultdict(list)
    erros_por_endpoint = Counter()
    for resultado in resultados:
        for execucao in resultado["execucoes"]:
            for chamada in execucao["chamadas_http"]:
                por_endpoint[chamada["endpoint"]].append(chamada["segundos"])
                if chamada["status"] != 200:
                    erros_por_endpoint[chamada["endpoint"]] += 1
    tabela = Table(title="Chamadas por tipo de endpoint", box=box.SIMPLE_HEAD, header_style="bold")
    for coluna, alinhamento in [("Endpoint", "left"), ("Chamadas", "right"), ("Média s", "right"), ("Máx s", "right"), ("≠200", "right")]:
        tabela.add_column(coluna, justify=alinhamento)
    for endpoint, tempos in sorted(por_endpoint.items(), key=lambda par: -statistics.fmean(par[1])):
        tabela.add_row(escape(endpoint), str(len(tempos)), _segundos(statistics.fmean(tempos)), _segundos(max(tempos)), str(erros_por_endpoint[endpoint]))
    console.print(tabela)

    tipos = Counter(divergencia["tipo"] for resultado in resultados for divergencia in resultado["divergencias"])
    if tipos:
        console.print("Divergência não é erro da tela: pode ser digitação da Ana ou o ML divergindo dela — olhar caso a caso.")
        tabela = Table(title="Divergências tela × cadastro", box=box.SIMPLE_HEAD, header_style="bold")
        tabela.add_column("Tipo")
        tabela.add_column("Casos", justify="right")
        for tipo, quantidade in tipos.most_common():
            tabela.add_row(escape(tipo), str(quantidade))
        console.print(tabela)


COR_DO_FORMULARIO = {"OK": "green", "FALTA": "yellow", "DIFERENTE": "dark_orange", "ERRO": "bold red"}


def _texto_do_formulario(resultado):
    formulario = resultado.get("formulario")
    nome = formulario["resultado"] if formulario else None
    if not nome:
        return "—"
    cor = COR_DO_FORMULARIO[nome]
    return f"[{cor}]{nome}[/{cor}]"


def imprimir_resumo_formulario(resultados):
    com_formulario = [resultado["formulario"] for resultado in resultados if resultado.get("formulario")]
    if not com_formulario:
        return
    simulados = [formulario for formulario in com_formulario if formulario["simulado"]]
    contagem = Counter(formulario["resultado"] or "sem botão" for formulario in com_formulario)

    console.rule('[bold]Formulário "Criar devolução": se a Ana criasse a devolução agora')
    baixou_fotos = any(formulario.get("fotos") and formulario["fotos"]["download"] is not None for formulario in simulados)
    console.print(
        'Como foi simulado: a tela Consultar Pedido é montada como se a devolução NÃO existisse, o endereço do botão\n'
        '"Criar devolução" é seguido até a view REAL da Nova devolução e os campos são lidos do HTML que ela devolveria\n'
        '(o que o navegador mostraria). Depois cada campo é comparado com o cadastro da Ana.\n'
        + ('Nada foi salvo. Só houve 1 chamada extra ao Mercado Livre por foto do cliente (--baixar-fotos): GET do anexo, sem guardar o arquivo.'
           if baixou_fotos else 'Nada foi salvo e nenhuma chamada extra foi feita ao Mercado Livre.')
    )
    console.print(
        f"\nDevoluções simuladas: {len(simulados)} de {len(com_formulario)}\n"
        f"  [green]OK: {contagem['OK']}[/green]  (tudo que é automático viria igual ao cadastro)\n"
        f"  [yellow]FALTA: {contagem['FALTA']}[/yellow]  (algum campo automático viria vazio, o produto não aparece na busca, "
        f"ou uma foto do cliente não baixaria)\n"
        f"  [dark_orange]DIFERENTE: {contagem['DIFERENTE']}[/dark_orange]  (algum campo automático viria diferente do cadastro, "
        f"o produto marcado sozinho é o errado, ou a devolução nasceria na aba errada)\n"
        f"  [bold red]ERRO: {contagem['ERRO']}[/bold red]  (o formulário não abriu, ou um campo viria num formato que o navegador ignora)"
    )

    tabela = Table(title="Campo a campo: o que o formulário traria x o que a Ana cadastrou", box=box.SIMPLE_HEAD, header_style="bold")
    for coluna, alinhamento in [("Campo", "left"), ("Modo", "left"), ("Igual", "right"), ("Parecido", "right"), ("Diferente", "right"),
                                ("Vem vazio", "right"), ("Só no form.", "right"), ("Vazio nos 2", "right"), ("Ilegível", "right")]:
        tabela.add_column(coluna, justify=alinhamento)
    for campo, rotulo, modo, _, _ in CAMPOS_DO_FORMULARIO:
        estados = Counter(formulario["campos"][campo]["estado"] for formulario in simulados if campo in formulario["campos"])
        tabela.add_row(rotulo, modo, str(estados["igual"]), str(estados["parecido"]), str(estados["diferente"]),
                       str(estados["falta"]), str(estados["so_formulario"]), str(estados["vazio"]), str(estados["ilegivel"]))
    console.print(tabela)
    console.print('"Vem vazio" é o esperado nos campos manuais (a Ana preenche). "Parecido" = o nome do cadastro é uma forma '
                  'abreviada do que o ML devolve (não conta como problema).')

    abas = Counter((formulario["aba"]["formulario"], formulario["aba"]["cadastro"], formulario["aba"]["estado"])
                   for formulario in simulados if formulario["aba"])
    if abas:
        tabela = Table(title="Aba em que a devolução nasceria (as datas de mediação são manuais: o esperado é 'Aguardando Conferência')",
                       box=box.SIMPLE_HEAD, header_style="bold")
        tabela.add_column("Pelo formulário")
        tabela.add_column("Hoje, no cadastro da Ana")
        tabela.add_column("Situação")
        tabela.add_column("Casos", justify="right")
        textos_da_aba = {"igual": "igual", "depois_a_ana_marca": "esperado: a Ana marca as datas de mediação depois",
                         "diferente": "o botão está levando data de mediação"}
        for (do_formulario, do_cadastro, estado), quantidade in sorted(abas.items(), key=lambda item: (item[0][2] == "diferente" and 0 or 1, -item[1])):
            cor = "dark_orange" if estado == "diferente" else "green"
            tabela.add_row(escape(do_formulario), escape(do_cadastro), textos_da_aba[estado], f"[{cor}]{quantidade}[/{cor}]")
        console.print(tabela)

    produtos = Counter(formulario["produto"]["estado"] for formulario in simulados if formulario["produto"])
    if produtos:
        tabela = Table(title="Produto: o botão marcou sozinho (SKU/EAN) ou a Ana teria que escolher?", box=box.SIMPLE_HEAD, header_style="bold")
        tabela.add_column("Situação")
        tabela.add_column("Casos", justify="right")
        for estado, texto in ROTULO_DO_ESTADO_DO_PRODUTO.items():
            if produtos[estado]:
                cor = "dark_orange" if estado in ("automatico_errado", "marcado_errado") else "green" if estado in ("automatico_certo", "marcado_certo") else "yellow" if estado in ("fora_da_lista", "sem_busca") else "white"
                tabela.add_row(escape(texto), f"[{cor}]{produtos[estado]}[/{cor}]")
        console.print(tabela)

        de_item_unico = [formulario["produto"] for formulario in simulados if formulario["produto"] and formulario["produto"].get("item_unico")]
        origens = Counter(produto.get("origem_no_servidor") or "nenhuma" for produto in de_item_unico)
        com_ean = sum(1 for produto in de_item_unico if produto.get("gtins_do_anuncio"))
        console.print(
            f"Pedidos de 1 item: {len(de_item_unico)} de {len(simulados)}. Em pedido de 2+ itens o botão não marca produto "
            f"(não há como saber qual é).\nO ML trouxe o GTIN/EAN do anúncio em {com_ean} de {len(de_item_unico)} pedidos de 1 item."
        )
        if de_item_unico and not com_ean:
            console.print("[yellow]Nenhum anúncio trouxe EAN: ou os anúncios não têm GTIN preenchido, ou o campo 'attributes' do "
                          "multiget /items não está voltando como esperado. Nesse caso o produto só é achado pelo SKU — vale conferir "
                          "a documentação de atributos do item do ML.[/yellow]")
        tabela = Table(title="Produto: como o servidor achou o produto (pedidos de 1 item)", box=box.SIMPLE_HEAD, header_style="bold")
        tabela.add_column("Batida")
        tabela.add_column("Casos", justify="right")
        for origem, texto in ROTULO_DA_ORIGEM_DO_PRODUTO.items():
            if origens[origem]:
                tabela.add_row(escape(texto), str(origens[origem]))
        console.print(tabela)

    fotos = [formulario["fotos"] for formulario in simulados if formulario.get("fotos")]
    if fotos:
        estados_das_fotos = Counter(item["estado"] for item in fotos)
        tabela = Table(title="Fotos do cliente: o chat da reclamação no ML x o que a Ana anexou", box=box.SIMPLE_HEAD, header_style="bold")
        tabela.add_column("Situação")
        tabela.add_column("Casos", justify="right")
        for estado, texto in ROTULO_DO_ESTADO_DAS_FOTOS.items():
            if estados_das_fotos[estado]:
                tabela.add_row(escape(texto), str(estados_das_fotos[estado]))
        console.print(tabela)
        console.print(f"Fotos que o botão levaria: {sum(item['no_formulario'] for item in fotos)} no total, em "
                      f"{sum(1 for item in fotos if item['no_formulario'])} devolução(ões). Fotos já anexadas pela Ana: "
                      f"{sum(item['cadastradas'] for item in fotos)}.")
        if baixou_fotos:
            testadas = sum(item["download"]["tentadas"] for item in fotos if item["download"])
            baixadas = sum(item["download"]["ok"] for item in fotos if item["download"])
            cor = "green" if testadas == baixadas else "yellow"
            convertidas = sum(item["download"].get("convertidas", 0) for item in fotos if item["download"])
            extra = f" ({convertidas} delas HEIC, convertida(s) para JPEG)" if convertidas else ""
            console.print(f"Download de verdade (--baixar-fotos): [{cor}]{baixadas} de {testadas} foto(s) baixaram como imagem{extra}[/{cor}].")
        else:
            console.print("O download das fotos NÃO foi testado (rode com --baixar-fotos para provar que o ML entrega cada anexo).")

    discordam = sum(1 for formulario in simulados if not formulario["obrigatorios_html_ok"])
    console.print(
        f"Campos obrigatórios: o HTML e o servidor concordam em {len(simulados) - discordam} de {len(simulados)} simulações."
        + ("" if not discordam else " [yellow]Há discordância: ver os avisos de cada caso.[/yellow]")
    )
    pela_ponte = sum(1 for resultado in resultados if resultado["devolucao"]["criada_pela_ponte"])
    if pela_ponte:
        console.print(f"{pela_ponte} das {len(resultados)} devoluções foram criadas depois de 18/09/2026, já pelo botão: "
                      "nelas \"igual\" prova menos (a Ana pode só ter confirmado o que o botão trouxe).")

    console.print("\nPor que cada campo é automático ou manual:")
    for _, rotulo, modo, obrigatorio, por_que in CAMPOS_DO_FORMULARIO + [CAMPO_PRODUTO, CAMPO_FOTOS]:
        etiqueta = f"{modo}; obrigatório" if obrigatorio else modo
        console.print(f"  {escape(rotulo)} ({etiqueta}): {escape(por_que)}")


def imprimir_casos_para_olhar(resultados):
    console.rule("[bold]Casos para olhar (um bloco por devolução que não ficou OK)")
    houve = False
    for resultado in resultados:
        if resultado["resultado"] == "OK":
            continue
        houve = True
        devolucao = resultado["devolucao"]
        cor = COR_DO_RESULTADO[resultado["resultado"]]
        ponte = "  (criada pela ponte: dados podem vir da própria tela)" if devolucao["criada_pela_ponte"] else ""
        console.print(f"\n[{cor}]{resultado['resultado']}[/{cor}]  {devolucao['conta']} {devolucao['numero_pedido']}  "
                      f"(devolução #{devolucao['id']}, situação: {resultado['situacao']}){ponte}")
        for rotulo, itens in [("ERRO", resultado["erros"]), ("INSTÁVEL", resultado["instabilidade"]),
                              ("ATENÇÃO", resultado["atencoes"]),
                              ("DIVERGÊNCIA", [divergencia["texto"] for divergencia in resultado["divergencias"]])]:
            for texto in itens[:MAXIMO_ITENS_POR_CASO_NA_TELA]:
                console.print(f"    {rotulo}: {escape(str(texto))}")
            if len(itens) > MAXIMO_ITENS_POR_CASO_NA_TELA:
                console.print(f"    {rotulo}: (+{len(itens) - MAXIMO_ITENS_POR_CASO_NA_TELA} no JSON)")
        # Os ERRO do formulário já foram impressos acima (entram na lista de erros do caso); aqui só o que é novo.
        problemas_do_formulario = [
            (tipo, texto_do_problema) for tipo, texto_do_problema in listar_problemas_do_formulario(
                resultado.get("formulario"), {divergencia["tipo"] for divergencia in resultado["divergencias"]})
            if tipo != "ERRO"]
        for tipo, texto_do_problema in problemas_do_formulario[:MAXIMO_ITENS_POR_CASO_NA_TELA]:
            console.print(f"    FORMULÁRIO ({tipo}): {escape(str(texto_do_problema))}")
        if len(problemas_do_formulario) > MAXIMO_ITENS_POR_CASO_NA_TELA:
            console.print(f"    FORMULÁRIO: (+{len(problemas_do_formulario) - MAXIMO_ITENS_POR_CASO_NA_TELA} no JSON)")
    if not houve:
        console.print("[green]Nenhum caso fora do OK.[/green]")


def salvar_saidas(resultados, argumentos):
    dados = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "repeticoes": argumentos.repeticoes,
        "total_devolucoes": len(resultados),
        "resultados": resultados,
    }
    ARQUIVO_JSON.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    console.save_text(str(ARQUIVO_RELATORIO))
    console.print(f"\nRelatório salvo em: {ARQUIVO_RELATORIO}\nDetalhe completo em: {ARQUIVO_JSON}")


# ─── Programa principal ──────────────────────────────────────────────────────

def ler_argumentos():
    analisador = argparse.ArgumentParser(description="Valida a Consultar Pedido sobre todas as devoluções cadastradas.")
    analisador.add_argument("--conta", choices=sorted(BANCO_POR_CONTA), help="só uma empresa (MB ou SV); padrão: as duas")
    analisador.add_argument("--pedido", help="só este número de pedido (procura nas contas escolhidas)")
    analisador.add_argument("--limite", type=int, help="valida só as N primeiras devoluções (teste curto)")
    analisador.add_argument("--repeticoes", type=int, default=REPETICOES_PADRAO,
                            help=f"quantas vezes consultar cada devolução (padrão {REPETICOES_PADRAO}; 1 desliga o teste de estabilidade)")
    analisador.add_argument("--pausa", type=float, default=PAUSA_PADRAO_SEGUNDOS,
                            help=f"segundos de pausa entre uma devolução e outra (padrão {PAUSA_PADRAO_SEGUNDOS})")
    analisador.add_argument("--sem-render", action="store_true", help="não monta o HTML (mais rápido; não testa o template)")
    analisador.add_argument("--sem-formulario", action="store_true",
                            help='não simula o botão "Criar devolução" (não confere o formulário da Nova devolução)')
    analisador.add_argument("--baixar-fotos", action="store_true",
                            help="baixa de verdade (só leitura) cada foto do cliente que o botão levaria, para provar que o ML entrega "
                                 "(faz 1 chamada a mais por foto; nada é guardado)")
    analisador.add_argument("--listar", action="store_true", help="só mostra o plano e a estimativa de chamadas, sem chamar a API")
    argumentos = analisador.parse_args()
    if argumentos.repeticoes < 1:
        analisador.error("--repeticoes precisa ser 1 ou mais")
    return argumentos


def main():
    argumentos = ler_argumentos()
    contas = [argumentos.conta] if argumentos.conta else sorted(BANCO_POR_CONTA)
    devolucoes = carregar_devolucoes(contas, argumentos.pedido, argumentos.limite)
    if not devolucoes:
        console.print("[yellow]Nenhuma devolução encontrada com esses filtros.[/yellow]")
        return

    por_conta = Counter(devolucao["conta"] for devolucao in devolucoes)
    chamadas_estimadas = len(devolucoes) * argumentos.repeticoes * CHAMADAS_POR_CONSULTA
    segundos_estimados = len(devolucoes) * (argumentos.repeticoes * 2.0 + argumentos.pausa)
    texto_do_formulario = ("não simulado (--sem-formulario)" if argumentos.sem_formulario
                           else "simulado, com download das fotos do cliente (1 chamada extra por foto, só leitura)" if argumentos.baixar_fotos
                           else "simulado, sem chamadas extras ao ML")
    console.rule("[bold]Plano")
    console.print(
        f"Devoluções: {len(devolucoes)}  ({', '.join(f'{conta}: {quantidade}' for conta, quantidade in sorted(por_conta.items()))})\n"
        f"Consultas por devolução: {argumentos.repeticoes}   Pausa entre devoluções: {argumentos.pausa} s\n"
        f"Chamadas estimadas ao ML: ~{chamadas_estimadas}  (~{chamadas_estimadas / COTA_DO_APP_POR_HORA:.1%} da cota de 1 hora, dividida com o Sistema Interno V2)\n"
        f"Tempo estimado: ~{segundos_estimados / 60:.0f} min\n"
        f"Formulário \"Criar devolução\": {texto_do_formulario}"
    )
    if argumentos.listar:
        console.print("\n(--listar: nada foi consultado.)")
        return

    fabrica_de_requisicoes = RequestFactory()
    resultados = []
    try:
        with Instrumentos(medir_render=not argumentos.sem_render) as instrumentos:
            for posicao, devolucao in enumerate(devolucoes, start=1):
                resultado = validar_devolucao(instrumentos, fabrica_de_requisicoes, devolucao, argumentos.repeticoes,
                                              com_formulario=not argumentos.sem_formulario, baixar_fotos=argumentos.baixar_fotos)
                resultados.append(resultado)
                console.print(_linha_do_resultado(posicao, len(devolucoes), resultado))
                if posicao < len(devolucoes):
                    time.sleep(argumentos.pausa)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrompido (Ctrl+C) — relatório parcial com o que já foi validado.[/yellow]")
    finally:
        definir_empresa_ativa(None)
        if resultados:
            imprimir_tabela_geral(resultados)
            imprimir_resumo(resultados, argumentos.repeticoes)
            imprimir_resumo_formulario(resultados)
            imprimir_casos_para_olhar(resultados)
            salvar_saidas(resultados, argumentos)


if __name__ == "__main__":
    main()
