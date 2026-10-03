# scripts_exploracao_ML/comparar_devolucoes_manual_vs_api.py

# Função Objetivo: Passo 2 da validação da tela Consultar Pedido. Pra cada
# devolução que já existe no banco (MB e SV), pergunta pra MESMA tela o que
# ela traria hoje e compara, campo a campo, com o que foi digitado à mão.
# A função view_consultar_pedido é chamada de verdade (não é reimplementada
# aqui) — então o que este script enxerga é exatamente o que a Ana veria.
# Só leitura: SELECT no banco, GET na API do Mercado Livre. Não grava nada.
#
# Rodar da raiz do projeto, com o ambiente virtual ativo:
#   python scripts_exploracao_ML/comparar_devolucoes_manual_vs_api.py --limite 3
#   python scripts_exploracao_ML/comparar_devolucoes_manual_vs_api.py
# Opções: --conta MB|SV (só uma empresa) e --limite N (só as N primeiras de cada).

import argparse
import json
import os
import sys
import time
import traceback
import unicodedata
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

# ─── Prepara o Django (mesmo bootstrap do listar_devolucoes_do_banco.py) ─
_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projeto_sistema_devolucao_mb_sv.settings")

import django

django.setup()

from django.test import RequestFactory
from django.utils import timezone
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from core.empresa import definir_empresa_ativa, EMPRESA_MAGAZINE, EMPRESA_SAMVALE
from devolucoes.models import Devolucao
from integracao_mercado_livre import views as tela_consultar_pedido

console = Console()

PASTA_SAIDA = Path(__file__).resolve().parent
ARQUIVO_SAIDA = PASTA_SAIDA / "comparacao_manual_vs_api.json"

# (conta no .env, alias do banco, empresa ativa que a tela espera)
BANCOS = [
    ("MB", "magazine", EMPRESA_MAGAZINE),
    ("SV", "samvale", EMPRESA_SAMVALE),
]

# Devoluções criadas a partir desta data podem ter vindo do botão "Criar
# devolução" (pré-preenchido pela própria API) — não são verdade independente.
DATA_INICIO_PONTE = date(2026, 9, 18)

# (campo da Devolucao, tipo, como ler o valor manual, chave no contexto da tela)
CAMPOS = [
    ("numero_pedido", "texto", lambda d: d.numero_pedido, "numero_pedido"),
    ("nome_cliente", "nome", lambda d: d.nome_cliente, "nome_comprador_input"),
    ("data_venda", "data", lambda d: d.data_venda, "data_venda_input"),
    ("data_recebimento_cliente", "data", lambda d: d.data_recebimento_cliente, "data_recebimento_cliente_input"),
    ("data_reclamacao_cliente", "data", lambda d: d.data_reclamacao_cliente, "data_reclamacao_cliente_input"),
    ("data_recebimento_por_nos", "data", lambda d: d.data_recebimento_por_nos, "data_recebimento_por_nos_input"),
    ("data_abertura_mediacao", "data", lambda d: d.data_abertura_mediacao, "data_abertura_mediacao_input"),
    ("data_finalizacao_mediacao", "data", lambda d: d.data_finalizacao_mediacao, "data_finalizacao_mediacao_input"),
    ("tipo_venda", "texto", lambda d: d.tipo_venda, "tipo_venda_sugerido"),
    ("preco_produto", "dinheiro", lambda d: d.preco_produto, "preco_produto_input"),
    ("claim_id", "texto", lambda d: d.claim_id, "claim_id"),
    ("produto.sku", "texto", lambda d: d.produto.sku, "sku_item_input"),
]

CLASSES = [
    ("igual", "igual"),
    ("igual_na_forma", "só na forma"),
    ("parcial", "parcial"),
    ("difere", "DIFERE"),
    ("manual_vazio", "manual vazio"),
    ("api_vazia", "API vazia"),
    ("ambos_vazios", "ambos vazios"),
]
ROTULO_DA_CLASSE = dict(CLASSES)
CLASSES_PARA_LISTAR = ("difere", "parcial", "api_vazia", "manual_vazio")
# Campos que as devoluções antigas (antes da ponte) nunca tiveram — "manual vazio"
# neles é esperado e só faria barulho na lista de divergências.
VAZIO_ESPERADO_ANTES_DA_PONTE = ("preco_produto", "claim_id")

STATUS_ROTULOS = {
    "ok": "ok",
    "sem_reclamacao": "sem reclamação",
    "sem_devolucao_fisica": "sem devolução física",
    "pack_ambiguo": "pack ambíguo",
    "erro_api": "erro da API",
    "excecao": "exceção",
    "fora_do_ml": "fora do ML",
}

# Pares de datas que deveriam estar em ordem cronológica.
PARES_DE_ORDEM = [
    ("data_venda", "data_recebimento_cliente"),
    ("data_recebimento_cliente", "data_reclamacao_cliente"),
    ("data_reclamacao_cliente", "data_recebimento_por_nos"),
    ("data_reclamacao_cliente", "data_abertura_mediacao"),
    ("data_abertura_mediacao", "data_finalizacao_mediacao"),
]
ROTULO_CURTO_DATA = {
    "data_venda": "venda",
    "data_recebimento_cliente": "entrega ao cliente",
    "data_reclamacao_cliente": "reclamação",
    "data_recebimento_por_nos": "recebido por nós",
    "data_abertura_mediacao": "abertura mediação",
    "data_finalizacao_mediacao": "fim mediação",
}


# ─── Consulta à tela ────────────────────────────────────────────────────

# * [EXPLICAÇÃO] → A view termina cada caminho com render(request, template,
#   contexto), que desenharia o HTML. Aqui trocamos SÓ esse render por uma
#   função que devolve o próprio contexto — o resto da view roda intacto
#   (mesmas chamadas à API, mesmas heurísticas). Vale só dentro deste script.
def _render_que_devolve_o_contexto(requisicao, template, contexto=None):
    return contexto


tela_consultar_pedido.render = _render_que_devolve_o_contexto

_FABRICA_DE_REQUISICOES = RequestFactory()


def consultar_pedido_na_tela(empresa, numero_pedido):
    definir_empresa_ativa(empresa)
    requisicao = _FABRICA_DE_REQUISICOES.get(
        "/mercado-livre/consultar-pedido/", {"numero_pedido": numero_pedido}
    )
    return tela_consultar_pedido.view_consultar_pedido(requisicao)


def classificar_resultado_da_tela(contexto):
    if contexto.get("encontrado"):
        return "ok", ""
    if contexto.get("lista_pedidos"):
        total = sum(len(bloco["pedidos"]) for bloco in contexto["lista_pedidos"])
        return "pack_ambiguo", f"{total} pedidos no mesmo pack — a tela pede pra escolher"
    erro = contexto.get("erro") or ""
    if erro.startswith("Nenhuma reclamação encontrada"):
        return "sem_reclamacao", erro
    if erro.startswith("Nenhuma reclamação tem devolução física"):
        return "sem_devolucao_fisica", erro
    if erro:
        return "erro_api", erro
    return "erro_api", "a tela não devolveu nem dados nem mensagem de erro"


# ─── Comparação ─────────────────────────────────────────────────────────

def _forma_normal_nome(texto):
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().split())


def _texto_comparavel(tipo, valor):
    if valor is None:
        return ""
    if tipo == "data":
        if isinstance(valor, date):
            return valor.isoformat()[:10]
        return str(valor).strip()
    if tipo == "dinheiro":
        try:
            return f"{Decimal(str(valor)):.2f}"
        except InvalidOperation:
            return str(valor).strip()
    return " ".join(str(valor).split())


def _classificar_campo(tipo, manual, api):
    if not manual and not api:
        return "ambos_vazios"
    if not manual:
        return "manual_vazio"
    if not api:
        return "api_vazia"
    if manual == api:
        return "igual"
    if tipo == "nome":
        nome_manual, nome_api = _forma_normal_nome(manual), _forma_normal_nome(api)
        if nome_manual == nome_api:
            return "igual_na_forma"
        # * [EXPLICAÇÃO] → Counter conta repetições: "Goncalves Goncalves" não cabe
        #   dentro de "Goncalves Pereira" (com set() cabia e escondia a diferença).
        palavras_manual, palavras_api = Counter(nome_manual.split()), Counter(nome_api.split())
        if not (palavras_manual - palavras_api) or not (palavras_api - palavras_manual):
            return "parcial"
    return "difere"


def _diferenca_em_dias(manual, api):
    try:
        return (date.fromisoformat(api) - date.fromisoformat(manual)).days
    except ValueError:
        return None


def _exibir(tipo, texto):
    if not texto:
        return "—"
    if tipo == "data":
        try:
            ano, mes, dia = texto.split("-")
            return f"{dia}/{mes}/{ano}"
        except ValueError:
            return texto
    return texto


def _pares_fora_de_ordem(datas):
    quebrados = []
    for antes, depois in PARES_DE_ORDEM:
        if datas.get(antes) and datas.get(depois) and datas[depois] < datas[antes]:
            quebrados.append(
                f"{ROTULO_CURTO_DATA[antes]} {_exibir('data', datas[antes])}"
                f" > {ROTULO_CURTO_DATA[depois]} {_exibir('data', datas[depois])}"
            )
    return quebrados


def _criada_apos_a_ponte(devolucao):
    criado = devolucao.criado_em
    if timezone.is_aware(criado):
        criado = timezone.localtime(criado)
    return criado.date() >= DATA_INICIO_PONTE


def montar_entrada(conta, empresa, devolucao):
    entrada = {
        "conta": conta,
        "id": devolucao.id,
        "numero_pedido": devolucao.numero_pedido,
        "criado_em": devolucao.criado_em.isoformat(),
        "pos_ponte": _criada_apos_a_ponte(devolucao),
        "api": {"status": None, "detalhe": "", "pedido_resolvido": None, "via_pack": False},
        "campos": {},
        "ordem_manual": [],
        "ordem_api": [],
    }

    if devolucao.nome_plataforma != Devolucao.PLATAFORMA_MERCADO_LIVRE:
        entrada["api"]["status"] = "fora_do_ml"
        entrada["api"]["detalhe"] = f"plataforma: {devolucao.nome_plataforma}"
        return entrada

    try:
        contexto = consultar_pedido_na_tela(empresa, devolucao.numero_pedido)
        status, detalhe = classificar_resultado_da_tela(contexto)
    except KeyboardInterrupt:
        raise
    except Exception as erro:
        # * [EXPLICAÇÃO] → só a mensagem ("'NoneType' object is not iterable") não diz ONDE
        #   quebrou. Juntamos os 3 últimos passos do traceback que não são de biblioteca:
        #   arquivo, linha, função e o próprio código da linha.
        passos = [
            passo for passo in traceback.extract_tb(erro.__traceback__)
            if "site-packages" not in passo.filename
        ]
        onde = "  <-  ".join(
            f'{Path(passo.filename).name}:{passo.lineno} {passo.name}() "{passo.line}"'
            for passo in reversed(passos[-3:])
        )
        contexto, status, detalhe = {}, "excecao", f"{type(erro).__name__}: {erro}  ||  {onde}"

    entrada["api"]["status"] = status
    entrada["api"]["detalhe"] = detalhe
    entrada["api"]["pedido_resolvido"] = str(contexto.get("numero_pedido") or "")
    entrada["api"]["via_pack"] = "aviso_pack" in contexto

    if status != "ok":
        return entrada

    datas_manual, datas_api = {}, {}
    for nome, tipo, ler_manual, chave_api in CAMPOS:
        manual = _texto_comparavel(tipo, ler_manual(devolucao))
        api = _texto_comparavel(tipo, contexto.get(chave_api))
        classe = _classificar_campo(tipo, manual, api)
        entrada["campos"][nome] = {
            "manual": manual,
            "api": api,
            "classe": classe,
            "dif_dias": _diferenca_em_dias(manual, api) if tipo == "data" and classe == "difere" else None,
        }
        if tipo == "data":
            datas_manual[nome], datas_api[nome] = manual, api

    entrada["ordem_manual"] = _pares_fora_de_ordem(datas_manual)
    entrada["ordem_api"] = _pares_fora_de_ordem(datas_api)
    return entrada


# ─── Relatório no terminal ──────────────────────────────────────────────

def _rotulo_ponte(entrada):
    return "depois" if entrada["pos_ponte"] else "antes"


def imprimir_resultado_da_tela(entradas):
    contas = sorted({e["conta"] for e in entradas})
    status_presentes = [s for s in STATUS_ROTULOS if any(e["api"]["status"] == s for e in entradas)]

    tabela = Table(title="1) O que a tela devolveu pra cada devolução do banco")
    tabela.add_column("Conta")
    tabela.add_column("Devoluções", justify="right")
    for status in status_presentes:
        tabela.add_column(STATUS_ROTULOS[status], justify="right")
    for conta in contas:
        daquela = [e for e in entradas if e["conta"] == conta]
        tabela.add_row(
            conta,
            str(len(daquela)),
            *[str(sum(1 for e in daquela if e["api"]["status"] == s)) for s in status_presentes],
        )
    console.print(tabela)

    sem_dados = [e for e in entradas if e["api"]["status"] != "ok"]
    if sem_dados:
        tabela = Table(title="   ...as que NÃO deram ok (a tela não preencheria nada pra elas)")
        for coluna in ("Conta", "Pedido", "Ponte", "Situação", "Detalhe"):
            tabela.add_column(coluna, overflow="fold")
        for e in sem_dados:
            tabela.add_row(
                e["conta"], e["numero_pedido"], _rotulo_ponte(e),
                STATUS_ROTULOS[e["api"]["status"]], escape(e["api"]["detalhe"]),
            )
        console.print(tabela)


def imprimir_resumo_por_campo(entradas):
    grupos = (
        (False, "ANTES da ponte (digitadas à mão)"),
        (True, "DEPOIS da ponte (podem ter vindo pré-preenchidas pela API)"),
    )
    for pos_ponte, titulo in grupos:
        grupo = [e for e in entradas if e["api"]["status"] == "ok" and e["pos_ponte"] == pos_ponte]
        if not grupo:
            console.print(f"[dim]Nada pra comparar no grupo: criadas {titulo}.[/dim]")
            continue
        tabela = Table(title=f"2) Campo a campo — criadas {titulo} — {len(grupo)} comparadas")
        tabela.add_column("Campo")
        for _classe, rotulo in CLASSES:
            tabela.add_column(rotulo, justify="right")
        for nome, _tipo, _ler, _chave in CAMPOS:
            contagem = Counter(e["campos"][nome]["classe"] for e in grupo)
            celulas = []
            for classe, _rotulo in CLASSES:
                n = contagem.get(classe, 0)
                if classe == "difere" and n:
                    celulas.append(f"[bold red]{n}[/]")
                elif classe == "api_vazia" and n:
                    celulas.append(f"[yellow]{n}[/]")
                else:
                    celulas.append(str(n) if n else "·")
            tabela.add_row(nome, *celulas)
        console.print(tabela)


def imprimir_divergencias(entradas):
    ordem_do_campo = {campo[0]: posicao for posicao, campo in enumerate(CAMPOS)}
    tipo_do_campo = {campo[0]: campo[1] for campo in CAMPOS}
    linhas = []
    for e in entradas:
        if e["api"]["status"] != "ok":
            continue
        for nome, resultado in e["campos"].items():
            if resultado["classe"] not in CLASSES_PARA_LISTAR:
                continue
            if resultado["classe"] == "manual_vazio" and not e["pos_ponte"] and nome in VAZIO_ESPERADO_ANTES_DA_PONTE:
                continue
            linhas.append((ordem_do_campo[nome], e, nome, resultado))
    linhas.sort(key=lambda linha: (linha[0], linha[1]["conta"], linha[1]["numero_pedido"]))

    if not linhas:
        console.print("[green]3) Nenhuma divergência (difere / parcial / API vazia / manual vazio).[/green]")
        return

    tabela = Table(title=f"3) Divergências — {len(linhas)} linhas (ordenadas por campo)")
    for coluna in ("Campo", "Conta", "Pedido", "Ponte", "Classe", "Manual", "API", "Δ dias (API−manual)"):
        tabela.add_column(coluna, overflow="fold")
    for _posicao, e, nome, resultado in linhas:
        tipo = tipo_do_campo[nome]
        dif = resultado["dif_dias"]
        tabela.add_row(
            nome, e["conta"], e["numero_pedido"], _rotulo_ponte(e),
            ROTULO_DA_CLASSE[resultado["classe"]],
            escape(_exibir(tipo, resultado["manual"])),
            escape(_exibir(tipo, resultado["api"])),
            "" if dif is None else f"{dif:+d}",
        )
    console.print(tabela)


def imprimir_ordem_estranha(entradas):
    linhas = []
    for e in entradas:
        for lado, chave in (("manual", "ordem_manual"), ("API", "ordem_api")):
            if e[chave]:
                linhas.append((e, lado, "; ".join(e[chave])))
    if not linhas:
        console.print("[green]4) Nenhuma devolução com datas fora de ordem.[/green]")
        return
    tabela = Table(title="4) Datas fora de ordem cronológica (venda → entrega → reclamação → recebido → mediação)")
    for coluna in ("Conta", "Pedido", "Ponte", "Lado", "O que está fora de ordem"):
        tabela.add_column(coluna, overflow="fold")
    for e, lado, texto in linhas:
        tabela.add_row(e["conta"], e["numero_pedido"], _rotulo_ponte(e), lado, texto)
    console.print(tabela)


# ─── Execução ───────────────────────────────────────────────────────────

def ler_argumentos():
    parser = argparse.ArgumentParser(description="Compara devoluções do banco com o que a tela Consultar Pedido traz da API.")
    parser.add_argument("--conta", choices=[b[0] for b in BANCOS], help="só uma empresa (MB ou SV)")
    parser.add_argument("--pedido", help="só a devolução com esse número de pedido")
    parser.add_argument("--limite", type=int, help="só as N primeiras devoluções de cada empresa")
    return parser.parse_args()


def main():
    argumentos = ler_argumentos()

    pendentes = []
    for conta, alias, empresa in BANCOS:
        if argumentos.conta and argumentos.conta != conta:
            continue
        consulta = Devolucao.objects.using(alias).select_related("produto").order_by("criado_em")
        if argumentos.pedido:
            consulta = consulta.filter(numero_pedido=argumentos.pedido)
        if argumentos.limite:
            consulta = consulta[: argumentos.limite]
        pendentes += [(conta, empresa, d) for d in consulta]

    console.print(
        f"[bold]{len(pendentes)} devoluções[/bold] pra consultar na API "
        "(a tela faz ~10 chamadas por pedido; só GET). Ctrl+C interrompe e mostra o parcial.\n"
    )

    entradas = []
    try:
        for posicao, (conta, empresa, devolucao) in enumerate(pendentes, start=1):
            inicio = time.monotonic()
            entrada = montar_entrada(conta, empresa, devolucao)
            entradas.append(entrada)
            console.print(
                f"[{posicao}/{len(pendentes)}] {conta} {devolucao.numero_pedido} → "
                f"{STATUS_ROTULOS[entrada['api']['status']]} ({time.monotonic() - inicio:.1f}s)"
            )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrompido — mostrando só o que já foi consultado.[/yellow]")

    console.print()
    if not entradas:
        return
    imprimir_resultado_da_tela(entradas)
    imprimir_resumo_por_campo(entradas)
    imprimir_divergencias(entradas)
    imprimir_ordem_estranha(entradas)

    with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as arquivo:
        json.dump(
            {"gerado_em": datetime.now().isoformat(timespec="seconds"), "entradas": entradas},
            arquivo, ensure_ascii=False, indent=2, default=str,
        )
    console.print(f"\nJSON completo (com tudo, inclusive os campos iguais): {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    main()