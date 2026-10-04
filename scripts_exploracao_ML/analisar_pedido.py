# scripts_exploracao_ML/analisar_pedido.py
#
# Percorre, para UM pedido, a cadeia de chamadas da API do Mercado Livre que
# o sistema de devoluções usa (compra -> reclamação -> devolução física) e
# mostra, para CADA chamada: o endpoint, os parâmetros, de onde veio o id
# usado, o status, o que trouxe, pra que serve e todos os campos devolvidos.
#
# O resultado vai para UM arquivo HTML fixo (sobrescrito a cada execução,
# sem histórico): scripts_exploracao_ML/logs/analise_pedido.html
# Deixe-o aberto no navegador e aperte F5 para ver o que mudou. A página é
# reescrita a cada chamada, então dá para acompanhar uma execução em andamento.
#
# Só leitura (só GET). Não grava nada no banco.
#
# Como rodar:
#   poetry run python scripts_exploracao_ML/analisar_pedido.py --empresa SV --pedido 2000018229470186
#
# Arquivos desta pasta usados por este script:
#   painel_html.py               -> preenche o modelo (só troca texto, sem Django)
#   modelo_analise_pedido.html   -> o HTML pronto, com os {{CAMPOS}} a preencher
#
# Chamadas, na ordem em que são feitas:
#   Etapa 1 - Compra:
#     GET /orders/{pedido}
#     GET /shipments/{ida}              (SEM header x-format-new, ver nota abaixo)
#     GET /shipments/{ida}/history      (COM header x-format-new)
#   Etapa 2 - Reclamação:
#     GET /post-purchase/v1/claims/search?order_id={pedido}
#     GET /post-purchase/v1/claims/{claim}            (uma por claim achada)
#     GET /post-purchase/v1/claims/{claim}/messages   (uma por claim achada)
#   Etapa 3 - Devolução física:
#     GET /post-purchase/v2/claims/{claim}/returns    (uma por claim achada)
#     GET /shipments/{volta}            (um por envio de volta listado)
#     GET /shipments/{volta}/history
#
# Chamada que depende de outra e não pôde ser feita aparece como "não
# executada" (cinza), dizendo de qual chamada dependia. Isso NÃO é erro.
#
# Nota sobre o header: views.py documenta que /shipments/{id} com
# x-format-new muda o formato e faz sender_address/receiver_address sumirem
# sem erro; por isso só o /history leva o header (igual à tela de Consultar
# Pedido).
#
# Sobre o tempo mostrado em cada chamada: é o tempo total dentro do
# chamar_api(), ou seja, INCLUI a espera de 0,4 s do espaçador entre
# chamadas da mesma conta e eventuais novas tentativas. Não é latência pura
# da API, e o número de tentativas não é exposto pelo chamar_api().
#
# Cuidado: o HTML guarda dados reais (nome do comprador, endereços). Ele fica
# em logs/, que está no .gitignore -- não copie para fora do projeto.

import argparse
import json
import re
import sys
import time
import traceback
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

_PASTA_DO_SCRIPT = Path(__file__).resolve().parent
_RAIZ_DO_PROJETO = _PASTA_DO_SCRIPT.parent
for _caminho in (_RAIZ_DO_PROJETO, _PASTA_DO_SCRIPT):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))

from api_mercado_livre.core.estrutura_api.cliente_api import (
    BASE_URL, chamar_api, ErroAPI, ErroAutenticacaoAPI,
)
from integracao_mercado_livre.traducoes_devolucao import (
    TRADUCAO_PAPEL,
    TRADUCAO_RESOLUTION_REASON,
    categorizar_motivo,
    traduzir_evento_envio,
    traduzir_resolucao,
    traduzir_tipo_e_etapa_claim,
)
import painel_html

PASTA_LOGS = _PASTA_DO_SCRIPT / "logs"
NOME_LOG = "analisar_pedido"
HEADER_FORMATO_NOVO = {"x-format-new": "true"}
FUSO = ZoneInfo("America/Sao_Paulo")
LIMITE_CAMPOS = 600     # linhas máximas na tabela "Todos os campos" de cada chamada
LIMITE_TEXTO = 300      # texto de um campo é cortado aqui (o JSON cru mostra inteiro)
LIMITE_JSON = 300_000   # JSON cru acima disso é cortado, pra página não ficar gigante

NOMES_ETAPAS = {1: "Compra", 2: "Reclamação", 3: "Devolução física"}
AUSENTE = "ausente ou null"

# ---------------------------------------------------------------------------
# Dicionários de tradução (copiados de consultar_fluxo_devolucao.py, que os
# tirou da documentação oficial). Código que não estiver aqui aparece CRU,
# com selo "sem tradução confirmada" -- nunca inventamos texto.
# ---------------------------------------------------------------------------

STATUS_PEDIDO = {
    "confirmed": "Confirmado",
    "payment_required": "Aguardando pagamento",
    "payment_in_process": "Pagamento em processamento",
    "paid": "Pago",
    "cancelled": "Cancelado",
    "invalid": "Inválido",
}

STATUS_ENVIO = {
    "to_be_agreed": "A combinar",
    "pending": "Pendente",
    "handling": "Em processamento",
    "ready_to_ship": "Pronto pra envio",
    "shipped": "Despachado",
    "delivered": "Entregue",
    "not_delivered": "Não entregue",
    "cancelled": "Cancelado",
}

SUBSTATUS_CONHECIDOS = {
    "ready_to_print": "Etiqueta pronta pra impressão",
    "printed": "Etiqueta impressa",
    "in_warehouse": "No depósito/CD",
    "ready_to_pack": "Pronto pra embalar",
    "packed": "Embalado",
    "in_packing_list": "Na lista de coleta (romaneio)",
    "first_visit": "1ª tentativa de entrega",
    "second_visit": "2ª tentativa de entrega",
    "invoice_pending": "Aguardando nota fiscal",
    "waiting_for_label_generation": "Aguardando geração da etiqueta",
    "in_pickup_list": "Na lista de coleta pra retirada",
    "dropped_off": "Deixado em ponto de coleta pelo comprador",
    "picked_up": "Coletado pela transportadora",
    "in_hub": "No hub de triagem da transportadora",
}

STATUS_RECLAMACAO = {
    "opened": "Aberta",
    "closed": "Fechada",
}

STATUS_DINHEIRO = {
    "retained": "Retido na sua conta (aguardando desfecho)",
    "refunded": "Devolvido ao comprador",
    "available": "Liberado / disponível pra você",
}

QUANDO_REEMBOLSA = {
    "shipped": "assim que o comprador despachar a devolução",
    "delivered": "3 dias depois de você receber a devolução de volta",
    "n/a": "não se aplica (caso sem devolução física do produto)",
}

STATUS_DEVOLUCAO = {
    "pending_cancel": "Em processo de cancelamento",
    "pending": "Criada, gerando o envio de volta",
    "failed": "Falha ao criar/gerar o envio de volta",
    "shipped": "Enviada de volta — dinheiro retido",
    "pending_delivered": "Em processo de confirmar entrega",
    "return_to_buyer": "Retornando ao comprador",
    "pending_expiration": "Em processo de expiração",
    "scheduled": "Retirada programada",
    "pending_failure": "Em processo de registrar falha",
    "label_generated": "Etiqueta gerada — pronta pra envio",
    "cancelled": "Cancelada — dinheiro disponível",
    "not_delivered": "Não entregue",
    "expired": "Expirada",
    "delivered": "Nas suas mãos (você já recebeu de volta)",
}

SUBTIPO_DEVOLUCAO = {
    "low_cost": "Devolução automática (low cost)",
    "return_partial": "Devolução parcial",
    "return_total": "Devolução total",
}

STATUS_ENVIO_DEVOLUCAO = {
    "pending": "Aguardando geração do envio",
    "ready_to_ship": "Etiqueta pronta pra despacho",
    "shipped": "Despachado",
    "not_delivered": "Não entregue",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

TIPO_ENVIO_DEVOLUCAO = {
    "return": "Envio de volta (comprador/CD → depósito Mercado Livre)",
    "return_from_triage": "Envio de triagem (depósito → revisão interna)",
}

DESTINO_ENVIO_DEVOLUCAO = {
    "seller_address": "Seu endereço (vendedor)",
    "warehouse": "Depósito do Mercado Livre",
}

PAPEL_MENSAGEM = {
    "mediator": "mediador (Mercado Livre)",
    "complainant": "reclamante",
    "respondent": "respondente",
}


# ---------------------------------------------------------------------------
# Pequenos ajudantes de formatação
# ---------------------------------------------------------------------------

def _ascii(texto):
    """Só pro console: tira acento, pra não sair lixo em terminal antigo."""
    normalizado = unicodedata.normalize("NFKD", str(texto))
    return normalizado.encode("ascii", "ignore").decode("ascii")


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _decimal_br(numero, casas=1):
    return f"{numero:.{casas}f}".replace(".", ",")


def _tempo_legivel(segundos):
    if segundos < 1:
        return f"{round(segundos * 1000)} ms"
    return f"{_decimal_br(segundos)} s"


def _parse_data(valor):
    if not valor or not isinstance(valor, str):
        return None
    try:
        data = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return data if data.tzinfo else None


def _fmt_data(valor):
    """ISO 8601 da API -> dd/mm/aaaa às HH:MM (horário de Brasília).
    Cada campo da API vem com um offset diferente; aqui tudo é normalizado.
    Se não der pra interpretar, devolve o texto como veio."""
    if valor is None or valor == "":
        return AUSENTE
    data = _parse_data(valor)
    if data is None:
        return str(valor)
    return data.astimezone(FUSO).strftime("%d/%m/%Y às %H:%M")


def _fmt_dinheiro(valor, moeda=""):
    if valor is None:
        return AUSENTE
    try:
        texto = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(valor)
    return f"{texto} {moeda}".strip()


def _get(dado, *caminho):
    """dado['a']['b']['c'] sem estourar quando algo no meio falta ou não é dict."""
    for chave in caminho:
        if not isinstance(dado, dict):
            return None
        dado = dado.get(chave)
    return dado


def _texto_curto(valor, limite=LIMITE_TEXTO):
    texto = str(valor)
    return texto if len(texto) <= limite else texto[:limite] + f"… (+{len(texto) - limite} caracteres)"


def _achatar(dado):
    """JSON -> lista de (caminho, valor em texto). Ex: ('orders[0].item_id', '123')."""
    linhas = []

    def ir(o, caminho):
        if isinstance(o, dict):
            if not o:
                linhas.append((caminho or "(raiz)", "{} (vazio)"))
                return
            for chave, valor in o.items():
                ir(valor, f"{caminho}.{chave}" if caminho else str(chave))
        elif isinstance(o, list):
            if not o:
                linhas.append((caminho or "(raiz)", "[] (vazia)"))
                return
            for i, valor in enumerate(o):
                ir(valor, f"{caminho}[{i}]")
        elif isinstance(o, str):
            linhas.append((caminho or "(raiz)", _texto_curto(o)))
        else:
            linhas.append((caminho or "(raiz)", json.dumps(o, ensure_ascii=False)))

    ir(dado, "")
    return linhas


def _json_cru(dado):
    texto = json.dumps(dado, ensure_ascii=False, indent=2)
    if len(texto) > LIMITE_JSON:
        texto = texto[:LIMITE_JSON] + f"\n… (cortado: +{len(texto) - LIMITE_JSON} caracteres)"
    return texto


def _fato(rotulo, valor, campo_api, selo=None):
    """Uma linha de 'O que trouxe'. selo = ('ok'|'av', texto) ou None."""
    return {
        "ROTULO": rotulo,
        "VALOR": valor,
        "CAMPO_API": campo_api,
        "SELO": [{"ESTADO": selo[0], "TEXTO": selo[1]}] if selo else [],
    }


def _selo_dic(dicionario, codigo):
    if codigo is None:
        return None
    if codigo in dicionario:
        return ("ok", "confirmado")
    return ("av", "sem tradução confirmada — código cru")


def _selo_flag(confirmado):
    return ("ok", "confirmado") if confirmado else ("av", "sem tradução confirmada — código cru")


def _traduz(dicionario, codigo):
    if codigo is None:
        return AUSENTE
    return dicionario.get(codigo, codigo)


def _traduzir_evento(status, substatus):
    """traduzir_evento_envio exige texto em status; aqui nunca estoura."""
    try:
        return traduzir_evento_envio(str(status), substatus)
    except Exception:
        return {"texto": None, "bruto": f"{status}/{substatus}", "confirmado": False}


def _resumir_endereco(endereco):
    """Cidade/UF + tipos do endereço. Rua e número ficam só na tabela de campos."""
    if not isinstance(endereco, dict):
        return AUSENTE
    cidade = _get(endereco, "city", "name") or "—"
    uf = (_get(endereco, "state", "id") or "").replace("BR-", "") or "—"
    tipos = ", ".join(endereco.get("types") or []) or "sem tipos"
    mascarada = " · rua mascarada" if endereco.get("street_name") == "XXXXXXX" else ""
    return f"{cidade}/{uf} · tipos: {tipos}{mascarada}"


# ---------------------------------------------------------------------------
# Extratores: recebem o JSON de UMA resposta e devolvem
#   (resumo curto, lista de fatos, {caminho: tradução} pra tabela de campos).
# Só aparecem como "fato" campos que o sistema já usa (ou que a doc oficial
# descreve e queremos conferir, marcados com selo amarelo). O resto da
# resposta fica visível em "Todos os campos" e "JSON cru".
# ---------------------------------------------------------------------------

def extrair_pedido(p, pedido_consultado):
    fatos, traducoes = [], {}

    id_pedido = p.get("id")
    if id_pedido is None:
        fatos.append(_fato("Número do pedido (id)", AUSENTE, "id", ("av", "esperado igual ao número consultado")))
    elif str(id_pedido) == str(pedido_consultado):
        fatos.append(_fato("Número do pedido (id)", id_pedido, "id", ("ok", "igual ao número consultado")))
    else:
        fatos.append(_fato("Número do pedido (id)", id_pedido, "id",
                           ("av", f"DIFERENTE do consultado ({pedido_consultado})")))

    status = p.get("status")
    status_txt = _traduz(STATUS_PEDIDO, status)
    if status in STATUS_PEDIDO:
        traducoes["status"] = status_txt
    fatos.append(_fato("Status do pedido", status_txt, f"status = {status}", _selo_dic(STATUS_PEDIDO, status)))
    fatos.append(_fato("Criado em", _fmt_data(p.get("date_created")), "date_created"))

    comprador = p.get("buyer") or {}
    nome = " ".join(x for x in (comprador.get("first_name"), comprador.get("last_name")) if x) or AUSENTE
    fatos.append(_fato("Comprador", nome, "buyer.first_name + buyer.last_name"))

    itens = [i for i in (p.get("order_items") or []) if isinstance(i, dict)]
    moeda = p.get("currency_id") or ""
    soma, soma_valida = 0.0, bool(itens)
    for indice, item in enumerate(itens):
        quantidade, preco = item.get("quantity"), item.get("unit_price")
        try:
            soma += float(quantidade) * float(preco)
        except (TypeError, ValueError):
            soma_valida = False
        if indice < 10:
            titulo = _get(item, "item", "title") or "—"
            fatos.append(_fato(
                f"Item {indice + 1}",
                f"{titulo} — {quantidade} × {_fmt_dinheiro(preco, moeda)}",
                f"order_items[{indice}].item.title · quantity · unit_price",
            ))
    if soma_valida:
        fatos.append(_fato("Soma dos itens", _fmt_dinheiro(soma, moeda),
                           "Σ quantity × unit_price (conta feita pelo script)"))

    aviso_novo = ("av", "campo da doc de Orders, ainda não usado pelo sistema — conferir")
    fatos.append(_fato("Total do pedido", _fmt_dinheiro(p.get("total_amount"), moeda), "total_amount", aviso_novo))
    fatos.append(_fato("Total pago", _fmt_dinheiro(p.get("paid_amount"), moeda), "paid_amount", aviso_novo))

    pagamentos = p.get("payments")
    fatos.append(_fato(
        "Pagamentos",
        _plural(len(pagamentos), "registro", "registros") + " (detalhe em «Todos os campos»)"
        if isinstance(pagamentos, list) else AUSENTE,
        "payments",
    ))

    envio = p.get("shipping") or {}
    id_envio = envio.get("id")
    fatos.append(_fato("ID do envio de ida", id_envio if id_envio else AUSENTE, "shipping.id"))
    tipo_logistico = envio.get("logistic_type")
    fatos.append(_fato(
        "Tipo logístico (o que a tela usa p/ FULL)",
        tipo_logistico if tipo_logistico else AUSENTE,
        "shipping.logistic_type",
        ("av", "regra da tela (views.py): só 'fulfillment' vira FULL; qualquer outro valor, ou ausente, vira 'comum'"),
    ))
    pack = p.get("pack_id")
    fatos.append(_fato("Pack ID", pack if pack else "sem pack (null)", "pack_id"))

    partes = [status_txt, _plural(len(itens), "item", "itens")]
    if soma_valida:
        partes.append(_fmt_dinheiro(soma, moeda))
    partes.append(f"envio {id_envio}" if id_envio else "sem envio")
    return " · ".join(partes), fatos, traducoes


def extrair_envio(e):
    fatos, traducoes = [], {}

    status = e.get("status")
    status_txt = _traduz(STATUS_ENVIO, status)
    if status in STATUS_ENVIO:
        traducoes["status"] = status_txt
    fatos.append(_fato("Status", status_txt, f"status = {status}", _selo_dic(STATUS_ENVIO, status)))

    substatus = e.get("substatus")
    if substatus is not None:
        sub_txt = _traduz(SUBSTATUS_CONHECIDOS, substatus)
        if substatus in SUBSTATUS_CONHECIDOS:
            traducoes["substatus"] = sub_txt
        fatos.append(_fato("Substatus", sub_txt, f"substatus = {substatus}", _selo_dic(SUBSTATUS_CONHECIDOS, substatus)))

    interpretacao = ("av", "interpretação do script, a validar: só 'fulfillment' vira FULL")
    fatos.append(_fato("Tipo logístico (raiz)", e.get("logistic_type") or AUSENTE, "logistic_type", interpretacao))
    fatos.append(_fato("Tipo logístico (aninhado)", _get(e, "logistic", "type") or AUSENTE, "logistic.type", interpretacao))

    fatos.append(_fato("Origem (quem despacha)", _resumir_endereco(e.get("sender_address")), "sender_address"))
    fatos.append(_fato("Destino (quem recebe)", _resumir_endereco(e.get("receiver_address")), "receiver_address"))
    fatos.append(_fato("Última atualização", _fmt_data(e.get("last_updated")), "last_updated"))

    resumo = status_txt + (f" / {_traduz(SUBSTATUS_CONHECIDOS, substatus)}" if substatus is not None else "")
    return resumo, fatos, traducoes


def extrair_historico(historico):
    if not isinstance(historico, list):
        raise ValueError(f"esperava uma lista de eventos, veio {type(historico).__name__}")
    fatos, traducoes = [], {}

    eventos = [(i, ev) for i, ev in enumerate(historico) if isinstance(ev, dict)]
    for indice, ev in eventos:
        traducao = _traduzir_evento(ev.get("status"), ev.get("substatus"))
        traducoes[f"[{indice}].status"] = traducao["texto"] if traducao["confirmado"] else "sem tradução confirmada"

    def ordem(par):
        data = _parse_data(par[1].get("date"))
        return (data is None, data.timestamp() if data else 0)

    eventos.sort(key=ordem)
    fatos.append(_fato("Eventos", len(historico), "(lista)"))

    def descrever(ev):
        traducao = _traduzir_evento(ev.get("status"), ev.get("substatus"))
        texto = traducao["texto"] or traducao["bruto"]
        return f"{_fmt_data(ev.get('date'))} — {texto}", traducao

    ultimo_texto = "—"
    if eventos:
        texto, traducao = descrever(eventos[0][1])
        fatos.append(_fato("Primeiro evento", texto, "status / substatus · date", _selo_flag(traducao["confirmado"])))
        ultimo_texto, traducao = descrever(eventos[-1][1])
        fatos.append(_fato("Último evento", ultimo_texto, "status / substatus · date", _selo_flag(traducao["confirmado"])))

    entregues = [ev for _, ev in eventos if ev.get("status") == "delivered"]
    fatos.append(_fato(
        "Entregue em",
        _fmt_data(entregues[-1].get("date")) if entregues else "nenhum evento com status delivered",
        "último evento com status = delivered",
    ))
    return f"{_plural(len(historico), 'evento', 'eventos')} · último: {ultimo_texto}", fatos, traducoes


def _claims_da_busca(busca):
    """[(posição em data[], claim)] -- aceita {"data": [...]} ou lista direta."""
    lista = busca.get("data") if isinstance(busca, dict) else busca
    return [(i, c) for i, c in enumerate(lista or []) if isinstance(c, dict)]


def extrair_busca_claims(busca):
    claims = _claims_da_busca(busca)
    fatos = [_fato("Claims encontradas", len(claims), "data")]
    for indice, claim in claims:
        tt = traduzir_tipo_e_etapa_claim(claim.get("type"), claim.get("stage"))
        status = claim.get("status")
        confirmado = tt["confirmado"] and status in STATUS_RECLAMACAO
        fatos.append(_fato(
            f"Claim {indice + 1}",
            f"{claim.get('id')} · {tt['texto']} · {_traduz(STATUS_RECLAMACAO, status)} · criada {_fmt_data(claim.get('date_created'))}",
            f"data[{indice}].id · type · stage · status · date_created",
            _selo_flag(confirmado),
        ))
    if not claims:
        return "Nenhuma claim para este pedido", fatos, {}
    return f"{_plural(len(claims), 'claim', 'claims')}: " + ", ".join(str(c.get("id")) for _, c in claims), fatos, {}


def extrair_claim(c):
    fatos, traducoes = [], {}

    tt = traduzir_tipo_e_etapa_claim(c.get("type"), c.get("stage"))
    fatos.append(_fato("Tipo / etapa", tt["texto"], f"type = {c.get('type')} · stage = {c.get('stage')}",
                       _selo_flag(tt["confirmado"])))

    status = c.get("status")
    status_txt = _traduz(STATUS_RECLAMACAO, status)
    if status in STATUS_RECLAMACAO:
        traducoes["status"] = status_txt
    fatos.append(_fato("Status", status_txt, f"status = {status}", _selo_dic(STATUS_RECLAMACAO, status)))

    motivo = categorizar_motivo(c.get("reason_id"))
    fatos.append(_fato("Motivo", motivo["texto"], f"reason_id = {c.get('reason_id')}", _selo_flag(motivo["confirmado"])))
    fatos.append(_fato("Criada em", _fmt_data(c.get("date_created")), "date_created"))

    jogadores = [p for p in (c.get("players") or []) if isinstance(p, dict)]
    fatos.append(_fato(
        "Jogadores",
        " · ".join(f"{TRADUCAO_PAPEL.get(p.get('role'), p.get('role'))}: {p.get('user_id')}" for p in jogadores) or AUSENTE,
        "players[].role · user_id",
    ))

    resolucao = c.get("resolution")
    traducao_resolucao = traduzir_resolucao(resolucao)
    fatos.append(_fato("Resolução", traducao_resolucao["texto"],
                       "resolution.reason · closed_by · benefited · applied_coverage",
                       _selo_flag(traducao_resolucao["confirmado"])))
    razao = _get(c, "resolution", "reason")
    if razao is None:
        fatos.append(_fato("Razão da resolução (cru)", "sem resolution.reason", "resolution.reason"))
    else:
        fatos.append(_fato("Razão da resolução (cru)", razao, "resolution.reason", _selo_dic(TRADUCAO_RESOLUTION_REASON, razao)))

    resumo = " · ".join([status_txt, tt["texto"], traducao_resolucao["motivo_curto"]])
    return resumo, fatos, traducoes


def extrair_mensagens(mensagens):
    if not isinstance(mensagens, list):
        raise ValueError(f"esperava uma lista de mensagens, veio {type(mensagens).__name__}")
    fatos = []
    validas = [m for m in mensagens if isinstance(m, dict)]

    contagem = {}
    anexos = 0
    for m in validas:
        contagem[m.get("sender_role")] = contagem.get(m.get("sender_role"), 0) + 1
        anexos += len(m.get("attachments") or [])
    fatos.append(_fato("Mensagens", len(validas), "(lista)"))
    for papel, quantidade in sorted(contagem.items(), key=lambda par: str(par[0])):
        fatos.append(_fato(f"De: {PAPEL_MENSAGEM.get(papel, papel)}", quantidade, "sender_role",
                           _selo_dic(PAPEL_MENSAGEM, papel)))
    fatos.append(_fato("Anexos (soma)", anexos, "attachments"))

    ordenadas = sorted(validas, key=lambda m: m.get("date_created") or "")

    def descrever(m):
        return (f"{_fmt_data(m.get('date_created'))} — {PAPEL_MENSAGEM.get(m.get('sender_role'), m.get('sender_role'))}"
                f" · stage = {m.get('stage')}")

    if ordenadas:
        fatos.append(_fato("Primeira mensagem", descrever(ordenadas[0]), "date_created · sender_role · stage"))
        da_disputa = [m for m in ordenadas if m.get("stage") == "dispute"]
        if da_disputa:
            fatos.append(_fato(
                "1ª mensagem da disputa", descrever(da_disputa[0]), "primeira com stage = dispute",
                ("av", "melhor aproximação disponível da abertura da disputa (a doc oficial não tem campo próprio)"),
            ))
        else:
            fatos.append(_fato("1ª mensagem da disputa", "nenhuma mensagem com stage = dispute", "stage"))
        fatos.append(_fato("Última mensagem", descrever(ordenadas[-1]), "date_created · sender_role · stage"))
    return _plural(len(validas), "mensagem", "mensagens"), fatos, {}


def _envios_da_devolucao(retorno):
    """[(posição em shipments[], shipment_id ou None)]. shipments pode vir null."""
    envios = (retorno.get("shipments") or []) if isinstance(retorno, dict) else []
    return [(i, e.get("shipment_id")) for i, e in enumerate(envios) if isinstance(e, dict)]


def extrair_devolucao(r):
    fatos, traducoes = [], {}

    status = r.get("status")
    status_txt = _traduz(STATUS_DEVOLUCAO, status)
    if status in STATUS_DEVOLUCAO:
        traducoes["status"] = status_txt
    fatos.append(_fato("Status da devolução", status_txt, f"status = {status}", _selo_dic(STATUS_DEVOLUCAO, status)))

    subtipo = r.get("subtype")
    fatos.append(_fato("Subtipo", _traduz(SUBTIPO_DEVOLUCAO, subtipo), f"subtype = {subtipo}", _selo_dic(SUBTIPO_DEVOLUCAO, subtipo)))
    fatos.append(_fato("Criada em", _fmt_data(r.get("date_created")), "date_created"))
    fatos.append(_fato("Fechada em", _fmt_data(r.get("date_closed")), "date_closed"))
    fatos.append(_fato("Última atualização", _fmt_data(r.get("last_updated")), "last_updated"))

    dinheiro = r.get("status_money")
    explicacao = f"; o dicionário do script diz: {STATUS_DINHEIRO[dinheiro]}" if dinheiro in STATUS_DINHEIRO else ""
    fatos.append(_fato("Dinheiro (status_money)", dinheiro if dinheiro is not None else AUSENTE, "status_money",
                       ("av", f"significado em aberto no vault{explicacao}")))

    reembolso = r.get("refund_at")
    fatos.append(_fato("Quando reembolsa", _traduz(QUANDO_REEMBOLSA, reembolso), f"refund_at = {reembolso}",
                       _selo_dic(QUANDO_REEMBOLSA, reembolso)))

    for indice, item in enumerate(r.get("orders") or []):
        if not isinstance(item, dict):
            continue
        fatos.append(_fato(
            f"Item da devolução {indice + 1}",
            f"{item.get('item_id')} — devolve {item.get('return_quantity')} de {item.get('total_quantity')}",
            f"orders[{indice}].item_id · return_quantity · total_quantity",
        ))

    envios = [(i, e) for i, e in enumerate(r.get("shipments") or []) if isinstance(e, dict)]
    if not envios:
        fatos.append(_fato("Envios de volta", "nenhum (shipments vazio ou null)", "shipments"))
    for indice, envio in envios:
        tipo, st = envio.get("type"), envio.get("status")
        destino = _get(envio, "destination", "name")
        fatos.append(_fato(
            f"Envio de volta {indice + 1}",
            f"{envio.get('shipment_id')} · {_traduz(TIPO_ENVIO_DEVOLUCAO, tipo)} · {_traduz(STATUS_ENVIO_DEVOLUCAO, st)}"
            f" · destino: {_traduz(DESTINO_ENVIO_DEVOLUCAO, destino)} · rastreio: {envio.get('tracking_number') or AUSENTE}",
            f"shipments[{indice}].shipment_id · type · status · destination.name · tracking_number",
            _selo_flag(tipo in TIPO_ENVIO_DEVOLUCAO and st in STATUS_ENVIO_DEVOLUCAO
                       and (destino is None or destino in DESTINO_ENVIO_DEVOLUCAO)),
        ))

    resumo = " · ".join([status_txt, _traduz(SUBTIPO_DEVOLUCAO, subtipo), _plural(len(envios), "envio de volta", "envios de volta")])
    return resumo, fatos, traducoes


# ---------------------------------------------------------------------------
# A análise: faz as chamadas, guarda um registro por chamada, reescreve o HTML
# ---------------------------------------------------------------------------

_PADRAO_ERRO_HTTP = re.compile(r"Erro\s+(\d{3})\s+em\s+[^:]*:\s*(.*)", re.S)


def _corpo_legivel(texto):
    texto = (texto or "").strip()
    if not texto:
        return "(corpo vazio)"
    try:
        return json.dumps(json.loads(texto), ensure_ascii=False, indent=2)
    except ValueError:
        return texto[:4000]


def _classificar_falha(erro):
    """Exceção -> (estado, status que aparece na pílula, resumo, nota, corpo do erro ou None)."""
    mensagem = str(erro)

    if isinstance(erro, ErroAutenticacaoAPI):
        return ("er", "401", "Falhou: autenticação (401) — nenhum dado recebido",
                ("Falhou.", "A API recusou o token (401). Não é problema do pedido: confira o token da conta."), mensagem)

    if isinstance(erro, ErroAPI):
        if "Número máximo de tentativas" in mensagem:
            return ("er", "429", "Falhou: limite de chamadas (429) esgotou as tentativas — o dado NÃO foi lido",
                    ("429 esgotado.", "Todas as tentativas bateram no limite de chamadas. Isto NÃO significa que o dado não existe: "
                                      "só que não conseguimos ler. Rode de novo."), mensagem)
        if "Timeout esgotado" in mensagem:
            return ("er", "timeout", "Falhou: timeout — nenhum dado recebido",
                    ("Falhou.", "Timeout esgotado depois das tentativas. Falha de rede, diferente de um 404."), mensagem)
        achado = _PADRAO_ERRO_HTTP.search(mensagem)
        if achado:
            codigo, corpo = achado.group(1), _corpo_legivel(achado.group(2))
            if codigo == "404":
                return ("av", "404", "A API respondeu 404 (não encontrado) — nenhum dado",
                        ("404 confirmado.", "Resposta válida da API, não é falha de rede: diferente de 429 e de timeout, "
                                            "aqui a API disse que este recurso não existe."), corpo)
            return ("er", codigo, f"A API respondeu {codigo} — nenhum dado recebido",
                    (f"Erro {codigo}.", "A API recusou a chamada. O corpo da resposta está logo abaixo."), corpo)
        return ("er", "erro", "Falhou: erro da API — nenhum dado recebido",
                ("Falhou.", "Erro da API em formato que o script não reconheceu."), mensagem)

    return ("er", "erro", f"Falhou: {type(erro).__name__} — nenhum dado recebido",
            ("Falhou.", f"Erro fora da API ({type(erro).__name__}), por exemplo conexão. O script segue para as próximas chamadas."),
            mensagem)


class Analise:
    def __init__(self, conta, pedido):
        self.conta = conta
        self.pedido = pedido
        self.registros = []          # [(etapa, registro)]
        self.inicio = time.perf_counter()

    # --- montagem de cada registro ---------------------------------------

    def _base(self, etapa, nome, modelo, objetivo, origem):
        n_origem, texto_origem = origem
        return {
            "NUM": len(self.registros) + 1,
            "NOME": nome,
            "METODO": "GET",
            "ENDPOINT_MODELO": modelo,
            "TROUXE": "",
            "ESTADO": "nd",
            "STATUS": "—",
            "TEMPO": "—",
            "ABRIR_HTML": "",
            "PARA_QUE": objetivo,
            "ORIGEM": texto_origem if n_origem is None else f"#{n_origem} → {texto_origem}",
            "ORIGEM_ANCORA": "topo" if n_origem is None else f"c{n_origem}",
            "PARAMS": [],
            "URL": "",
            "NOTA": [],
            "DADOS": [],
            "ERRO_CORPO": [],
        }

    def executar(self, etapa, nome, modelo, endpoint, objetivo, origem, extrator,
                 vars_caminho=None, params=None, headers=None, dica_404=""):
        """Faz UMA chamada GET, registra tudo e devolve (json ou None, número da chamada)."""
        registro = self._base(etapa, nome, modelo, objetivo, origem)
        textos_param = list(vars_caminho or [])
        textos_param += [f"{k} = {v}" for k, v in (params or {}).items()]
        textos_param += [f"header {k} = {v}" for k, v in (headers or {}).items()]
        registro["PARAMS"] = [{"TEXTO": t} for t in (textos_param or ["nenhum"])]
        registro["URL"] = f"{BASE_URL}{endpoint}" + (f"?{urlencode(params)}" if params else "")

        inicio = time.perf_counter()
        resposta, falha = None, None
        try:
            resposta = chamar_api(
                "GET", endpoint, pasta_logs=PASTA_LOGS, conta=self.conta,
                params=params, headers_extra=headers, nome_log=NOME_LOG,
            )
        except Exception as erro:  # qualquer falha vira um cartão vermelho; o script não morre
            falha = erro
        registro["TEMPO"] = _tempo_legivel(time.perf_counter() - inicio)

        dados = None
        if falha is not None:
            estado, status, resumo, nota, corpo = _classificar_falha(falha)
            if estado == "av" and dica_404:
                nota = (nota[0], f"{nota[1]} {dica_404}")
            registro.update(ESTADO=estado, STATUS=status, TROUXE=resumo)
            registro["NOTA"] = [{"ESTADO": estado, "TITULO": nota[0], "TEXTO": nota[1]}]
            if corpo:
                registro["ERRO_CORPO"] = [{"TEXTO": corpo}]
        else:
            codigo = getattr(resposta, "status_code", None)
            try:
                dados = resposta.json()
            except ValueError:
                registro.update(ESTADO="er", STATUS=str(codigo), TROUXE=f"Resposta {codigo}, mas o corpo não é JSON válido")
                registro["NOTA"] = [{"ESTADO": "er", "TITULO": "Corpo ilegível.",
                                     "TEXTO": "A API respondeu com sucesso, mas o corpo não é JSON. Veja o texto abaixo."}]
                registro["ERRO_CORPO"] = [{"TEXTO": (getattr(resposta, "text", "") or "")[:4000] or "(corpo vazio)"}]
            else:
                registro.update(ESTADO="ok", STATUS=str(codigo))
                if codigo == 206:
                    registro["ESTADO"] = "av"
                    registro["NOTA"] = [{"ESTADO": "av", "TITULO": "Resposta parcial (206).",
                                         "TEXTO": "A API devolveu só parte dos dados. Não tire conclusão de campo ausente aqui."}]
                try:
                    resumo, fatos, traducoes = extrator(dados)
                except Exception as erro_extrator:
                    resumo = "Resumo indisponível (o script não conseguiu ler esta resposta) — os dados completos estão abaixo"
                    fatos = [_fato("Resumo", "indisponível", "—")]
                    traducoes = {}
                    registro["NOTA"] = registro["NOTA"] + [{
                        "ESTADO": "av", "TITULO": "Resumo indisponível.",
                        "TEXTO": f"Erro do script ao ler a resposta ({type(erro_extrator).__name__}: {erro_extrator}). "
                                 "A resposta da API veio normal; os campos estão na tabela e no JSON cru.",
                    }]
                registro["TROUXE"] = resumo
                linhas = _achatar(dados)
                tabela = [{"CAMINHO": c, "VALOR": v, "TRADUCAO": traducoes.get(c)} for c, v in linhas[:LIMITE_CAMPOS]]
                if len(linhas) > LIMITE_CAMPOS:
                    tabela.append({"CAMINHO": "(…)", "VALOR": f"+{len(linhas) - LIMITE_CAMPOS} linhas não mostradas — veja o JSON cru",
                                   "TRADUCAO": None})
                registro["DADOS"] = [{
                    "FATOS": fatos,
                    "CAMPOS_QTD": str(len(linhas)) if len(linhas) <= LIMITE_CAMPOS else f"{LIMITE_CAMPOS} de {len(linhas)}",
                    "CAMPOS": tabela,
                    "JSON_CRU": _json_cru(dados),
                }]

        return dados, self._registrar(etapa, registro)

    def pular(self, etapa, nome, modelo, objetivo, origem, motivo):
        """Registra uma chamada que NÃO foi feita porque depende de outra que não trouxe dado."""
        registro = self._base(etapa, nome, modelo, objetivo, origem)
        registro.update(
            ESTADO="nd", STATUS="não executada", TEMPO="—",
            TROUXE=f"Não executada: {motivo}",
            URL="(não chamada)",
            PARAMS=[{"TEXTO": "(não definidos: a chamada não foi feita)"}],
            NOTA=[{"ESTADO": "nd", "TITULO": "Não executada.",
                   "TEXTO": f"Depende de outra chamada: {motivo} Nenhuma chamada foi feita — isto não é erro, é dependência."}],
        )
        return self._registrar(etapa, registro)

    def _registrar(self, etapa, registro):
        if registro["ESTADO"] in ("av", "er"):
            registro["ABRIR_HTML"] = " open"   # o que pede atenção já nasce aberto
        self.registros.append((etapa, registro))
        print(_ascii(
            f"[#{registro['NUM']:>2}] {registro['STATUS']:<14} GET {registro['ENDPOINT_MODELO']:<52} {registro['TEMPO']}"
        ))
        self.gravar(f"executando… {_plural(self._feitas(), 'chamada feita', 'chamadas feitas')}")
        return registro["NUM"]

    # --- página -----------------------------------------------------------

    def _feitas(self):
        return sum(1 for _, r in self.registros if r["ESTADO"] != "nd")

    @staticmethod
    def _contagem(registros):
        """['2 × 200', '1 × 404', '1 não executada'] na ordem ok, av, er, nd."""
        grupos = {}
        for r in registros:
            if r["ESTADO"] != "nd":
                grupos[(r["ESTADO"], r["STATUS"])] = grupos.get((r["ESTADO"], r["STATUS"]), 0) + 1
        ordem = {"ok": 0, "av": 1, "er": 2}
        resultado = [(estado, f"{q} × {status}") for (estado, status), q in
                     sorted(grupos.items(), key=lambda kv: (ordem[kv[0][0]], kv[0][1]))]
        nao_executadas = sum(1 for r in registros if r["ESTADO"] == "nd")
        if nao_executadas:
            resultado.append(("nd", _plural(nao_executadas, "não executada", "não executadas")))
        return resultado

    def dados_pagina(self, situacao):
        todos = [r for _, r in self.registros]
        etapas_presentes = sorted({etapa for etapa, _ in self.registros})
        etapas = []
        for numero in etapas_presentes:
            registros = [r for e, r in self.registros if e == numero]
            partes = [_plural(len(registros), "chamada", "chamadas")] + [t for _, t in self._contagem(registros)]
            etapas.append({
                "N": numero,
                "NOME": NOMES_ETAPAS[numero],
                "PONTOS": [{"ESTADO": r["ESTADO"]} for r in registros],
                "CONTAGEM": " · ".join(partes),
                "CHAMADAS": registros,
            })
        return {
            "PEDIDO": self.pedido,
            "CONTA": self.conta,
            "GERADO_EM": datetime.now(FUSO).strftime("%d/%m/%Y às %H:%M:%S"),
            "TOTAL_CHAMADAS": self._feitas(),
            "TEMPO_TOTAL": _tempo_legivel(time.perf_counter() - self.inicio),
            "SITUACAO": situacao,
            "RESUMO": [{"ESTADO": estado, "TEXTO": texto} for estado, texto in self._contagem(todos)],
            "FAIXA": [{"N": e["N"], "NOME": e["NOME"], "PONTOS": e["PONTOS"]} for e in etapas],
            "ETAPAS": etapas,
        }

    def gravar(self, situacao):
        return painel_html.gravar_painel(self.dados_pagina(situacao))


# ---------------------------------------------------------------------------
# O roteiro: qual chamada vem depois de qual
# ---------------------------------------------------------------------------

def percorrer(a):
    pedido = a.pedido

    # ---------------- Etapa 1 - Compra ----------------
    dados_pedido, n_pedido = a.executar(
        1, "Pedido", "/orders/{pedido}", f"/orders/{pedido}",
        "Dados da venda: status, comprador, itens, valores e o id do envio de ida (shipping.id).",
        (None, "entrada (número do pedido)"),
        lambda d: extrair_pedido(d, pedido),
        vars_caminho=[f"pedido = {pedido}"],
        dica_404="Se este número for um Pack ID (e não um pedido), /orders responde 404 — veja investigar_pack.py.",
    )
    id_ida = _get(dados_pedido, "shipping", "id")

    if id_ida:
        a.executar(
            1, "Envio de ida", "/shipments/{ida}", f"/shipments/{id_ida}",
            "Status atual, tipo logístico e endereços de origem/destino da perna de ida. "
            "Chamado SEM o header x-format-new (com ele, sender/receiver_address somem — views.py).",
            (n_pedido, "shipping.id"), extrair_envio,
            vars_caminho=[f"ida = {id_ida}"],
        )
        a.executar(
            1, "Histórico do envio de ida", "/shipments/{ida}/history", f"/shipments/{id_ida}/history",
            "Linha do tempo de eventos do envio de ida (coleta, trânsito, entrega).",
            (n_pedido, "shipping.id"), extrair_historico,
            vars_caminho=[f"ida = {id_ida}"], headers=HEADER_FORMATO_NOVO,
        )
    else:
        motivo = (f"o pedido (#{n_pedido}) não trouxe dado, então não há shipping.id." if dados_pedido is None
                  else f"o pedido (#{n_pedido}) veio sem shipping.id (sem envio gerenciado pelo ML?).")
        a.pular(1, "Envio de ida", "/shipments/{ida}", "Status atual, tipo logístico e endereços da perna de ida.",
                (n_pedido, "shipping.id"), motivo)
        a.pular(1, "Histórico do envio de ida", "/shipments/{ida}/history", "Linha do tempo de eventos do envio de ida.",
                (n_pedido, "shipping.id"), motivo)

    # ---------------- Etapa 2 - Reclamação ----------------
    busca, n_busca = a.executar(
        2, "Busca de reclamações", "/post-purchase/v1/claims/search", "/post-purchase/v1/claims/search",
        "Descobrir se o pedido tem reclamação e qual o id de cada uma.",
        (None, "entrada (número do pedido)"), extrair_busca_claims,
        params={"order_id": pedido},
    )
    claims = _claims_da_busca(busca) if busca is not None else []
    varias = len(claims) > 1

    nomes_claim = ("Detalhe da claim", "/post-purchase/v1/claims/{claim}",
                   "Tipo, etapa, status, motivo, jogadores e resolução da reclamação.")
    nomes_msg = ("Mensagens da claim", "/post-purchase/v1/claims/{claim}/messages",
                 "Mensagens da mediação (ML, vendedor e comprador). A 1ª com stage = dispute é a melhor aproximação "
                 "da data de abertura da disputa.")
    nomes_ret = ("Devolução", "/post-purchase/v2/claims/{claim}/returns",
                 "Saber se existe devolução física, em que status, como está o dinheiro e quais são os envios de volta.")

    validas = [(i, c) for i, c in claims if c.get("id") is not None]
    if not validas:
        motivo = (f"a busca de reclamações (#{n_busca}) falhou, então não sei qual é a claim." if busca is None
                  else f"a busca (#{n_busca}) respondeu, mas sem nenhuma claim para este pedido.")
        for nome, modelo, objetivo in (nomes_claim, nomes_msg):
            a.pular(2, nome, modelo, objetivo, (n_busca, "data[0].id"), motivo)
        a.pular(3, nomes_ret[0], nomes_ret[1], nomes_ret[2], (n_busca, "data[0].id"), motivo)
        a.pular(3, "Envio de volta", "/shipments/{volta}", "Status e endereços da perna de volta.",
                (n_busca, "data[0].id"), motivo)
        a.pular(3, "Histórico do envio de volta", "/shipments/{volta}/history", "Linha do tempo do envio de volta.",
                (n_busca, "data[0].id"), motivo)
        return

    ids_claim = {}
    for indice, claim in validas:
        cid = claim["id"]
        sufixo = f" ({cid})" if varias else ""
        origem = (n_busca, f"data[{indice}].id")
        _, n_claim = a.executar(
            2, nomes_claim[0] + sufixo, nomes_claim[1], f"/post-purchase/v1/claims/{cid}", nomes_claim[2],
            origem, extrair_claim, vars_caminho=[f"claim = {cid}"],
        )
        ids_claim[cid] = n_claim
        a.executar(
            2, nomes_msg[0] + sufixo, nomes_msg[1], f"/post-purchase/v1/claims/{cid}/messages", nomes_msg[2],
            origem, extrair_mensagens, vars_caminho=[f"claim = {cid}"],
        )

    # ---------------- Etapa 3 - Devolução física ----------------
    for indice, claim in validas:
        cid = claim["id"]
        sufixo = f" ({cid})" if varias else ""
        origem = (n_busca, f"data[{indice}].id")
        retorno, n_retorno = a.executar(
            3, nomes_ret[0] + sufixo, nomes_ret[1], f"/post-purchase/v2/claims/{cid}/returns", nomes_ret[2],
            origem, extrair_devolucao, vars_caminho=[f"claim = {cid}"],
            dica_404=(f"Pelo vault, resolution.reason = coverage_decision ou no_bpp costuma dar 404 aqui "
                      f"(uma exceção confirmada: pedido 2000017788033354). Compare com a resolução da claim #{ids_claim[cid]}."),
        )

        envios = _envios_da_devolucao(retorno) if retorno is not None else []
        if not envios:
            motivo = (f"a devolução (#{n_retorno}) não trouxe dado." if retorno is None
                      else f"a devolução (#{n_retorno}) veio sem envios de volta (shipments vazio ou null).")
            a.pular(3, "Envio de volta" + sufixo, "/shipments/{volta}", "Status e endereços da perna de volta.",
                    (n_retorno, "shipments[0].shipment_id"), motivo)
            a.pular(3, "Histórico do envio de volta" + sufixo, "/shipments/{volta}/history",
                    "Linha do tempo do envio de volta.", (n_retorno, "shipments[0].shipment_id"), motivo)
            continue

        muitos = varias or len(envios) > 1
        for posicao, volta in envios:
            origem_volta = (n_retorno, f"shipments[{posicao}].shipment_id")
            sufixo_volta = f" ({volta})" if muitos and volta else (sufixo if muitos else "")
            if not volta:
                motivo = f"shipments[{posicao}] da devolução (#{n_retorno}) veio sem shipment_id."
                a.pular(3, "Envio de volta" + sufixo_volta, "/shipments/{volta}", "Status e endereços da perna de volta.",
                        origem_volta, motivo)
                a.pular(3, "Histórico do envio de volta" + sufixo_volta, "/shipments/{volta}/history",
                        "Linha do tempo do envio de volta.", origem_volta, motivo)
                continue
            a.executar(
                3, "Envio de volta" + sufixo_volta, "/shipments/{volta}", f"/shipments/{volta}",
                "Status, tipo logístico e endereços de origem/destino da perna de volta.",
                origem_volta, extrair_envio, vars_caminho=[f"volta = {volta}"],
            )
            a.executar(
                3, "Histórico do envio de volta" + sufixo_volta, "/shipments/{volta}/history",
                f"/shipments/{volta}/history",
                "Linha do tempo do envio de volta: de onde saem as datas de postagem, chegada e entrega.",
                origem_volta, extrair_historico, vars_caminho=[f"volta = {volta}"], headers=HEADER_FORMATO_NOVO,
            )


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Analisa UM pedido do Mercado Livre e grava o painel HTML.")
    parser.add_argument("--empresa", required=True, help="MB ou SV")
    parser.add_argument("--pedido", required=True, help="número do pedido (só dígitos)")
    args = parser.parse_args()

    conta = args.empresa.strip().upper()
    if conta not in ("MB", "SV"):
        parser.error("--empresa deve ser MB ou SV")
    pedido = args.pedido.strip()
    if not pedido.isdigit():
        parser.error("--pedido deve ter só dígitos")

    PASTA_LOGS.mkdir(parents=True, exist_ok=True)
    analise = Analise(conta, pedido)
    caminho = analise.gravar("preparando… nenhuma chamada feita ainda")
    print(_ascii(f"Pedido {pedido} - conta {conta}"))
    print(f"Painel (abra no navegador e aperte F5): {caminho.as_uri()}")
    print()

    try:
        percorrer(analise)
    except KeyboardInterrupt:
        analise.gravar("interrompido por você (Ctrl+C)")
        print(_ascii("\nInterrompido (Ctrl+C). O painel mostra o que foi feito ate aqui."))
        return
    except Exception as erro:
        traceback.print_exc()
        analise.gravar(f"INTERROMPIDO por erro no script: {type(erro).__name__}: {erro}")
        raise

    analise.gravar("concluído")
    print()
    print(_ascii("Concluido: " + " | ".join(t for _, t in Analise._contagem([r for _, r in analise.registros])) +
                 f" | {_tempo_legivel(time.perf_counter() - analise.inicio)} no total"))
    print(f"Painel: {caminho}")


if __name__ == "__main__":
    main()