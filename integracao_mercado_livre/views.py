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
import os
import re
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
    traduzir_evento_envio, traduzir_tipo_e_etapa_claim,
    traduzir_resolucao,
)
from devolucoes.models import Devolucao, Produto

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


def _formatar_data_para_input(valor_iso):
    """Mesma conversão de fuso de _formatar_data, mas no formato que os
    campos <input type="date"> do formulário de Nova Devolução esperam
    (YYYY-MM-DD) — usado só pra montar o link 'Criar devolução' que sai
    dessa tela auto-preenchendo o que der pra confiar (decisão de
    Matheus, 18/09/2026: sem produto, sem reembolsado, sem motivo da
    reclamação — só datas/cliente/pedido, que vêm direto da API)."""
    if not valor_iso or not isinstance(valor_iso, str):
        return ''
    try:
        instante = datetime.fromisoformat(valor_iso)
    except ValueError:
        return ''
    instante = instante.astimezone(FUSO_HORARIO_EXIBICAO)
    return instante.strftime("%Y-%m-%d")


def _dia_local(valor_iso):
    """Mesma conversão de fuso de _formatar_data, mas devolvendo só o DIA como
    objeto date (ou None). É o que a faixa "Datas do caso" do topo da tela usa
    pra mostrar o dia e pra contar quantos dias passaram entre uma data e a
    seguinte (decisão de Matheus, 04/10/2026). Sem valor ou valor ilegível →
    None, e a tela mostra o "sem registro" daquele passo."""
    if not valor_iso or not isinstance(valor_iso, str):
        return None
    try:
        instante = datetime.fromisoformat(valor_iso)
    except ValueError:
        return None
    return instante.astimezone(FUSO_HORARIO_EXIBICAO).date()


def _tempo_entre(dia_de, dia_ate, regra_dos_7_dias=False):
    """Tempo entre 2 datas vizinhas da faixa "Datas do caso", pronto pro
    template (a "etiqueta" que fica em cima da linha que liga os 2 pontos).

    * [EXPLICAÇÃO] → conta DIAS CORRIDOS entre os 2 dias — a mesma conta que
      Devolucao.dias_ate_reclamacao faz com os campos de data do cadastro.
      Com regra_dos_7_dias=True (trecho "Recebido (cliente) → Reclamação
      aberta") aplica a mesma regra de Devolucao.reclamacao_dentro_do_prazo:
      até 7 dias corridos conta como DENTRO — assim essa tela e o Visualizar
      nunca discordam. Só esse trecho ganha cor (verde/vermelho); os outros
      ficam neutros, só informativos. Se uma das datas não existe → None (sem
      etiqueta, a linha fica tracejada). Se a data seguinte for ANTERIOR à
      anterior (dado esquisito vindo do ML), não inventa número negativo:
      mostra um aviso curto."""
    if dia_de is None or dia_ate is None:
        return None
    dias = (dia_ate - dia_de).days
    if dias < 0:
        texto = 'antes da entrega' if regra_dos_7_dias else 'fora de ordem'
        return {
            'texto': texto, 'depois': texto, 'tom': 'neutro', 'extra': None, 'simbolo': None,
            'titulo': 'Essa data é anterior à data do passo anterior — vale conferir no Mercado Livre',
        }
    if dias == 0:
        texto, depois = 'mesmo dia', 'no mesmo dia'
    else:
        texto = f'{dias} dia' if dias == 1 else f'{dias} dias'
        depois = f'{texto} depois'
    tempo = {'texto': texto, 'depois': depois, 'tom': 'neutro', 'extra': None, 'simbolo': None, 'titulo': None}
    if regra_dos_7_dias:
        dentro = dias <= 7
        tempo.update(
            tom='ok' if dentro else 'alerta',
            extra='dentro dos 7' if dentro else 'fora dos 7',
            simbolo='✓' if dentro else '✕',
            titulo=('Reclamou dentro dos 7 dias corridos depois de receber'
                    if dentro else 'Reclamou depois dos 7 dias corridos do recebimento'),
        )
    return tempo


def _montar_datas_do_caso(*, dia_venda, dia_entrega_cliente, dia_reclamacao, dia_chegada_nos,
                          dia_mediacao_aberta, dia_mediacao_encerrada,
                          sem_devolucao_fisica, caso_encerrado, eh_mediacao, devolucao_cadastrada):
    """Monta a faixa "Datas do caso" do topo: a linha do tempo COMPLETA do
    pedido, da venda até o fim da mediação, sempre com os 6 passos — mesmo os
    que ainda não aconteceram (a Ana vê em que fase o pedido está). Pedido de
    Matheus, 04/10/2026: a Consultar Pedido é o ponto de entrada pra ver tudo
    de um pedido, em qualquer fase.

    * [EXPLICAÇÃO] → de onde vem cada data:
      - Venda, Recebido (cliente), Reclamação aberta, Recebido (nós): API do ML
        (são as 4 datas obrigatórias do formulário de Nova Devolução).
      - Mediação aberta: SÓ o que a Ana registrou no cadastro da devolução
        (decisão de 03/10/2026: é o dia em que ELA abriu a mediação pra
        contestar o cliente; a API não sabe essa data). Sem cadastro → a tela
        diz "ainda não cadastrada".
      - Mediação encerrada: a data de fechamento que o ML informa (a mesma que
        o botão "Criar devolução" já leva pro formulário), ou a do cadastro se
        o ML não trouxe. Só aparece se o caso TEVE mediação (eh_mediacao, ou a
        Ana registrou a abertura) — um caso que fechou sem mediação mostra "—".
    Cada passo que ainda não tem data diz o motivo ("sem mediação", "em
    andamento"...) em vez de ficar em branco."""
    teve_mediacao = eh_mediacao or dia_mediacao_aberta is not None
    if not teve_mediacao:
        dia_mediacao_encerrada = None

    if sem_devolucao_fisica:
        sem_chegada = 'sem devolução física'
    elif caso_encerrado:
        sem_chegada = 'sem registro de entrega'
    else:
        sem_chegada = 'ainda não chegou'

    if not eh_mediacao and dia_mediacao_aberta is None:
        sem_abertura = 'sem mediação'
    elif devolucao_cadastrada:
        sem_abertura = 'sem data registrada'
    else:
        sem_abertura = 'ainda não cadastrada'

    if not teve_mediacao:
        sem_fim = '—'
    elif caso_encerrado:
        sem_fim = 'sem data informada'
    else:
        sem_fim = 'em andamento'

    passos = [
        {'rotulo': 'Venda', 'dia': dia_venda, 'sem_registro': 'sem registro'},
        {'rotulo': 'Recebido (cliente)', 'dia': dia_entrega_cliente, 'sem_registro': 'sem registro de entrega'},
        {'rotulo': 'Reclamação aberta', 'dia': dia_reclamacao, 'sem_registro': 'sem registro'},
        {'rotulo': 'Recebido (nós)', 'dia': dia_chegada_nos, 'sem_registro': sem_chegada},
        {'rotulo': 'Mediação aberta', 'dia': dia_mediacao_aberta, 'sem_registro': sem_abertura},
        {'rotulo': 'Mediação encerrada', 'dia': dia_mediacao_encerrada, 'sem_registro': sem_fim},
    ]
    resultado = []
    for posicao, passo in enumerate(passos):
        proximo = passos[posicao + 1] if posicao + 1 < len(passos) else None
        resultado.append({
            'rotulo': passo['rotulo'],
            'data': passo['dia'].strftime('%d/%m/%Y') if passo['dia'] else None,
            'sem_registro': passo['sem_registro'],
            # linha cheia só quando os 2 pontos têm data; senão fica tracejada
            'liga': bool(proximo and passo['dia'] and proximo['dia']),
            # etiqueta de tempo que fica em cima da linha ENTRE este passo e o seguinte
            'tempo': _tempo_entre(passo['dia'], proximo['dia'], regra_dos_7_dias=(posicao == 1)) if proximo else None,
            'tempo_anterior': None,
        })
    # No celular as linhas somem; aí o tempo aparece embaixo da data do passo seguinte ("9 dias depois").
    for posicao in range(1, len(resultado)):
        resultado[posicao]['tempo_anterior'] = resultado[posicao - 1]['tempo']
    return resultado


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


def _buscar_shipment_completo(shipment_id, conta):
    """Recurso completo do shipment (/shipments/{id}) — diferente de
    /shipments/{id}/history, esse traz sender_address/receiver_address.
    O Mercado Livre mascara rua/número/CEP/nome/telefone em endereços
    cadastrais normais (não em agências) — ver a descoberta 'Mascaramento
    de Endereço no Shipment do ML...' no vault. Usado só pra mostrar
    origem/destino na linha do tempo e confirmar se bate com o endereço
    oficial da conta (MB_ADDRESS_ID/SV_ADDRESS_ID no .env).

    IMPORTANTE: ao contrário de _buscar_historico_envio, esse endpoint
    NÃO leva o header x-format-new — investigar_enderecos_shipment.py
    (script já testado empiricamente com pedidos reais) chama
    /shipments/{id} sem headers_extra nenhum. Mandar x-format-new aqui
    muda o formato da resposta e faz sender_address/receiver_address
    sumirem silenciosamente (sem erro, só sem endereço)."""
    resposta = chamar_api(
        "GET", f"/shipments/{shipment_id}",
        pasta_logs=PASTA_LOGS_ML, conta=conta,
    )
    return resposta.json()


def _montar_linha_do_tempo(historico, endereco_origem=None, endereco_destino=None):
    """endereco_origem/endereco_destino (ver _resumir_endereco_para_exibicao)
    só são anexados no evento de coleta física (substatus picked_up) e no
    evento de entrega (status delivered) — são as 2 únicas pontas da rota
    que a API de fato associa a um endereço; o meio do caminho não tem
    essa informação em nenhum endpoint testado."""
    eventos_em_ordem = sorted(historico, key=lambda evento: evento.get("date") or "")
    linha_do_tempo = []
    for evento in eventos_em_ordem:
        traducao = traduzir_evento_envio(evento.get("status"), evento.get("substatus"))
        endereco_do_evento = None
        if evento.get("substatus") == "picked_up":
            endereco_do_evento = endereco_origem
        elif evento.get("status") == "delivered":
            endereco_do_evento = endereco_destino
        linha_do_tempo.append({
            'data': _formatar_data(evento.get('date')),
            'texto': traducao['texto'],
            'bruto': traducao['bruto'],
            'confirmado': traducao['confirmado'],
            'endereco': endereco_do_evento,
        })
    return linha_do_tempo


def _resumir_endereco_para_exibicao(endereco, conta):
    """Resume um sender_address/receiver_address pra exibir na linha do
    tempo: rua/número (mascarados ou não, como a API mandar), bairro/cidade
    (nunca mascarados) e, quando MB_ADDRESS_ID/SV_ADDRESS_ID estiver no
    .env, confirma se bate com o cadastro oficial da conta, é uma agência
    do Mercado Livre, ou é um depósito/centro de distribuição do Full
    (types com 'warehouse' ou 'logistic_center_*' — nesse caso o endereço
    nunca vai ter address_id próprio, porque não é um endereço cadastrado
    da conta, é uma instalação do próprio Mercado Livre)."""
    if not endereco:
        return None

    rua = endereco.get('street_name') or '—'
    numero = endereco.get('street_number') or ''
    mascarado = rua == 'XXXXXXX'
    rua_numero = f'{rua}, nº {numero}' if numero else rua

    bairro = (endereco.get('neighborhood') or {}).get('name') or '—'
    cidade = (endereco.get('city') or {}).get('name') or '—'
    uf = (endereco.get('state') or {}).get('id', '').replace('BR-', '') or '—'
    cidade_bairro = f'{bairro}, {cidade}/{uf}'

    tipos = endereco.get('types') or []
    address_id_oficial = os.getenv(f'{conta}_ADDRESS_ID')

    confirmacao = None
    rotulo_agencia = None
    if 'agency_address' in tipos:
        confirmacao = 'agencia'
        rotulo_agencia = (endereco.get('agency') or {}).get('description')
    elif 'warehouse' in tipos or any(tipo.startswith('logistic_center_') for tipo in tipos):
        confirmacao = 'deposito_full'
    elif address_id_oficial and str(endereco.get('id')) == str(address_id_oficial):
        confirmacao = 'oficial'
    elif address_id_oficial:
        confirmacao = 'nao_bate'

    return {
        'rua_numero': rua_numero,
        'mascarado': mascarado,
        'cidade_bairro': cidade_bairro,
        'confirmacao': confirmacao,
        'rotulo_agencia': rotulo_agencia,
    }


def _rotulo_confirmacao_endereco(resumo_endereco):
    """Rótulo curto pro cabeçalho do bloco (ex: '· destino: ...'). None
    quando não dá pra confirmar nada (endereço ausente, ou ADDRESS_ID da
    conta ainda não configurado no .env)."""
    if not resumo_endereco:
        return None
    confirmacao = resumo_endereco.get('confirmacao')
    if confirmacao == 'oficial':
        return '✅ endereço oficial confirmado'
    if confirmacao == 'agencia':
        rotulo = resumo_endereco.get('rotulo_agencia')
        return f'📍 agência — {rotulo}' if rotulo else '📍 agência do Mercado Livre'
    if confirmacao == 'deposito_full':
        return '📦 Depósito do FULL'
    if confirmacao == 'nao_bate':
        return '⚠️ não é o endereço oficial'
    return None


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


def _url_anexo_mensagem(numero_pedido, claim_id, conta, anexo):
    """Mesma URL de download de anexo usada em devolucoes/varredura_mediacoes.py
    (ver vault 'Anexos de Imagem nas Mensagens de Mediação', 20/09/2026) --
    exige sessão web logada no Mercado Livre (cookie), por isso só funciona
    como link aberto em nova guia, nunca embutido como <img>."""
    filename = anexo.get('filename')
    seller_id = os.getenv(f'{conta}_USER_ID')
    if not filename or not seller_id:
        return None
    return (
        f'https://vendedores.mercadolivre.com.br/api/messages/packs/{numero_pedido}'
        f'/sellers/{seller_id}/messages/attachments/{filename}'
        f'?siteId=MLB&tag=claim&claimId={claim_id}&dispute=false'
    )


def _construir_mensagens_mediacao(claim_id, conta, meu_user_id, claim, iniciais_cliente, numero_pedido):
    """Monta a lista de mensagens da claim pro Bloco 4, já classificada em
    ML / você / cliente (mesma lógica do varredura_respostas_mediacao.py:
    sender_role == 'mediator' é o ML, sender_role == o seu papel nos players
    é você, o resto é a cliente) e com o texto pronto pra exibir no chat.
    Anexos (attachments) incluídos a partir de 20/09/2026, mesmo padrão de
    devolucoes/varredura_mediacoes.py -- ícone clicável que abre o anexo em
    nova guia, autenticado pela sessão do navegador."""
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

        anexos = []
        for anexo in (m.get('attachments') or []):
            url = _url_anexo_mensagem(numero_pedido, claim_id, conta, anexo)
            if url:
                anexos.append({'url': url})

        resultado.append({
            "papel": papel,
            "lado": lado,
            "rotulo": rotulo,
            "iniciais": iniciais,
            "data": _formatar_data(m.get("date_created")),
            "texto_html": _preparar_mensagem_html(m.get("message")),
            "anexos": anexos,
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
    reclamação->devolução que view_consultar_pedido já usa pra 1 pedido.
    Também aproveita, de graça, o campo 'date_closed' que a resposta de
    /returns já traz (mesmo campo usado como 'esta_encerrado' na tela de
    detalhe de 1 pedido) — sem nenhuma chamada nova à API pra isso."""
    try:
        resposta_claims = chamar_api(
            "GET", "/post-purchase/v1/claims/search",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
            params={"order_id": numero_pedido},
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        codigo = 'sem_problema'
        return {'codigo': codigo, 'texto': _TEXTO_CLASSIFICACAO[codigo], 'esta_encerrado': None}

    claims = resposta_claims.json().get("data", [])
    if not claims:
        codigo = 'sem_problema'
        return {'codigo': codigo, 'texto': _TEXTO_CLASSIFICACAO[codigo], 'esta_encerrado': None}

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
        dados_devolucao = resposta_devolucao.json()
        if dados_devolucao:
            codigo = 'com_devolucao'
            return {
                'codigo': codigo,
                'texto': _TEXTO_CLASSIFICACAO[codigo],
                'esta_encerrado': bool(dados_devolucao.get('date_closed')),
            }

    codigo = 'com_reclamacao'
    return {'codigo': codigo, 'texto': _TEXTO_CLASSIFICACAO[codigo], 'esta_encerrado': None}


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


def _formatar_moeda_br(valor):
    """1479.0 -> 'R$ 1.479,00'. Só pra exibir na tela (o valor que vai pro
    formulário de Nova Devolução continua em preco_produto_input, com '.')."""
    if valor is None:
        return None
    try:
        texto_numero = f"{float(valor):,.2f}"
    except (TypeError, ValueError):
        return None
    return "R$ " + texto_numero.replace(",", "X").replace(".", ",").replace("X", ".")


# Só 'active' ganha o link "Ver anúncio"; os outros status viram um aviso
# em texto (o anúncio de um pedido antigo muito provavelmente já foi encerrado).
ROTULO_SITUACAO_ANUNCIO = {
    'closed': 'Anúncio encerrado',
    'paused': 'Anúncio pausado',
    'under_review': 'Anúncio em revisão',
    'inactive': 'Anúncio inativo',
}


# Tipo da devolução, como o ML informa em /returns (campo "subtype"). Só os 3
# valores conhecidos (dicionário dos scripts de exploração); qualquer outro
# valor não aparece na tela — melhor não mostrar do que mostrar código cru.
SUBTIPO_DEVOLUCAO = {
    'return_total': 'Devolução total',
    'return_partial': 'Devolução parcial',
    'low_cost': 'Devolução automática (low cost)',
}


def _formatar_unidades(valor):
    """1.0 -> '1'; 2.5 -> '2,5'. O ML manda essas quantidades como texto ('1.0')."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return str(int(numero)) if numero.is_integer() else str(numero).replace('.', ',')


def _forcar_https(url):
    if url and url.startswith('http://'):
        return 'https://' + url[len('http://'):]
    return url


def _url_foto_grande(url):
    """Troca o tamanho da foto do ML pelo maior: '...-O.jpg' vira '...-F.jpg'.

    * [EXPLICAÇÃO] → decisão de Matheus (04/10/2026): a URL que a API
      devolve termina em -O (tamanho médio); o sufixo -F é a imagem
      grande, melhor pra ver o produto ao expandir. Se a URL não tiver esse
      formato (ex.: miniatura), volta igual. A tela guarda a URL original
      como plano B caso a grande não carregue."""
    if not url:
        return url
    return re.sub(r'-[A-Z]\.((?i:jpg|jpeg|png|webp))$', r'-F.\1', url)


def _buscar_dados_dos_anuncios(order_items, conta):
    """Foto, link e situação dos anúncios (MLB) de um pedido, numa chamada só.

    * [EXPLICAÇÃO] → o /orders traz o MLB (order_items[].item.id) mas NÃO traz
      foto nem link. Os dois vêm do multiget GET /items?ids=MLB1,MLB2 (devolve
      uma lista de {code, body}). Pedimos só os campos que a tela usa
      (attributes=...) pra resposta ficar pequena. Se a chamada falhar, ou o
      anúncio não vier (apagado, sem permissão), devolve {} e a tela mostra
      "sem foto" — a consulta do pedido nunca quebra por causa disso.
    * [NÃO CONFIRMADO] → comportamento pra anúncio já encerrado: esperado vir
      com status 'closed' e as fotos antigas; o 1º teste real vai mostrar.
    """
    mlbs = []
    for item_bruto in order_items:
        mlb = (item_bruto.get('item') or {}).get('id')
        if mlb and mlb not in mlbs:
            mlbs.append(mlb)
    if not mlbs:
        return {}
    try:
        resposta = chamar_api(
            "GET", "/items",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
            params={"ids": ",".join(mlbs), "attributes": "id,status,permalink,thumbnail,pictures"},
        )
        lista = resposta.json()
    except (ErroAPI, ErroAutenticacaoAPI, ValueError):
        return {}
    if not isinstance(lista, list):
        return {}

    dados = {}
    for posicao, entrada in enumerate(lista):
        if not isinstance(entrada, dict) or entrada.get('code') != 200:
            continue
        corpo = entrada.get('body') or {}
        mlb = corpo.get('id') or (mlbs[posicao] if posicao < len(mlbs) else None)
        if not mlb:
            continue
        # A 1ª foto é a capa (a que a tela mostra); as outras só vão pra
        # galeria que abre ao clicar — viram elementos escondidos na tela,
        # então o navegador só baixa cada uma quando a Ana navega até ela.
        urls_originais = []
        for figura in (corpo.get('pictures') or []):
            if not isinstance(figura, dict):
                continue
            url_figura = figura.get('secure_url') or figura.get('url')
            if url_figura:
                urls_originais.append(_forcar_https(url_figura))
        if not urls_originais and corpo.get('thumbnail'):
            urls_originais.append(_forcar_https(corpo['thumbnail']))
        dados[mlb] = {
            'foto_url': _url_foto_grande(urls_originais[0]) if urls_originais else None,
            'foto_url_original': urls_originais[0] if urls_originais else None,
            'fotos_extras': [_url_foto_grande(url) for url in urls_originais[1:]],
            'permalink': corpo.get('permalink'),
            'status': corpo.get('status'),
        }
    return dados


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

                # ----- Bloco do cliente: 1 chamada extra (não por pedido) -----
                # Todo pedido dessa lista já veio filtrado por buyer=id_cliente, ou
                # seja, é garantidamente do mesmo comprador — usamos QUALQUER 1 deles
                # pra buscar o detalhe completo (/orders/{id} traz nome completo do
                # comprador; /orders/search e /users/{id} não trazem, só nickname —
                # ver validação em scripts_exploracao_ML/testar_fluxo_bloco_cliente.py).
                try:
                    pedido_para_identificar_cliente = pedidos_do_cliente[0]['numero_pedido']
                    resposta_qualquer_pedido = chamar_api(
                        "GET", f"/orders/{pedido_para_identificar_cliente}",
                        pasta_logs=PASTA_LOGS_ML, conta=conta,
                    )
                    comprador_lista = resposta_qualquer_pedido.json().get("buyer") or {}
                    nome_comprador_lista = f"{comprador_lista.get('first_name', '')} {comprador_lista.get('last_name', '')}".strip()
                    contexto['nome_comprador'] = nome_comprador_lista or None
                    contexto['nickname_comprador'] = comprador_lista.get('nickname')
                    contexto['id_comprador'] = comprador_lista.get('id') or id_cliente
                except (ErroAPI, ErroAutenticacaoAPI):
                    # Bloco do cliente é só um complemento visual — se essa 1 chamada
                    # falhar, a lista de pedidos continua funcionando normalmente, só
                    # sem o nome do cliente no topo.
                    contexto['nome_comprador'] = None
                    contexto['nickname_comprador'] = None
                    contexto['id_comprador'] = id_cliente

                # ----- Abas por status: mesmo dado que já existe (classificacao.codigo),
                # só reorganizado — dentro de cada aba, os pedidos continuam agrupados
                # por pack e ordenados por data (mesma lógica de sempre). -----
                pedidos_sem_problema = [p for p in pedidos_do_cliente if p['classificacao']['codigo'] == 'sem_problema']
                pedidos_com_reclamacao = [p for p in pedidos_do_cliente if p['classificacao']['codigo'] == 'com_reclamacao']
                pedidos_com_devolucao = [p for p in pedidos_do_cliente if p['classificacao']['codigo'] == 'com_devolucao']

                contexto['contagem_sem_problema'] = len(pedidos_sem_problema)
                contexto['contagem_com_reclamacao'] = len(pedidos_com_reclamacao)
                contexto['contagem_com_devolucao'] = len(pedidos_com_devolucao)
                contexto['lista_sem_problema'] = _agrupar_e_ordenar_pedidos(pedidos_sem_problema)
                contexto['lista_com_reclamacao'] = _agrupar_e_ordenar_pedidos(pedidos_com_reclamacao)
                contexto['lista_com_devolucao'] = _agrupar_e_ordenar_pedidos(pedidos_com_devolucao)

                if contexto['contagem_com_devolucao']:
                    contexto['aba_padrao_status'] = 'devolucao'
                elif contexto['contagem_com_reclamacao']:
                    contexto['aba_padrao_status'] = 'reclamacao'
                else:
                    contexto['aba_padrao_status'] = 'sem-problema'

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
        erros_returns = []  # 1 texto por claim cujo /returns falhou — alimenta o aviso lá embaixo
        for candidata in claims_em_ordem_de_tentativa:
            try:
                resposta_devolucao = chamar_api(
                    "GET", f"/post-purchase/v2/claims/{candidata['id']}/returns",
                    pasta_logs=PASTA_LOGS_ML, conta=conta,
                )
            except (ErroAPI, ErroAutenticacaoAPI) as erro:
                erros_returns.append(str(erro))
                continue
            devolucao = resposta_devolucao.json()
            resposta_claim = chamar_api(
                "GET", f"/post-purchase/v1/claims/{candidata['id']}",
                pasta_logs=PASTA_LOGS_ML, conta=conta,
            )
            claim = resposta_claim.json()
            break

        # * [EXPLICAÇÃO] → antes (até 03/10/2026) a tela parava aqui com um erro e
        #   não mostrava NADA quando nenhuma claim tinha /returns. Achado real: 7
        #   devoluções SV do banco (pedido cancelado, ida entregue, 1 claim
        #   mediations/dispute/closed, /returns 404) caíam nisso. Agora cai na 1ª
        #   claim da fila: mostra claim + pedido + um aviso claro. "devolucao"
        #   vira {} só pro resto da função continuar funcionando com .get().
        sem_devolucao_fisica = devolucao is None
        if sem_devolucao_fisica:
            devolucao = {}
            resposta_claim = chamar_api(
                "GET", f"/post-purchase/v1/claims/{claims_em_ordem_de_tentativa[0]['id']}",
                pasta_logs=PASTA_LOGS_ML, conta=conta,
            )
            claim = resposta_claim.json()

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
        # * [EXPLICAÇÃO] → unit_price é irmão de "item" dentro de
        #   order_items, não fica aninhado dentro de item["item"] (igual
        #   title/seller_sku) — confirmado na doc oficial do ML e testado
        #   empiricamente com pedido real (2000018056884044: unit_price
        #   366.0, gross_price 495.0 — já é o preço COM desconto
        #   aplicado, que é o que Matheus confirmou usar em 19/09/2026).
        preco_unitario_item = item.get("unit_price")

        # ----- Todos os produtos do pedido (antes só o 1º aparecia) -----
        # * [EXPLICAÇÃO] → decisão de Matheus (04/10/2026): o topo da tela vira
        #   Produto / Cliente / Pedido. Cada produto mostra foto, MLB do anúncio
        #   exato em que o cliente comprou, SKU, quantidade e preço unitário.
        #   O formulário de Nova Devolução só aceita 1 produto: quando o pedido
        #   tem mais de 1, o link "Criar devolução" NÃO pré-preenche SKU nem
        #   preço (melhor vazio do que o produto errado) — a Ana escolhe lá.
        itens_brutos = pedido.get("order_items") or []

        # * [EXPLICAÇÃO] → a Ana precisa saber, ao olhar o pedido, se ele já foi
        #   cadastrado no sistema (aí o botão vira "Abrir devolução"). Mesma
        #   regra que nova_devolucao já usa: 1 devolução por numero_pedido.
        devolucao_no_sistema = Devolucao.objects.select_related('produto__marca').filter(
            numero_pedido=str(numero_pedido),
        ).first()
        devolucao_no_sistema_id = devolucao_no_sistema.id if devolucao_no_sistema else None

        # * [EXPLICAÇÃO] → decisão de Matheus (04/10/2026): a 1ª foto do anúncio
        #   às vezes é uma arte estilizada, não o produto em si; a foto que a
        #   Ana cadastra do produto também ajuda a identificar. Como achamos o
        #   Produto cadastrado de cada item: (1) pedido de 1 produto que já
        #   tem devolução → o produto escolhido nela (vínculo mais firme);
        #   (2) senão, o Produto cujo SKU é igual ao seller_sku do anúncio.
        #   Se não achar, a tela só não mostra a foto do cadastro interno.
        skus_do_pedido = {
            (item_bruto.get("item") or {}).get("seller_sku")
            for item_bruto in itens_brutos
        } - {None, ""}
        produtos_por_sku = {}
        if skus_do_pedido:
            for produto_cadastrado in Produto.objects.select_related('marca').filter(sku__in=skus_do_pedido):
                produtos_por_sku[produto_cadastrado.sku.lower()] = produto_cadastrado

        # * [EXPLICAÇÃO] → decisão de Matheus (04/10/2026): mostrar quantas
        #   unidades estão VOLTANDO (≠ quantas o cliente comprou). Vem da
        #   devolução física do ML (/returns): orders[].item_id aponta o MLB do
        #   item e return_quantity / total_quantity dizem "voltam X de Y". Sem
        #   devolução física no ML (sem_devolucao_fisica), não há dado — a tela
        #   simplesmente não mostra o campo, sem afirmar nada. Num pedido de 2
        #   produtos, só o item que aparece na lista mostra o campo.
        #   [NÃO CONFIRMADO] → só vi devolução TOTAL em dado real; parcial segue
        #   a doc (return_quantity < total_quantity), validar no 1º caso real.
        unidades_por_item = {}
        for registro in (devolucao.get("orders") or []):
            if not isinstance(registro, dict):
                continue
            try:
                voltando = float(registro.get("return_quantity"))
                total_do_item = float(registro.get("total_quantity"))
            except (TypeError, ValueError):
                continue
            acumulado = unidades_por_item.setdefault(registro.get("item_id"), [0.0, 0.0])
            acumulado[0] += voltando
            acumulado[1] += total_do_item
        tipo_devolucao_texto = SUBTIPO_DEVOLUCAO.get(devolucao.get("subtype"))

        dados_anuncios = _buscar_dados_dos_anuncios(itens_brutos, conta)
        itens_pedido = []
        for item_bruto in itens_brutos:
            dados_do_item = item_bruto.get("item") or {}
            mlb_do_item = dados_do_item.get("id")
            anuncio = dados_anuncios.get(mlb_do_item, {})
            situacao_anuncio = anuncio.get("status")

            sku_do_item = dados_do_item.get("seller_sku")
            if devolucao_no_sistema is not None and len(itens_brutos) == 1:
                produto_do_item = devolucao_no_sistema.produto
            elif sku_do_item:
                produto_do_item = produtos_por_sku.get(sku_do_item.lower())
            else:
                produto_do_item = None
            foto_cadastro_url = produto_do_item.foto.url if (produto_do_item is not None and produto_do_item.foto) else None

            unidades = unidades_por_item.get(mlb_do_item)
            texto_unidades_voltando = None
            if unidades:
                sufixo_unidade = '' if unidades[1] == 1 else 's'
                texto_unidades_voltando = (
                    f"{_formatar_unidades(unidades[0])} de {_formatar_unidades(unidades[1])} unidade{sufixo_unidade}"
                )

            itens_pedido.append({
                'titulo': dados_do_item.get("title") or "—",
                'sku': dados_do_item.get("seller_sku") or "—",
                'mlb': mlb_do_item or "—",
                'quantidade': item_bruto.get("quantity") or 1,
                'preco_unitario': _formatar_moeda_br(item_bruto.get("unit_price")),
                'foto_url': anuncio.get("foto_url"),
                'foto_url_original': anuncio.get("foto_url_original"),
                'fotos_extras': anuncio.get("fotos_extras") or [],
                'link_anuncio': anuncio.get("permalink") if situacao_anuncio == 'active' else None,
                'rotulo_situacao_anuncio': ROTULO_SITUACAO_ANUNCIO.get(situacao_anuncio),
                'produto_cadastrado': produto_do_item is not None,
                'produto_cadastrado_nome': produto_do_item.nome if produto_do_item is not None else None,
                'foto_cadastro_url': foto_cadastro_url,
                'produto_marca': produto_do_item.marca.nome if produto_do_item is not None else None,
                'produto_codigo_barras': produto_do_item.codigo_barras if produto_do_item is not None else None,
                'texto_unidades_voltando': texto_unidades_voltando,
                'tipo_devolucao': tipo_devolucao_texto if texto_unidades_voltando else None,
            })

        shipping_id_ida = (pedido.get("shipping") or {}).get("id")
        historico_ida = []
        endereco_origem_ida = None
        endereco_destino_ida = None
        logistic_type_ida = None
        metodo_envio_ida = None
        if shipping_id_ida:
            historico_ida = _buscar_historico_envio(shipping_id_ida, conta)
            try:
                shipment_ida_completo = _buscar_shipment_completo(shipping_id_ida, conta)
            except (ErroAPI, ErroAutenticacaoAPI):
                shipment_ida_completo = None
            if shipment_ida_completo:
                # * [EXPLICAÇÃO] → o tipo logístico do envio mora na RAIZ do
                #   /shipments/{id} (chamado SEM x-format-new; nesse formato o
                #   campo aninhado logistic.type vem ausente). Confirmado no
                #   pedido real 2000018229470186: raiz = 'xd_drop_off'.
                logistic_type_ida = shipment_ida_completo.get('logistic_type')
                # Nome da modalidade como o ML mostra (ex.: "MEL Voluminoso") — já
                # vem em texto legível, não é código.
                metodo_envio_ida = shipment_ida_completo.get('tracking_method')
                endereco_origem_ida = _resumir_endereco_para_exibicao(
                    shipment_ida_completo.get('sender_address'), conta,
                )
                endereco_destino_ida = _resumir_endereco_para_exibicao(
                    shipment_ida_completo.get('receiver_address'), conta,
                )
        # * [EXPLICAÇÃO] → decisão de Matheus (03/10/2026): a divisão FULL vs
        #   não-FULL é a mesma do Sistema Interno V2 — 'fulfillment' é o único
        #   tipo que vira FULL; qualquer outro vira 'comum'. A fonte é o ENVIO
        #   de ida: o pedido do /orders não traz logistic_type (por isso a tela
        #   antes sempre caía em 'comum'). Se o tipo não veio (envio não
        #   carregou ou campo ausente), fica '' e o formulário mostra
        #   "Selecione..." — melhor do que chutar 'comum'. Os valores
        #   ('comum'/'full') têm que continuar batendo com
        #   Devolucao.TIPO_VENDA_CHOICES.
        if not logistic_type_ida:
            tipo_venda_sugerido = ''
        elif logistic_type_ida == 'fulfillment':
            tipo_venda_sugerido = 'full'
        else:
            tipo_venda_sugerido = 'comum'
        historico_ida_ordenado = sorted(historico_ida, key=lambda e: e.get('date') or '')
        data_entrega_cliente = _ultimo_evento_com_status(historico_ida, "delivered") if historico_ida else None

        # ----- Envio(s) de volta -----
        # * [EXPLICAÇÃO] → .get("shipments", []) só usa o [] quando a chave NÃO existe;
        #   se a API mandar "shipments": null (achado real em 03/10/2026, pedido
        #   2000018090218022), o valor vem None e o for abaixo derrubava a tela
        #   inteira com TypeError. "or []" trata os dois casos.
        envios_volta = devolucao.get("shipments") or []
        historicos_volta = []
        data_postagem_cliente = None
        data_chegada_nos = None
        confirmacao_chegada_final = None
        for envio in envios_volta:
            shipment_id_volta = envio.get("shipment_id")
            if not shipment_id_volta:
                continue
            historico_volta = _buscar_historico_envio(shipment_id_volta, conta)

            try:
                shipment_volta_completo = _buscar_shipment_completo(shipment_id_volta, conta)
            except (ErroAPI, ErroAutenticacaoAPI):
                shipment_volta_completo = None

            endereco_origem_volta = endereco_destino_volta = None
            if shipment_volta_completo:
                endereco_origem_volta = _resumir_endereco_para_exibicao(
                    shipment_volta_completo.get('sender_address'), conta,
                )
                endereco_destino_volta = _resumir_endereco_para_exibicao(
                    shipment_volta_completo.get('receiver_address'), conta,
                )

            historicos_volta.append({
                'shipment_id': shipment_id_volta,
                'linha_tempo': _montar_linha_do_tempo(historico_volta, endereco_origem_volta, endereco_destino_volta),
            })
            candidato_postagem = _primeiro_evento_com_status(historico_volta, "shipped")
            candidato_chegada = _ultimo_evento_com_status(historico_volta, "delivered")
            if candidato_postagem and (not data_postagem_cliente or candidato_postagem < data_postagem_cliente):
                data_postagem_cliente = candidato_postagem
            if candidato_chegada and (not data_chegada_nos or candidato_chegada > data_chegada_nos):
                data_chegada_nos = candidato_chegada
                confirmacao_chegada_final = endereco_destino_volta

        # ----- Branch mediação -----
        players = claim.get("players", [])
        tem_mediador = any(p.get("role") == "mediator" for p in players)
        eh_mediacao = tem_mediador or claim.get("stage") == "dispute"
        ramo = "Mediação" if eh_mediacao else "Devolução simples (sem mediação)"

        # * [EXPLICAÇÃO] → decisão de Matheus (03/10/2026): "abertura da
        #   mediação" é SEMPRE o dia em que a Ana recebeu a devolução, viu o
        #   defeito e abriu a mediação no ML pra contestar o cliente — e a
        #   devolução costuma ser cadastrada ANTES disso. A API não sabe essa
        #   data (a 1ª mensagem de disputa do ML é outra coisa), então ela é
        #   sempre manual: a tela não mostra e o link "Criar devolução" não leva.

        claim_id = claim.get('id')

        # ----- Conversa da claim (Bloco 4) -----
        try:
            me = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS_ML, conta=conta).json()
            mensagens_mediacao = _construir_mensagens_mediacao(
                claim_id, conta, me.get('id'), claim, (nome_comprador[:1] or "C").upper(), numero_pedido,
            )
        except (ErroAPI, ErroAutenticacaoAPI):
            mensagens_mediacao = []

        # ----- Encerramento: vem da devolução física; sem ela, vem da própria claim -----
        resolucao = traduzir_resolucao(claim.get("resolution"))
        if sem_devolucao_fisica:
            esta_encerrado = claim.get('status') == 'closed'
            # * [NÃO CONFIRMADO] → resolution.date_created é o campo que eu espero pra
            #   data do encerramento da claim; ainda falta conferir na doc oficial do ML.
            #   Se vier ausente, a tela diz "Encerrada (data não informada pela API)".
            data_encerramento = _formatar_data((claim.get('resolution') or {}).get('date_created'))
            if esta_encerrado and not claim.get('resolution'):
                resolucao = {
                    'texto': "Encerrada — a API não informou o detalhe da resolução",
                    'motivo_curto': "sem detalhe da resolução",
                    'confirmado': True,
                }
        else:
            esta_encerrado = bool(devolucao.get('date_closed'))
            data_encerramento = _formatar_data(devolucao.get('date_closed'))

        # * [EXPLICAÇÃO] → só "404 em todas" prova que o ML não registra devolução
        #   física. Qualquer outro erro no /returns (500, 400, 401...) é falha de
        #   consulta — nesse caso o aviso fala em "não foi possível consultar",
        #   não em "não existe".
        aviso_sem_devolucao = None
        if sem_devolucao_fisica:
            todos_404 = all(e.startswith("Erro 404 ") for e in erros_returns)
            aviso_sem_devolucao = {
                'confirmado': todos_404,
                'detalhe_erro': None if todos_404 else erros_returns[-1],
                'pedido_cancelado': pedido.get('status') == 'cancelled',
                'total_claims': len(claims_em_ordem_de_tentativa),
            }

        contexto.update({
            'encontrado': True,
            'sem_devolucao_fisica': sem_devolucao_fisica,
            'aviso_sem_devolucao': aviso_sem_devolucao,
            'esta_encerrado': esta_encerrado,
            'nome_comprador': nome_comprador,
            'nickname_comprador': nickname_comprador,
            'data_compra': _formatar_data(pedido.get('date_created')),
            # * [EXPLICAÇÃO] → faixa "Datas do caso" do topo: linha do tempo completa,
            #   da venda até o fim da mediação, com o tempo entre as datas (decisão
            #   de Matheus, 04/10/2026). Toda a regra está em _montar_datas_do_caso.
            'datas_do_caso': _montar_datas_do_caso(
                dia_venda=_dia_local(pedido.get('date_created')),
                dia_entrega_cliente=_dia_local(data_entrega_cliente),
                dia_reclamacao=_dia_local(claim.get('date_created')),
                dia_chegada_nos=_dia_local(data_chegada_nos),
                dia_mediacao_aberta=devolucao_no_sistema.data_abertura_mediacao if devolucao_no_sistema is not None else None,
                dia_mediacao_encerrada=(
                    _dia_local((claim.get('resolution') or {}).get('date_created') if sem_devolucao_fisica else devolucao.get('date_closed'))
                    or (devolucao_no_sistema.data_finalizacao_mediacao if devolucao_no_sistema is not None else None)
                ),
                sem_devolucao_fisica=sem_devolucao_fisica,
                caso_encerrado=esta_encerrado,
                eh_mediacao=eh_mediacao,
                devolucao_cadastrada=devolucao_no_sistema is not None,
            ),
            # Pro grupo "Devolução / reclamação" saber se mostra "Unidades voltando"
            # (só aparece quando a devolução física do ML trouxe essa informação).
            'ha_unidades_voltando': any(i.get('texto_unidades_voltando') for i in itens_pedido),
            'tipo_devolucao_texto': tipo_devolucao_texto,
            'titulo_item': titulo_item,
            'sku_item': sku_item,
            'quantidade_item': quantidade_item,
            'itens_pedido': itens_pedido,
            # str() de propósito: o Django não pode formatar o ID do cliente
            # com separador de milhar (1.003.452.048 não bate com a etiqueta).
            'id_comprador': str(comprador.get('id') or ''),
            'devolucao_no_sistema_id': devolucao_no_sistema_id,
            'claim_id': claim_id,
            'url_ver_pedido': f'https://www.mercadolivre.com.br/vendas/{numero_pedido}/detalhe',
            'url_ver_reclamacao': f'https://www.mercadolivre.com.br/vendas/novo/mensagens/{numero_pedido}/reclamacao/{claim_id}',
            'url_ver_mediacao': f'https://www.mercadolivre.com.br/vendas/novo/mensagens/{numero_pedido}/mediacao/{claim_id}',
            'linha_tempo_ida': _montar_linha_do_tempo(historico_ida, endereco_origem_ida, endereco_destino_ida),
            'data_inicio_ida': _formatar_data(historico_ida_ordenado[0]['date']) if historico_ida_ordenado else None,
            'data_fim_ida': _formatar_data(historico_ida_ordenado[-1]['date']) if historico_ida_ordenado else None,
            'data_abertura_claim': _formatar_data(claim.get('date_created')),
            'tipo_etapa': traduzir_tipo_e_etapa_claim(claim.get("type"), claim.get("stage")),
            # * [EXPLICAÇÃO] → sem 'motivo' (decisão de Matheus, 03/10/2026): o
            #   motivo que importa é o que o cliente escreveu, registrado à mão
            #   pela Ana — não o código padronizado do ML traduzido.
            'data_virou_devolucao': _formatar_data(devolucao.get('date_created')),
            'shipments_volta': historicos_volta,
            'data_postagem_cliente': _formatar_data(data_postagem_cliente),
            'data_chegada_nos': _formatar_data(data_chegada_nos),
            'destino_chegada': _rotulo_confirmacao_endereco(confirmacao_chegada_final),
            'confirmacao_chegada': confirmacao_chegada_final,
            'ramo': ramo,
            'eh_mediacao': eh_mediacao,
            'status_devolucao': traduzir_evento_envio(devolucao.get("status"), None) if devolucao.get("status") else None,
            'resolucao': resolucao,
            'data_encerramento': data_encerramento,
            'status_dinheiro': devolucao.get('status_money'),
            'mensagens_mediacao': mensagens_mediacao,
            # ===== Só pro botão "Criar devolução" (ponte Consultar Pedido →
            #   Nova Devolução, decisão do vault 17/09 23:24) — datas no
            #   formato de <input type="date">, sem reembolsado/motivo/
            #   produto: decisão de Matheus (18/09/2026) de deixar de fora
            #   o que não dá pra confiar 100% vindo da API. =====
            'nome_comprador_input': nome_comprador if nome_comprador != '—' else '',
            'data_venda_input': _formatar_data_para_input(pedido.get('date_created')),
            'data_recebimento_cliente_input': _formatar_data_para_input(data_entrega_cliente),
            'data_reclamacao_cliente_input': _formatar_data_para_input(claim.get('date_created')),
            'data_recebimento_por_nos_input': _formatar_data_para_input(data_chegada_nos),
            'data_finalizacao_mediacao_input': _formatar_data_para_input(devolucao.get('date_closed')),
            'tipo_venda_sugerido': tipo_venda_sugerido,
            'metodo_envio_ida': metodo_envio_ida,
            # SKU do vendedor no anúncio do ML — não é código de barras,
            # mas alimenta a mesma busca de produto que já sabe achar por
            # código de barras exato OU por nome/SKU/cód. fabricante/marca
            # (ver produto_busca em nova_devolucao/script_nova_devolucao.js).
            'sku_item_input': '' if (len(itens_pedido) > 1 or sku_item == '—') else sku_item,
            # Preço do produto (pedido de Ana, 19/09/2026) — formatado já
            # com '.' (nunca deixa o Django localizar sozinho pro
            # template), pro <input type=number> de nova_devolucao.html
            # aceitar o value sem estranhar (ver nota em
            # devolucoes/views.py::_valores_da_devolucao).
            'preco_produto_input': '' if (len(itens_pedido) > 1 or preco_unitario_item is None) else f'{preco_unitario_item:.2f}',
        })

    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        contexto['erro'] = str(erro)

    return render(request, 'integracao_mercado_livre/consultar_pedido.html', contexto)