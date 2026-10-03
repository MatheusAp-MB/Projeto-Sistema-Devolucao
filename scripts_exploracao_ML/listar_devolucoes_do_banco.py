# scripts_exploracao_ML/listar_devolucoes_do_banco.py
#
# Objetivo: passo 1 do ciclo "Consultar Pedido — manual vs API". Lista, pra
# TODAS as devoluções dos 2 bancos (MB e SV), os campos digitados à mão que
# têm par direto na tela Consultar Pedido, organizados por empresa. O JSON
# gerado é a entrada do passo 2 (rebuscar cada pedido na API e comparar
# "o que existe manual" vs "o que a API trouxe").
#
# Só leitura no banco (nenhum save/update/delete). NÃO chama a API do ML.

import json
import os
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projeto_sistema_devolucao_mb_sv.settings")

import django  # noqa: E402

django.setup()

from django.utils import timezone  # noqa: E402

from devolucoes.models import Devolucao  # noqa: E402

# ==== CONFIGURA AQUI ANTES DE RODAR ====
# Devoluções criadas a partir desta data podem ter vindo PRÉ-PREENCHIDAS pelo
# botão "Criar devolução" da própria Consultar Pedido (ponte implementada em
# 18/09/2026) — nesses casos o valor "manual" pode não ser independente da API.
DATA_INICIO_PONTE = date(2026, 9, 18)
# Quantas linhas de Mercado Livre mostrar no terminal por empresa (o JSON
# sempre leva TODAS).
LINHAS_NO_TERMINAL = 12
# ========================================

BANCOS = [("MB", "magazine"), ("SV", "samvale")]
CAMINHO_SAIDA = Path(__file__).resolve().parent / "devolucoes_do_banco.json"

console = Console()


def _iso(valor):
    return valor.isoformat() if valor is not None else None


def _texto(valor):
    return str(valor) if valor is not None else None


def _data_br(valor_iso):
    # "2026-09-08" -> "08/09/26"; vazio vira "—"
    if not valor_iso:
        return "—"
    ano, mes, dia = valor_iso[:10].split("-")
    return f"{dia}/{mes}/{ano[2:]}"


def montar_linha(conta, d):
    criado_local = timezone.localtime(d.criado_em) if timezone.is_aware(d.criado_em) else d.criado_em
    return {
        "conta": conta,
        "id": d.id,
        "criado_em": criado_local.strftime("%Y-%m-%d %H:%M"),
        "criada_a_partir_da_ponte": criado_local.date() >= DATA_INICIO_PONTE,
        "status_fluxo": d.status_fluxo,
        # ---- Campos com par direto na tela Consultar Pedido ----
        "numero_pedido": d.numero_pedido,
        "plataforma": d.nome_plataforma,
        "tipo_venda": d.tipo_venda,
        "nome_cliente": d.nome_cliente,
        "data_venda": _iso(d.data_venda),
        "data_recebimento_cliente": _iso(d.data_recebimento_cliente),
        "data_reclamacao_cliente": _iso(d.data_reclamacao_cliente),
        "data_recebimento_por_nos": _iso(d.data_recebimento_por_nos),
        "data_abertura_mediacao": _iso(d.data_abertura_mediacao),
        "data_finalizacao_mediacao": _iso(d.data_finalizacao_mediacao),
        "preco_produto": _texto(d.preco_produto),
        "claim_id": d.claim_id,
        "produto_sku": d.produto.sku,
        "produto_nome": d.produto.nome,
        # ---- Campos manuais SEM par na tela (só pra referência) ----
        "numero_nota_fiscal": d.numero_nota_fiscal,
        "reembolsado": d.reembolsado,
        "valor_reembolsado": _texto(d.valor_reembolsado),
        "destino_produto": d.destino_produto,
        "relatorio_impresso_em": _iso(d.relatorio_impresso_em),
        "motivo_reclamacao": d.motivo_reclamacao,
    }


linhas = []
resumo = {}

for conta, alias in BANCOS:
    # select_related('produto'): o SKU/nome do produto vêm na mesma consulta,
    # sem depender do roteador de banco (que só opina em requisição web).
    queryset = Devolucao.objects.using(alias).select_related("produto").order_by("criado_em")
    linhas_da_conta = [montar_linha(conta, d) for d in queryset]
    linhas.extend(linhas_da_conta)
    resumo[conta] = {
        "total": len(linhas_da_conta),
        "por_plataforma": dict(Counter(l["plataforma"] for l in linhas_da_conta)),
        "por_status_fluxo": dict(Counter(l["status_fluxo"] for l in linhas_da_conta)),
        "criadas_a_partir_da_ponte": sum(1 for l in linhas_da_conta if l["criada_a_partir_da_ponte"]),
        "com_claim_id": sum(1 for l in linhas_da_conta if l["claim_id"]),
    }

# ---- Terminal: resumo por empresa ----
tabela_resumo = Table(title="Devoluções no banco, por empresa", box=box.SIMPLE_HEAVY)
for coluna in ("Empresa", "Total", "Mercado Livre", "Outras plataformas", "A partir da ponte", "Com claim_id"):
    tabela_resumo.add_column(coluna)
for conta, r in resumo.items():
    ml = r["por_plataforma"].get("Mercado Livre", 0)
    outras = {p: n for p, n in r["por_plataforma"].items() if p != "Mercado Livre"}
    tabela_resumo.add_row(
        conta, str(r["total"]), str(ml),
        ", ".join(f"{p}: {n}" for p, n in outras.items()) or "—",
        str(r["criadas_a_partir_da_ponte"]), str(r["com_claim_id"]),
    )
console.print(tabela_resumo)

# ---- Terminal: amostra das devoluções de Mercado Livre ----
for conta, _alias in BANCOS:
    do_ml = [l for l in linhas if l["conta"] == conta and l["plataforma"] == "Mercado Livre"]
    tabela = Table(
        title=f"{conta} — Mercado Livre (primeiras {min(LINHAS_NO_TERMINAL, len(do_ml))} de {len(do_ml)})",
        box=box.SIMPLE_HEAVY,
    )
    for coluna in ("Pedido", "Criada", "Cliente", "Venda", "Receb. cliente", "Reclamação",
                   "Receb. nós", "Abert. med.", "Fim med.", "Preço", "Tipo"):
        tabela.add_column(coluna)
    for l in do_ml[:LINHAS_NO_TERMINAL]:
        tabela.add_row(
            l["numero_pedido"], _data_br(l["criado_em"]), (l["nome_cliente"] or "—")[:18],
            _data_br(l["data_venda"]), _data_br(l["data_recebimento_cliente"]),
            _data_br(l["data_reclamacao_cliente"]), _data_br(l["data_recebimento_por_nos"]),
            _data_br(l["data_abertura_mediacao"]), _data_br(l["data_finalizacao_mediacao"]),
            l["preco_produto"] or "—", l["tipo_venda"] or "—",
        )
    console.print(tabela)

# ---- JSON completo (já ignorado pelo .gitignore: scripts_exploracao_ML/*.json) ----
saida = {
    "gerado_em": datetime.now().isoformat(timespec="seconds"),
    "data_inicio_ponte": DATA_INICIO_PONTE.isoformat(),
    "resumo": resumo,
    "devolucoes": linhas,
}
CAMINHO_SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
console.print(f"\nJSON completo ({len(linhas)} devoluções): {CAMINHO_SAIDA}")