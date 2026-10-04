# integracao_mercado_livre/traducoes_devolucao.py

# Função Objetivo: traduz os códigos brutos de status/substatus de envio,
# tipo/etapa de reclamação, motivo e resolução da API do Mercado Livre pros
# textos em português usados na tela de Consultar Pedido — mesmas tabelas já
# validadas em scripts_exploracao_ML/consultar_linha_tempo_devolucao.py, só
# que devolvendo dict pronto pro template em vez de imprimir no console.
#
# Combinação fora das tabelas abaixo volta com confirmado=False e o código
# bruto no lugar do texto — nunca inventa uma tradução.

TRADUCAO_EVENTO_ENVIO = {
    ("handling", None): "Registrado, aguardando próxima etapa",
    ("ready_to_ship", "ready_to_print"): "Etiqueta de envio liberada",
    ("ready_to_ship", "printed"): "Etiqueta de envio impressa",
    ("ready_to_ship", "on_route_to_pickup"): "Transportadora a caminho pra coleta",
    ("ready_to_ship", "soon_to_pickup"): "Coleta prestes a acontecer",
    ("ready_to_ship", "picking_up"): "Coletando o pacote",
    ("ready_to_ship", "picked_up"): "Pacote coletado fisicamente",
    ("ready_to_ship", "in_hub"): "Chegou no centro de distribuição",
    ("shipped", None): "Despachado pro trajeto principal",
    ("shipped", "first_visit"): "Primeira tentativa de entrega",
    ("delivered", None): "Entregue",
}


def traduzir_evento_envio(status, substatus):
    traducao = TRADUCAO_EVENTO_ENVIO.get((status, substatus))
    bruto = status + (f"/{substatus}" if substatus else "")
    if traducao:
        return {'texto': traducao, 'bruto': bruto, 'confirmado': True}
    return {'texto': None, 'bruto': bruto, 'confirmado': False}


TRADUCAO_TIPO_CLAIM = {
    "mediations": "Mediação",
    "return": "Devolução",
    "cancel_purchase": "Cancelamento da compra (pelo comprador)",
    "cancel_sale": "Cancelamento da venda (pelo vendedor)",
    "change": "Troca",
    "fulfillment": "Fulfillment (armazenagem/logística do Mercado Livre)",
}

TRADUCAO_ETAPA_CLAIM = {
    "claim": "Reclamação aberta",
    "dispute": "Em mediação",
}


def traduzir_tipo_e_etapa_claim(tipo, etapa):
    texto_tipo = TRADUCAO_TIPO_CLAIM.get(tipo)
    texto_etapa = TRADUCAO_ETAPA_CLAIM.get(etapa)
    confirmado = texto_tipo is not None and texto_etapa is not None
    return {
        'texto': f"{texto_tipo or tipo} / {texto_etapa or etapa}",
        'confirmado': confirmado,
    }


def categorizar_motivo(reason_id):
    if not reason_id:
        return {'texto': "—", 'confirmado': True}
    prefixo = reason_id[:3].upper()
    categorias = {
        "PNR": "Pago e não recebido",
        "PDD": "Produto defeituoso",
    }
    categoria = categorias.get(prefixo)
    if categoria:
        return {'texto': categoria, 'confirmado': True}
    return {'texto': reason_id, 'confirmado': False}


TRADUCAO_RESOLUTION_REASON = {
    "item_returned": "Item devolvido fisicamente",
    "warehouse_decision": "Decisão tomada em centro de triagem do ML",
    "item_changed": "Item trocado",
    "coverage_decision": "Coberto pela política de proteção do ML (nem sempre exige devolução física)",
    "no_bpp": "Sem cobertura de proteção ao comprador (nem sempre exige devolução física)",
}

TRADUCAO_CLOSED_BY = {
    "mediator": "Mediador do Mercado Livre",
    "buyer": "Comprador",
    "seller": "Vendedor",
}

TRADUCAO_PAPEL = {
    "complainant": "reclamante",
    "respondent": "respondente",
}


def traduzir_resolucao(resolucao):
    if not resolucao:
        return {'texto': "Ainda não resolvida", 'motivo_curto': "Ainda não resolvida", 'confirmado': True}
    motivo_bruto = resolucao.get("reason")
    motivo_texto = TRADUCAO_RESOLUTION_REASON.get(motivo_bruto)
    closed_by_bruto = resolucao.get("closed_by")
    closed_by_texto = TRADUCAO_CLOSED_BY.get(closed_by_bruto)
    beneficiados = [TRADUCAO_PAPEL.get(papel, papel) for papel in (resolucao.get("benefited") or [])]
    texto_beneficiados = ", ".join(beneficiados) if beneficiados else "—"
    cobertura = "com" if resolucao.get("applied_coverage") else "sem"
    confirmado = motivo_texto is not None and closed_by_texto is not None
    return {
        'texto': (
            f"{motivo_texto or motivo_bruto} — encerrada por {closed_by_texto or closed_by_bruto}, "
            f"beneficiando {texto_beneficiados}, {cobertura} cobertura aplicada."
        ),
        'motivo_curto': motivo_texto or motivo_bruto,
        'confirmado': confirmado,
    }


def descrever_desfecho(resolucao, meu_papel=None):
    """Linha curta do topo da tela: quem a mediação favoreceu e se houve cobertura.

    Só repete o que a API disse em `benefited` e `applied_coverage` — não
    interpreta o efeito financeiro da cobertura. `meu_papel` é o papel da
    nossa conta na claim (complainant/respondent); sem ele, usa o nome do
    lado como a API informa. Sem resolução (ex.: claim cancelada pela
    venda), não há desfecho: devolve None.
    """
    if not resolucao:
        return None
    beneficiados = resolucao.get("benefited") or []
    partes = []
    if beneficiados:
        if meu_papel is None:
            nomes = ["do " + TRADUCAO_PAPEL.get(papel, papel) for papel in beneficiados]
            partes.append("a favor " + " e ".join(nomes))
        else:
            a_nosso_favor = meu_papel in beneficiados
            a_favor_do_cliente = any(papel != meu_papel for papel in beneficiados)
            if a_nosso_favor and a_favor_do_cliente:
                partes.append("a favor dos dois lados")
            elif a_nosso_favor:
                partes.append("a nosso favor")
            else:
                partes.append("a favor do cliente")
    cobertura = resolucao.get("applied_coverage")
    if cobertura is not None:
        partes.append("cobertura aplicada" if cobertura else "sem cobertura aplicada")
    if not partes:
        return None
    texto = " · ".join(partes)
    return texto[:1].upper() + texto[1:]