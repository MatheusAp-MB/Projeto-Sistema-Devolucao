# integracao_mercado_livre/views.py

# Função Objetivo: views do app integracao_mercado_livre — teste de conexão
# com a API do Mercado Livre e a tela de Consultar Pedido (Hub de Consulta),
# que junta compra, reclamação, devolução física e mediação/resolução num
# só lugar, pra quem cuida do setor de devolução não precisar navegar
# manualmente pelas telas da Central de Vendedores do Mercado Livre.
# Resolve a conta (MB/SV) sozinha a partir da empresa ativa da sessão —
# mesmo padrão já usado em view_teste_conexao_ml, o usuário só digita o
# número do pedido.

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.shortcuts import render

from core.empresa import obter_empresa_ativa, EMPRESA_MAGAZINE, EMPRESA_SAMVALE
from api_mercado_livre.core.estrutura_api.cliente_api import (
    chamar_api, ErroAPI, ErroAutenticacaoAPI,
)
from api_mercado_livre.core.auth.gerenciador_token import FalhaAutenticacao
from integracao_mercado_livre.traducoes_devolucao import (
    traduzir_evento_envio, traduzir_tipo_e_etapa_claim, categorizar_motivo,
    traduzir_resolucao,
)

CONTA_POR_EMPRESA = {
    EMPRESA_MAGAZINE: 'MB',
    EMPRESA_SAMVALE: 'SV',
}

PASTA_LOGS_ML = settings.DADOS_DIR / 'logs' / 'mercado_livre'

FUSO_HORARIO_EXIBICAO = ZoneInfo("America/Sao_Paulo")
HEADER_FORMATO_NOVO = {"x-format-new": "true"}


def view_teste_conexao_ml(request):
    empresa = obter_empresa_ativa()
    conta = CONTA_POR_EMPRESA.get(empresa)

    contexto = {'empresa': empresa, 'conta': conta}

    if conta is None:
        contexto['erro'] = f'Empresa ativa "{empresa}" não mapeada pra nenhuma conta MB/SV.'
        return render(request, 'integracao_mercado_livre/teste_conexao.html', contexto)

    try:
        resposta = chamar_api('GET', '/users/me', pasta_logs=PASTA_LOGS_ML, conta=conta)
        contexto['resultado_json'] = json.dumps(resposta.json(), ensure_ascii=False, indent=2)
    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        contexto['erro'] = str(erro)

    return render(request, 'integracao_mercado_livre/teste_conexao.html', contexto)


def _formatar_data(valor_iso):
    if not valor_iso or not isinstance(valor_iso, str):
        return None
    try:
        instante = datetime.fromisoformat(valor_iso)
    except ValueError:
        return valor_iso
    instante = instante.astimezone(FUSO_HORARIO_EXIBICAO)
    return instante.strftime("%d/%m/%Y %H:%M")


def _primeiro_evento_com_status(eventos, status_procurado):
    for evento in eventos:
        if evento.get("status") == status_procurado:
            return evento.get("date")
    return None


def _ultimo_evento_com_status(eventos, status_procurado):
    encontrado = None
    for evento in eventos:
        if evento.get("status") == status_procurado:
            encontrado = evento.get("date")
    return encontrado


def _buscar_historico_envio(shipment_id, conta):
    resposta = chamar_api(
        "GET", f"/shipments/{shipment_id}/history",
        pasta_logs=PASTA_LOGS_ML, conta=conta,
        headers_extra=HEADER_FORMATO_NOVO,
    )
    return resposta.json()


def _montar_linha_do_tempo(historico):
    eventos_em_ordem = sorted(historico, key=lambda evento: evento.get("date") or "")
    linha_do_tempo = []
    for evento in eventos_em_ordem:
        traducao = traduzir_evento_envio(evento.get("status"), evento.get("substatus"))
        linha_do_tempo.append({
            'data': _formatar_data(evento.get('date')),
            'texto': traducao['texto'],
            'bruto': traducao['bruto'],
            'confirmado': traducao['confirmado'],
        })
    return linha_do_tempo


def _data_abertura_disputa(claim_id, conta):
    try:
        resposta = chamar_api(
            "GET", f"/post-purchase/v1/claims/{claim_id}/messages",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        return None
    mensagens = resposta.json()
    mensagens_dispute = [m for m in mensagens if m.get("stage") == "dispute"]
    if not mensagens_dispute:
        return None
    return min(m.get("date_created") for m in mensagens_dispute if m.get("date_created"))


def view_consultar_pedido(request):
    empresa = obter_empresa_ativa()
    conta = CONTA_POR_EMPRESA.get(empresa)
    numero_pedido = request.GET.get('numero_pedido', '').strip()

    contexto = {
        'pagina_ativa': 'consultar_pedido_ml',
        'empresa': empresa,
        'conta': conta,
        'numero_pedido': numero_pedido,
    }

    if not numero_pedido:
        return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)

    if conta is None:
        contexto['erro'] = f'Empresa ativa "{empresa}" não mapeada pra nenhuma conta MB/SV.'
        return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)

    try:
        # ----- Reclamação -----
        resposta_claims = chamar_api(
            "GET", "/post-purchase/v1/claims/search",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
            params={"order_id": numero_pedido},
        )
        claims = resposta_claims.json().get("data", [])
        if not claims:
            contexto['erro'] = 'Nenhuma reclamação encontrada pra esse pedido.'
            return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)

        claims_em_ordem_de_tentativa = sorted(
            claims, key=lambda c: 0 if c.get("type") in ("return", "fulfillment") else 1
        )

        devolucao = None
        claim = None
        for candidata in claims_em_ordem_de_tentativa:
            try:
                resposta_devolucao = chamar_api(
                    "GET", f"/post-purchase/v2/claims/{candidata['id']}/returns",
                    pasta_logs=PASTA_LOGS_ML, conta=conta,
                )
            except (ErroAPI, ErroAutenticacaoAPI):
                continue
            devolucao = resposta_devolucao.json()
            resposta_claim = chamar_api(
                "GET", f"/post-purchase/v1/claims/{candidata['id']}",
                pasta_logs=PASTA_LOGS_ML, conta=conta,
            )
            claim = resposta_claim.json()
            break

        if devolucao is None:
            contexto['erro'] = (
                'Nenhuma reclamação tem devolução física associada — '
                'pode ter sido resolvido sem devolução física (reembolso direto, troca, etc).'
            )
            return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)

        # ----- Pedido -----
        resposta_pedido = chamar_api(
            "GET", f"/orders/{numero_pedido}",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
        )
        pedido = resposta_pedido.json()

        comprador = pedido.get("buyer") or {}
        nome_comprador = f"{comprador.get('first_name', '')} {comprador.get('last_name', '')}".strip() or "—"
        nickname_comprador = comprador.get("nickname") or "—"

        item = (pedido.get("order_items") or [{}])[0]
        titulo_item = (item.get("item") or {}).get("title", "—")
        sku_item = (item.get("item") or {}).get("seller_sku") or "—"
        quantidade_item = item.get("quantity") or 1

        shipping_id_ida = (pedido.get("shipping") or {}).get("id")
        historico_ida = []
        if shipping_id_ida:
            historico_ida = _buscar_historico_envio(shipping_id_ida, conta)
        historico_ida_ordenado = sorted(historico_ida, key=lambda e: e.get('date') or '')

        # ----- Envio(s) de volta -----
        envios_volta = devolucao.get("shipments", [])
        historicos_volta = []
        data_postagem_cliente = None
        data_chegada_nos = None
        destino_chegada = None
        for envio in envios_volta:
            shipment_id_volta = envio.get("shipment_id")
            if not shipment_id_volta:
                continue
            historico_volta = _buscar_historico_envio(shipment_id_volta, conta)
            historicos_volta.append({
                'shipment_id': shipment_id_volta,
                'linha_tempo': _montar_linha_do_tempo(historico_volta),
            })
            candidato_postagem = _primeiro_evento_com_status(historico_volta, "shipped")
            candidato_chegada = _ultimo_evento_com_status(historico_volta, "delivered")
            if candidato_postagem and (not data_postagem_cliente or candidato_postagem < data_postagem_cliente):
                data_postagem_cliente = candidato_postagem
            if candidato_chegada and (not data_chegada_nos or candidato_chegada > data_chegada_nos):
                data_chegada_nos = candidato_chegada
                destino_chegada = (envio.get("destination") or {}).get("name")

        # ----- Branch mediação -----
        players = claim.get("players", [])
        tem_mediador = any(p.get("role") == "mediator" for p in players)
        eh_mediacao = tem_mediador or claim.get("stage") == "dispute"
        ramo = "Mediação" if eh_mediacao else "Devolução simples (sem mediação)"

        data_abertura_mediacao = None
        if eh_mediacao:
            data_dispute = _data_abertura_disputa(claim.get('id'), conta)
            data_abertura_mediacao = _formatar_data(data_dispute) if data_dispute else None

        claim_id = claim.get('id')

        contexto.update({
            'encontrado': True,
            'esta_encerrado': bool(devolucao.get('date_closed')),
            'nome_comprador': nome_comprador,
            'nickname_comprador': nickname_comprador,
            'data_compra': _formatar_data(pedido.get('date_created')),
            'titulo_item': titulo_item,
            'sku_item': sku_item,
            'quantidade_item': quantidade_item,
            'claim_id': claim_id,
            'url_ver_pedido': f'https://www.mercadolivre.com.br/vendas/{numero_pedido}/detalhe',
            'url_ver_reclamacao': f'https://www.mercadolivre.com.br/vendas/novo/mensagens/{numero_pedido}/reclamacao/{claim_id}',
            'url_ver_mediacao': f'https://www.mercadolivre.com.br/vendas/novo/mensagens/{numero_pedido}/mediacao/{claim_id}',
            'linha_tempo_ida': _montar_linha_do_tempo(historico_ida),
            'data_inicio_ida': _formatar_data(historico_ida_ordenado[0]['date']) if historico_ida_ordenado else None,
            'data_fim_ida': _formatar_data(historico_ida_ordenado[-1]['date']) if historico_ida_ordenado else None,
            'data_abertura_claim': _formatar_data(claim.get('date_created')),
            'tipo_etapa': traduzir_tipo_e_etapa_claim(claim.get("type"), claim.get("stage")),
            'motivo': categorizar_motivo(claim.get("reason_id")),
            'data_virou_devolucao': _formatar_data(devolucao.get('date_created')),
            'shipments_volta': historicos_volta,
            'data_postagem_cliente': _formatar_data(data_postagem_cliente),
            'data_chegada_nos': _formatar_data(data_chegada_nos),
            'destino_chegada': destino_chegada,
            'ramo': ramo,
            'eh_mediacao': eh_mediacao,
            'status_devolucao': traduzir_evento_envio(devolucao.get("status"), None) if devolucao.get("status") else None,
            'resolucao': traduzir_resolucao(claim.get("resolution")),
            'data_abertura_mediacao': data_abertura_mediacao,
            'data_encerramento': _formatar_data(devolucao.get('date_closed')),
            'status_dinheiro': devolucao.get('status_money'),
        })

    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        contexto['erro'] = str(erro)

    return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)