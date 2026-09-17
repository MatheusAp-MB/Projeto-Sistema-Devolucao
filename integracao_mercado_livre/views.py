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
import bleach
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

# Tags que sobrevivem à sanitização do campo "message" das mensagens da claim
# — o mediador do ML manda esse campo em HTML (parágrafo, negrito, link);
# sanitizamos com bleach pra poder renderizar com |safe no template sem abrir
# brecha de XSS.
TAGS_PERMITIDAS_MENSAGEM = ["p", "br", "strong", "b", "em", "i", "a"]
ATRIBUTOS_PERMITIDOS_MENSAGEM = {"a": ["href"]}


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


def _preparar_mensagem_html(texto):
    """Prepara o campo 'message' de uma mensagem da claim pra exibição segura
    no template com |safe: se já vier com HTML (parágrafo, negrito, link —
    como normalmente vêm as mensagens do mediador), sanitiza mantendo só um
    punhado de tags seguras (bleach). Se vier em texto puro (como normalmente
    vêm as suas e as do comprador), cada quebra de linha vira <br> antes de
    sanitizar, senão o navegador ignora as quebras. Todo link vira
    target="_blank" pra não tirar o usuário da tela sem aviso."""
    if not texto:
        return '<p class="text-muted mb-0">(sem texto — mensagem só com anexo, ou campo vazio)</p>'
    if "<" not in texto:
        texto = texto.replace("\n", "<br>")
    limpo = bleach.clean(
        texto,
        tags=TAGS_PERMITIDAS_MENSAGEM,
        attributes=ATRIBUTOS_PERMITIDOS_MENSAGEM,
        strip=True,
    )
    return limpo.replace("<a ", '<a target="_blank" rel="noopener" ')


def _construir_mensagens_mediacao(claim_id, conta, meu_user_id, claim, iniciais_cliente):
    """Monta a lista de mensagens da claim pro Bloco 4, já classificada em
    ML / você / cliente (mesma lógica do varredura_respostas_mediacao.py:
    sender_role == 'mediator' é o ML, sender_role == o seu papel nos players
    é você, o resto é a cliente) e com o texto pronto pra exibir no chat."""
    meu_papel = None
    for player in claim.get("players", []):
        if player.get("user_id") == meu_user_id:
            meu_papel = player.get("role")
            break

    try:
        resposta = chamar_api(
            "GET", f"/post-purchase/v1/claims/{claim_id}/messages",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        return []

    mensagens = resposta.json()
    mensagens.sort(key=lambda m: m.get("date_created") or "")

    resultado = []
    for m in mensagens:
        sender = m.get("sender_role")
        if sender == "mediator":
            papel, lado, rotulo, iniciais = "ml", "esq", "Mercado Livre", "ML"
        elif meu_papel is not None and sender == meu_papel:
            papel, lado, rotulo, iniciais = "voce", "dir", "Você", conta
        else:
            papel, lado, rotulo, iniciais = "cliente", "esq", "Cliente", iniciais_cliente
        resultado.append({
            "papel": papel,
            "lado": lado,
            "rotulo": rotulo,
            "iniciais": iniciais,
            "data": _formatar_data(m.get("date_created")),
            "texto_html": _preparar_mensagem_html(m.get("message")),
        })
    return resultado


# ─── Consultar Pedido — busca por ID do Cliente ou Pack (novo) ──────────
#
# Ideia validada nos scripts de exploração desta investigação
# (consultar_pedidos_por_cliente.py, investigar_pack.py, etc.):
# buyer.id -> lista pedidos do cliente -> classifica cada um; e Número da
# Venda -> tenta como Pedido, cai pra Pack em caso de erro.

_TEXTO_CLASSIFICACAO = {
    'sem_problema': 'Sem problema',
    'com_reclamacao': 'Com reclamação',
    'com_devolucao': 'Com devolução',
}


def _classificar_pedido_leve(numero_pedido, conta):
    """Classifica um pedido em sem_problema / com_reclamacao / com_devolucao
    sem buscar todos os detalhes que view_consultar_pedido busca pra 1
    pedido só — usado pra montar a lista de desambiguação (cliente ou pack
    com mais de 1 pedido), reaproveitando a mesma lógica de
    reclamação->devolução que view_consultar_pedido já usa pra 1 pedido."""
    try:
        resposta_claims = chamar_api(
            "GET", "/post-purchase/v1/claims/search",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
            params={"order_id": numero_pedido},
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        codigo = 'sem_problema'
        return {'codigo': codigo, 'texto': _TEXTO_CLASSIFICACAO[codigo]}

    claims = resposta_claims.json().get("data", [])
    if not claims:
        codigo = 'sem_problema'
        return {'codigo': codigo, 'texto': _TEXTO_CLASSIFICACAO[codigo]}

    claims_em_ordem_de_tentativa = sorted(
        claims, key=lambda c: 0 if c.get("type") in ("return", "fulfillment") else 1
    )
    for candidata in claims_em_ordem_de_tentativa:
        try:
            resposta_devolucao = chamar_api(
                "GET", f"/post-purchase/v2/claims/{candidata['id']}/returns",
                pasta_logs=PASTA_LOGS_ML, conta=conta,
            )
        except (ErroAPI, ErroAutenticacaoAPI):
            continue
        if resposta_devolucao.json():
            codigo = 'com_devolucao'
            return {'codigo': codigo, 'texto': _TEXTO_CLASSIFICACAO[codigo]}

    codigo = 'com_reclamacao'
    return {'codigo': codigo, 'texto': _TEXTO_CLASSIFICACAO[codigo]}


def _listar_pedidos_do_cliente(buyer_id, conta):
    """Busca todos os pedidos de um comprador (buyer.id do Mercado Livre)
    nesta conta e classifica cada um — mesma lógica validada em
    consultar_pedidos_por_cliente.py. Sem paginação ainda: só traz a 1ª
    página de /orders/search (ponto de polimento futuro). Não ordena
    aqui — quem ordena (pela data real, não pelo texto formatado) e
    agrupa por pack é _agrupar_e_ordenar_pedidos."""
    resposta_eu = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS_ML, conta=conta)
    seller_id = resposta_eu.json().get("id")

    resposta_busca = chamar_api(
        "GET", "/orders/search",
        pasta_logs=PASTA_LOGS_ML, conta=conta,
        params={"seller": seller_id, "buyer": buyer_id},
    )
    resultados = resposta_busca.json().get("results", [])

    pedidos = []
    for pedido in resultados:
        item = (pedido.get("order_items") or [{}])[0]
        pedidos.append({
            'numero_pedido': pedido.get('id'),
            'data': _formatar_data(pedido.get('date_created')),
            'data_ordenacao': pedido.get('date_created') or '',
            'titulo_item': (item.get('item') or {}).get('title', '—'),
            'pack_id': pedido.get('pack_id'),
            'classificacao': _classificar_pedido_leve(pedido.get('id'), conta),
        })
    return pedidos


def _resolver_pack(numero, conta):
    """Tenta resolver 'numero' como um Pack ID (carrinho de compra) quando
    ele não bate como pedido individual — ver achados sobre números
    impressos como 'Pedido' que na verdade eram Pack ID. Retorna a lista
    de pedidos daquele pack (já classificados), ou None se também não
    existir como pack. Não ordena aqui — ver _agrupar_e_ordenar_pedidos."""
    try:
        resposta_pack = chamar_api("GET", f"/packs/{numero}", pasta_logs=PASTA_LOGS_ML, conta=conta)
    except ErroAPI as erro:
        if str(erro).startswith("Erro 404 "):
            return None
        raise

    pack = resposta_pack.json()
    ids_dos_pedidos = [o.get('id') for o in pack.get('orders', []) if o.get('id')]

    pedidos = []
    for numero_pedido_do_pack in ids_dos_pedidos:
        resposta_pedido = chamar_api(
            "GET", f"/orders/{numero_pedido_do_pack}",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
        )
        pedido = resposta_pedido.json()
        item = (pedido.get("order_items") or [{}])[0]
        pedidos.append({
            'numero_pedido': pedido.get('id'),
            'data': _formatar_data(pedido.get('date_created')),
            'data_ordenacao': pedido.get('date_created') or '',
            'titulo_item': (item.get('item') or {}).get('title', '—'),
            'pack_id': numero,
            'classificacao': _classificar_pedido_leve(pedido.get('id'), conta),
        })
    return pedidos


def _agrupar_e_ordenar_pedidos(pedidos):
    """Agrupa visualmente os pedidos que compartilham o mesmo pack_id
    (mesma compra em carrinho) — só forma grupo quando 2 ou mais pedidos
    dessa lista têm o mesmo pack_id; pedido sozinho fica solto, mesmo
    tendo pack_id (o parceiro dele não está nessa lista). Ordena pela
    data real (data_ordenacao, formato ISO da API), não pelo texto já
    formatado — ordenar pelo texto "dd/mm/aaaa" quebra cruzando mês/ano.
    Retorna uma lista de blocos: {'pack_id': None ou o id, 'pedidos': [...]}."""
    por_pack = {}
    soltos = []
    for p in pedidos:
        pack_id = p.get('pack_id')
        if pack_id:
            por_pack.setdefault(pack_id, []).append(p)
        else:
            soltos.append(p)

    blocos = []
    for pack_id, itens in por_pack.items():
        if len(itens) > 1:
            blocos.append({'pack_id': pack_id, 'pedidos': itens})
        else:
            soltos.extend(itens)
    blocos += [{'pack_id': None, 'pedidos': [p]} for p in soltos]

    for bloco in blocos:
        bloco['pedidos'].sort(key=lambda p: p.get('data_ordenacao') or '', reverse=True)

    blocos.sort(key=lambda b: max(p.get('data_ordenacao') or '' for p in b['pedidos']), reverse=True)
    return blocos


def view_consultar_pedido(request):
    empresa = obter_empresa_ativa()
    conta = CONTA_POR_EMPRESA.get(empresa)
    numero_pedido = request.GET.get('numero_pedido', '').strip()
    id_cliente = request.GET.get('id_cliente', '').strip()

    contexto = {
        'pagina_ativa': 'consultar_pedido_ml',
        'empresa': empresa,
        'conta': conta,
        'numero_pedido': numero_pedido,
        'id_cliente': id_cliente,
    }

    if not numero_pedido and not id_cliente:
        return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)

    if numero_pedido and id_cliente:
        contexto['erro'] = 'Preencha só um dos campos por vez — ID do Cliente OU Número da Venda, não os dois ao mesmo tempo.'
        return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)

    if conta is None:
        contexto['erro'] = f'Empresa ativa "{empresa}" não mapeada pra nenhuma conta MB/SV.'
        return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)

    pedido = None  # se já buscarmos o pedido lá embaixo (fluxo direto), evita buscar de novo

    try:
        if id_cliente:
            # ----- Busca por ID do Cliente -----
            pedidos_do_cliente = _listar_pedidos_do_cliente(id_cliente, conta)
            if not pedidos_do_cliente:
                contexto['erro'] = 'Nenhum pedido encontrado pra esse ID de cliente.'
                return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)
            if len(pedidos_do_cliente) > 1:
                contexto['lista_pedidos'] = _agrupar_e_ordenar_pedidos(pedidos_do_cliente)
                contexto['veio_de'] = 'cliente'
                return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)
            numero_pedido = pedidos_do_cliente[0]['numero_pedido']
            contexto['numero_pedido'] = numero_pedido
            contexto['aviso_cliente_unico'] = True

        else:
            # ----- Busca por Número da Venda, com fallback pra Pack -----
            try:
                resposta_pedido = chamar_api(
                    "GET", f"/orders/{numero_pedido}",
                    pasta_logs=PASTA_LOGS_ML, conta=conta,
                )
                pedido = resposta_pedido.json()
            except ErroAPI as erro:
                if not str(erro).startswith("Erro 404 "):
                    raise
                pedidos_do_pack = _resolver_pack(numero_pedido, conta)
                if pedidos_do_pack is None:
                    contexto['erro'] = f'Nenhum pedido nem pacote encontrado com o número {numero_pedido}.'
                    return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)
                contexto['aviso_pack'] = {
                    'pack_id': numero_pedido,
                    'total_pedidos': len(pedidos_do_pack),
                }
                if len(pedidos_do_pack) > 1:
                    contexto['lista_pedidos'] = _agrupar_e_ordenar_pedidos(pedidos_do_pack)
                    contexto['veio_de'] = 'pack'
                    return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)
                numero_pedido = pedidos_do_pack[0]['numero_pedido']
                contexto['numero_pedido'] = numero_pedido
                pedido = None  # só temos o resumo — o bloco "Pedido" abaixo busca o detalhe completo

        # ----- A partir daqui, numero_pedido é garantidamente 1 pedido real -----

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
        if pedido is None:
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

        # ----- Conversa da claim (Bloco 4) -----
        try:
            me = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS_ML, conta=conta).json()
            mensagens_mediacao = _construir_mensagens_mediacao(
                claim_id, conta, me.get('id'), claim, (nome_comprador[:1] or "C").upper()
            )
        except (ErroAPI, ErroAutenticacaoAPI):
            mensagens_mediacao = []

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
            'mensagens_mediacao': mensagens_mediacao,
        })

    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        contexto['erro'] = str(erro)

    return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)