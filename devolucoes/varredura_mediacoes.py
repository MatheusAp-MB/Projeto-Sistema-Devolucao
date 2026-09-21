# devolucoes/varredura_mediacoes.py

# Função Objetivo: lógica de varredura de reclamações/mediações do
# Mercado Livre em segundo plano — busca reclamações abertas na API,
# verifica devolução física e mensagens de cada uma, grava tudo na cache
# ClaimMercadoLivre e atualiza StatusVarreduraMediacoes item a item (não
# só no final), pros 2 botões da tela "Mediações ML" (varredura completa
# e atualização dos itens em acompanhamento). Lógica adaptada da já
# validada em scripts_exploracao_ML/buscar_mediacoes_abertas_recentes.py
# e cronometrada em cronometrar_refresh_individual.py (ambos
# 20/09/2026) — porta as funções de busca pra cá porque
# scripts_exploracao_ML/ é pasta de exploração, não código de produção.

import bleach
import os
import re

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI
from core.empresa import definir_empresa_ativa
from integracao_mercado_livre.views import CONTA_POR_EMPRESA, PASTA_LOGS_ML

from .models import ClaimMercadoLivre, Devolucao, MediacaoAvulsa, StatusVarreduraMediacoes

FUSO_HORARIO_EXIBICAO_MSG = ZoneInfo("America/Sao_Paulo")
TAGS_PERMITIDAS_MENSAGEM = ["p", "br", "strong", "b", "em", "i", "a"]
ATRIBUTOS_PERMITIDOS_MENSAGEM = {"a": ["href"]}

MESES_ATRAS = 6
LIMITE_POR_PAGINA = 100
MAX_PAGINAS = 10
FUSO_HORARIO_EXIBICAO = ZoneInfo("America/Sao_Paulo")


def _formatar_data_para_filtro(instante):
    texto = instante.isoformat(timespec="milliseconds")
    return texto[:-6] + texto[-6:].replace(":", "")


def _buscar_user_id(conta):
    resposta = chamar_api("GET", "/users/me", pasta_logs=PASTA_LOGS_ML, conta=conta)
    return resposta.json()["id"]


def _buscar_claims_abertas(conta, user_id, papel, inicio_formatado, fim_formatado):
    claims = []
    offset = 0
    for _ in range(MAX_PAGINAS):
        resposta = chamar_api(
            "GET", "/post-purchase/v1/claims/search",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
            params={
                "players.user_id": user_id,
                "players.role": papel,
                "status": "opened",
                "range": f"date_created:after:{inicio_formatado},before:{fim_formatado}",
                "sort": "date_created:desc",
                "limit": LIMITE_POR_PAGINA,
                "offset": offset,
            },
        )
        pagina = resposta.json()
        dados = pagina.get("data", [])
        claims.extend(dados)
        total = (pagina.get("paging") or {}).get("total", 0)
        offset += LIMITE_POR_PAGINA
        if offset >= total or not dados:
            break
    return claims


def _tem_devolucao_fisica(conta, claim_id):
    """True/False = confirmado via /returns. None = não deu pra confirmar
    (erro que não foi um 404 limpo) — mesma semântica de
    buscar_mediacoes_abertas_recentes.py::tem_devolucao_fisica()."""
    try:
        chamar_api("GET", f"/post-purchase/v2/claims/{claim_id}/returns", pasta_logs=PASTA_LOGS_ML, conta=conta)
        return True
    except ErroAPI as erro:
        if str(erro).startswith("Erro 404 "):
            return False
        return None
    except ErroAutenticacaoAPI:
        return None


def _buscar_mensagens_da_reclamacao(conta, claim_id):
    try:
        resposta = chamar_api("GET", f"/post-purchase/v1/claims/{claim_id}/messages", pasta_logs=PASTA_LOGS_ML, conta=conta)
        return resposta.json()
    except (ErroAPI, ErroAutenticacaoAPI):
        return None


def buscar_nome_cliente_e_produto(conta, numero_pedido):
    """Nome do comprador + título do item — mesmo endpoint e mesma
    extração já validados em produção
    (integracao_mercado_livre/views.py::view_consultar_pedido: GET
    /orders/{id} -> buyer.first_name/last_name, order_items[0].item.title).
    Best-effort: em qualquer falha devolve ('', '') — o pedido/claim_id já
    são suficientes pra criar a MediacaoAvulsa, o nome é só um complemento
    visual (mesmo espírito do bloco do cliente em view_consultar_pedido)."""
    try:
        resposta = chamar_api("GET", f"/orders/{numero_pedido}", pasta_logs=PASTA_LOGS_ML, conta=conta)
    except (ErroAPI, ErroAutenticacaoAPI):
        return '', ''
    pedido = resposta.json()
    comprador = pedido.get("buyer") or {}
    nome_cliente = f"{comprador.get('first_name', '')} {comprador.get('last_name', '')}".strip()
    item = (pedido.get("order_items") or [{}])[0]
    nome_produto = (item.get("item") or {}).get("title") or ''
    return nome_cliente, nome_produto


def resolver_claim_por_numero_pedido(conta, numero_pedido):
    """Busca avulsa e única -- roda só quando Ana abre o detalhe de uma
    mediação (Devolucao ou MediacaoAvulsa) que ainda não tem claim_id.
    Isso acontece com pedido cuja reclamação já estava encerrada no ML
    antes dessa feature existir (ou antes de qualquer varredura ter
    rodado) -- a varredura completa só busca status=opened (decisão de
    Matheus, 20/09/2026: buscar todo status de uma vez trouxe volume
    demais de reclamação já resolvida sem necessidade de acompanhamento,
    revertido), então nunca teria como achar esse pedido sozinha.

    Busca por order_id -- mesmo parâmetro já validado em produção na
    tela "Consultar Pedido" (integracao_mercado_livre/views.py) -- que
    NÃO exige status, então acha a reclamação esteja ela aberta ou
    encerrada. Se tiver mais de uma reclamação pro mesmo pedido, prefere
    a que estiver em stage=dispute (é o campo que define "é mediação de
    verdade", mesmo critério usado em categoria_slug).

    Roda 1x só: grava na cache ClaimMercadoLivre e devolve — quem chama
    é responsável por salvar esse claim_id na Devolucao/MediacaoAvulsa.
    Depois disso, o claim_id fica permanente lá, e essa busca nunca mais
    roda pra esse pedido. Best-effort: qualquer falha (API fora do ar,
    pedido sem reclamação nenhuma) devolve None sem quebrar a tela --
    ela simplesmente continua mostrando "ainda não vinculada"."""
    try:
        resposta = chamar_api(
            "GET", "/post-purchase/v1/claims/search",
            pasta_logs=PASTA_LOGS_ML, conta=conta,
            params={"order_id": numero_pedido},
        )
        claims = resposta.json().get("data", [])
    except (ErroAPI, ErroAutenticacaoAPI):
        return None
    if not claims:
        return None

    claim = next((c for c in claims if c.get("stage") == "dispute"), claims[0])
    claim_id = str(claim.get("id"))

    try:
        meu_user_id = _buscar_user_id(conta)
    except (ErroAPI, ErroAutenticacaoAPI):
        meu_user_id = None
    meu_papel = None
    for player in claim.get("players", []):
        if player.get("user_id") == meu_user_id:
            meu_papel = player.get("role")
            break

    tem_devolucao = _tem_devolucao_fisica(conta, claim_id)

    cache, _criado = ClaimMercadoLivre.objects.update_or_create(
        claim_id=claim_id,
        defaults={
            'numero_pedido': numero_pedido,
            'meu_papel': meu_papel,
            'dados_brutos': claim,
            'tem_devolucao_fisica': tem_devolucao,
            'esta_acompanhando': True,
            'ultima_busca_em': timezone.now(),
        },
    )
    return cache


# ==== auto-completar MediacaoAvulsa na criação (decisão de Matheus, ====
# 20/09/2026: o motivo de existir "mediação avulsa" em vez de criar
# uma Devolução é não precisar preencher nada à mão -- ao cadastrar,
# tudo que a API já responde sozinha deve ser buscado de uma vez).

def _para_date_local(valor_iso):
    """Converte uma data ISO da API (com timezone) pra um date() no
    fuso de exibição -- mesma conversão já usada em
    integracao_mercado_livre/views.py::_formatar_data_para_input, só
    que devolvendo date() em vez de string formatada pra input HTML
    (aqui o destino é direto um DateField do model). Sem essa conversão
    de fuso, um evento perto da meia-noite (UTC ou fuso da API) podia
    cair gravado no dia errado."""
    if not valor_iso or not isinstance(valor_iso, str):
        return None
    try:
        instante = datetime.fromisoformat(valor_iso)
    except ValueError:
        return None
    return instante.astimezone(FUSO_HORARIO_EXIBICAO).date()


def completar_avulsa_automaticamente(conta, avulsa):
    """Preenche uma MediacaoAvulsa recém-criada com tudo que a API do
    Mercado Livre já consegue responder sozinha. Roda 1x só, de forma
    síncrona, dentro do POST de adicionar_mediacao_avulsa, e nunca
    impede o cadastro de acontecer: cada busca aqui é best-effort
    (mesmo espírito de buscar_nome_cliente_e_produto/
    resolver_claim_por_numero_pedido) -- qualquer falha isolada só
    deixa aquele campo específico em branco, exatamente como já
    ficava antes desta função existir.

    Não reaproveita buscar_nome_cliente_e_produto porque aqui também
    precisamos do preço do produto (ClaimMercadoLivre, pra quem aquela
    função foi feita, não tem esse campo) -- por isso o /orders/ é
    buscado de novo aqui, com a mesma extração já validada em
    view_consultar_pedido (buyer.first_name/last_name,
    order_items[0].item.title, order_items[0].unit_price -- este
    último irmão de "item", não aninhado nele)."""
    numero_pedido = avulsa.numero_pedido
    campos_alterados = []

    try:
        resposta_pedido = chamar_api("GET", f"/orders/{numero_pedido}", pasta_logs=PASTA_LOGS_ML, conta=conta)
        pedido = resposta_pedido.json()
    except (ErroAPI, ErroAutenticacaoAPI):
        pedido = None

    if pedido:
        comprador = pedido.get("buyer") or {}
        nome_cliente = f"{comprador.get('first_name', '')} {comprador.get('last_name', '')}".strip()
        item = (pedido.get("order_items") or [{}])[0]
        nome_produto = (item.get("item") or {}).get("title") or ''
        preco_produto = item.get("unit_price")

        if nome_cliente:
            avulsa.nome_cliente = nome_cliente
            campos_alterados.append('nome_cliente')
        if nome_produto:
            avulsa.nome_produto = nome_produto
            campos_alterados.append('nome_produto')
        if preco_produto is not None:
            try:
                avulsa.preco_produto = Decimal(str(preco_produto))
                campos_alterados.append('preco_produto')
            except (InvalidOperation, TypeError):
                pass

    cache_claim = resolver_claim_por_numero_pedido(conta, numero_pedido)
    if cache_claim:
        avulsa.claim_id = cache_claim.claim_id
        campos_alterados.append('claim_id')

        mensagens_claim = _buscar_mensagens_da_reclamacao(conta, cache_claim.claim_id)
        if mensagens_claim:
            datas_dispute = [
                m.get('date_created') for m in mensagens_claim
                if m.get('stage') == 'dispute' and m.get('date_created')
            ]
            if datas_dispute:
                data_abertura = _para_date_local(min(datas_dispute))
                if data_abertura:
                    avulsa.data_abertura_mediacao = data_abertura
                    campos_alterados.append('data_abertura_mediacao')

        try:
            resposta_devolucao = chamar_api(
                "GET", f"/post-purchase/v2/claims/{cache_claim.claim_id}/returns",
                pasta_logs=PASTA_LOGS_ML, conta=conta,
            )
            dados_devolucao = resposta_devolucao.json()
        except (ErroAPI, ErroAutenticacaoAPI):
            dados_devolucao = None

        data_fechamento = _para_date_local((dados_devolucao or {}).get('date_closed'))
        if data_fechamento:
            avulsa.data_finalizacao_mediacao = data_fechamento
            campos_alterados.append('data_finalizacao_mediacao')

    if campos_alterados:
        avulsa.save(update_fields=campos_alterados)


# ==== categoria (Reclamação / +Mediação / +Devolução / +Mediação+Devolução) ====
#
# Nunca fica salva — sempre recalculada a partir de dados_brutos['stage']
# + tem_devolucao_fisica, reaproveitando a mesma leitura já validada em
# buscar_mediacoes_abertas_recentes.py::classificar() (stage == "dispute"
# é o que decide mediação, não "type"). O slug (com hífen) é o que a
# tela usa em data-combinacao/data-filtro; None quando não dá pra
# confirmar devolução é tratado como "sem devolução" só pra fins de
# exibição do chip/badge — o valor True/False/None real continua salvo
# como veio, sem perda de informação.

def categoria_slug(stage, tem_devolucao_fisica):
    eh_mediacao = stage == 'dispute'
    tem_devolucao = bool(tem_devolucao_fisica)
    if eh_mediacao and tem_devolucao:
        return 'mediacao-devolucao'
    if eh_mediacao:
        return 'mediacao'
    if tem_devolucao:
        return 'devolucao'
    return 'reclamacao'


def contagem_por_categoria(itens):
    """itens = lista de dicts com chave 'categoria_slug' (pode ser None).
    Chaves do dict de retorno usam _ em vez de - (mediacao_devolucao) pra
    dar pra acessar direto no template Django, que não aceita hífen em
    lookup de variável."""
    contagem = {'todas': len(itens), 'reclamacao': 0, 'mediacao': 0, 'devolucao': 0, 'mediacao_devolucao': 0}
    for item in itens:
        slug = item.get('categoria_slug')
        if slug:
            chave = slug.replace('-', '_')
            contagem[chave] = contagem.get(chave, 0) + 1
    return contagem


# ==== orquestração — rodam na thread de segundo plano ====

def _atualizar_status(**campos):
    StatusVarreduraMediacoes.objects.filter(pk=1).update(**campos)


def _concluir_varredura(itens_nao_confirmados):
    StatusVarreduraMediacoes.objects.filter(pk=1).update(
        rodando=False, finalizado_em=timezone.now(),
        itens_nao_confirmados=itens_nao_confirmados, erro='',
    )


def _falhar_varredura(mensagem_tecnica):
    StatusVarreduraMediacoes.objects.filter(pk=1).update(
        rodando=False, finalizado_em=timezone.now(), erro=mensagem_tecnica,
    )


def executar_varredura_completa(empresa):
    """Roda na thread de segundo plano do botão 'Fazer varredura completa
    (6 meses)'. Busca todas as reclamações abertas dos últimos
    MESES_ATRAS meses (respondent E complainant), verifica devolução
    física e mensagens de cada uma, grava/atualiza a cache
    ClaimMercadoLivre item a item e casa automaticamente com Devolucao
    ou MediacaoAvulsa existente pelo numero_pedido (gatilho: presença do
    registro, não a categoria encontrada — decisão de Matheus,
    20/09/2026). A thread precisa chamar definir_empresa_ativa() ela
    mesma logo no início — threading.local() não herda da requisição
    que disparou a thread."""
    definir_empresa_ativa(empresa)
    conta = CONTA_POR_EMPRESA.get(empresa)
    if conta is None:
        _falhar_varredura(f'Empresa ativa "{empresa}" não mapeada pra nenhuma conta MB/SV.')
        return

    try:
        agora = datetime.now(FUSO_HORARIO_EXIBICAO)
        inicio_formatado = _formatar_data_para_filtro(agora - timedelta(days=MESES_ATRAS * 30))
        fim_formatado = _formatar_data_para_filtro(agora)

        _atualizar_status(fase_atual='Buscando reclamações dos últimos 6 meses...')
        user_id = _buscar_user_id(conta)
        claims_encontradas = []
        ids_ja_vistos = set()
        for papel in ('respondent', 'complainant'):
            for c in _buscar_claims_abertas(conta, user_id, papel, inicio_formatado, fim_formatado):
                if c.get('id') in ids_ja_vistos:
                    continue
                ids_ja_vistos.add(c.get('id'))
                claims_encontradas.append((c, papel))

        total = len(claims_encontradas)
        _atualizar_status(total=total)

        itens_nao_confirmados = 0
        for indice, (claim, papel) in enumerate(claims_encontradas, start=1):
            claim_id = str(claim.get('id'))
            numero_pedido = claim.get('resource_id')

            _atualizar_status(fase_atual='Verificando devolução física de cada uma...', processados=indice - 1)
            tem_devolucao = _tem_devolucao_fisica(conta, claim_id)
            if tem_devolucao is None:
                itens_nao_confirmados += 1

            _atualizar_status(fase_atual='Buscando mensagens e dados do pedido...')
            mensagens = _buscar_mensagens_da_reclamacao(conta, claim_id)
            if mensagens is None:
                itens_nao_confirmados += 1

            # * [EXPLICACAO] -> nome do cliente + produto pra TODO item
            #   encontrado, nao so quem vira MediacaoAvulsa -- decisao de
            #   Matheus, 20/09/2026: facilita a vida da Ana (mostra nome
            #   de verdade em "Encontrados pelo Sistema", nao so numero
            #   de pedido) e permite buscar por nome ali tambem. Custo
            #   aceito: mais 1 chamada por item (~0,5-0,7s). Best-effort
            #   (a propria funcao devolve string vazia em qualquer falha,
            #   nunca quebra a varredura) -- por isso NAO soma em
            #   itens_nao_confirmados, mesmo espirito de quem ja usa essa
            #   funcao em acompanhar_claim.
            nome_cliente, nome_produto = buscar_nome_cliente_e_produto(conta, numero_pedido)

            ultima_mensagem_em, ultima_mensagem_de, ultima_mensagem_resumo = calcular_ultima_mensagem(mensagens, papel)

            cache, _criado = ClaimMercadoLivre.objects.update_or_create(
                claim_id=claim_id,
                defaults={
                    'numero_pedido': numero_pedido,
                    'meu_papel': papel,
                    'dados_brutos': claim,
                    'tem_devolucao_fisica': tem_devolucao,
                    'mensagens': mensagens,
                    'nome_cliente': nome_cliente,
                    'nome_produto': nome_produto,
                    'ultima_busca_em': timezone.now(),
                    'ultima_mensagem_em': ultima_mensagem_em,
                    'ultima_mensagem_de': ultima_mensagem_de,
                    'ultima_mensagem_resumo': ultima_mensagem_resumo,
                },
            )

            # * [EXPLICACAO] -> casamento automatico com Devolucao OU
            #   MediacaoAvulsa existente -- so liga a flag, nunca desliga
            #   sozinho. Preenche o claim_id de quem ja existia (Devolucao
            #   esperava por isso desde a migration 0019; MediacaoAvulsa
            #   cadastrada ANTES desta feature nunca tinha claim_id
            #   nenhum -- sem isso ela nunca casava com a cache e a
            #   conversa ficava travada pra sempre no "ainda não
            #   vinculada").
            if not cache.esta_acompanhando:
                devolucao_correspondente = Devolucao.objects.filter(numero_pedido=numero_pedido).first()
                avulsa_correspondente = MediacaoAvulsa.objects.filter(numero_pedido=numero_pedido).first()
                if devolucao_correspondente or avulsa_correspondente:
                    cache.esta_acompanhando = True
                    cache.save(update_fields=['esta_acompanhando'])
                    if devolucao_correspondente and not devolucao_correspondente.claim_id:
                        devolucao_correspondente.claim_id = claim_id
                        devolucao_correspondente.save(update_fields=['claim_id'])
                    if avulsa_correspondente and not avulsa_correspondente.claim_id:
                        avulsa_correspondente.claim_id = claim_id
                        avulsa_correspondente.save(update_fields=['claim_id'])

            _atualizar_status(processados=indice, itens_nao_confirmados=itens_nao_confirmados)

        _concluir_varredura(itens_nao_confirmados)
    except Exception as erro:
        _falhar_varredura(str(erro))


def executar_atualizacao_acompanhados(empresa):
    """Roda na thread de segundo plano do botão 'Atualizar itens em
    acompanhamento' -- refaz devolução física + mensagens só dos claims
    já marcados esta_acompanhando=True (não busca reclamações novas) --
    normalmente ~6 itens, no extremo ~25 (dado por Matheus, 20/09/2026).
    Não re-busca dados_brutos (stage) -- só devolução+mensagens, mesma
    conta de custo (~1,34s/item) usada pra estimar o tempo na tela."""
    definir_empresa_ativa(empresa)
    conta = CONTA_POR_EMPRESA.get(empresa)
    if conta is None:
        _falhar_varredura(f'Empresa ativa "{empresa}" não mapeada pra nenhuma conta MB/SV.')
        return

    try:
        itens = list(ClaimMercadoLivre.objects.filter(esta_acompanhando=True))
        total = len(itens)
        _atualizar_status(total=total)

        itens_nao_confirmados = 0
        for indice, cache in enumerate(itens, start=1):
            _atualizar_status(fase_atual='Verificando devolução física de cada uma...', processados=indice - 1)
            tem_devolucao = _tem_devolucao_fisica(conta, cache.claim_id)
            if tem_devolucao is None:
                itens_nao_confirmados += 1

            _atualizar_status(fase_atual='Buscando e classificando mensagens...')
            mensagens = _buscar_mensagens_da_reclamacao(conta, cache.claim_id)
            if mensagens is None:
                itens_nao_confirmados += 1

            ultima_mensagem_em, ultima_mensagem_de, ultima_mensagem_resumo = calcular_ultima_mensagem(mensagens, cache.meu_papel)

            cache.tem_devolucao_fisica = tem_devolucao
            cache.mensagens = mensagens
            cache.ultima_busca_em = timezone.now()
            cache.ultima_mensagem_em = ultima_mensagem_em
            cache.ultima_mensagem_de = ultima_mensagem_de
            cache.ultima_mensagem_resumo = ultima_mensagem_resumo
            cache.save(update_fields=[
                'tem_devolucao_fisica', 'mensagens', 'ultima_busca_em',
                'ultima_mensagem_em', 'ultima_mensagem_de', 'ultima_mensagem_resumo',
            ])

            _atualizar_status(processados=indice, itens_nao_confirmados=itens_nao_confirmados)

        _concluir_varredura(itens_nao_confirmados)
    except Exception as erro:
        _falhar_varredura(str(erro))


# ==== refresh individual de 1 chat -- síncrono, dentro da própria
# requisição de abrir a tela (decisão de Matheus, 20/09/2026, validada em
# cronometrar_refresh_individual.py: ~0,63s médio isolado, bem abaixo de
# 1s -- não precisa do mecanismo de segundo plano usado pelas 2
# varreduras). Classificação e sanitização das mensagens (bleach) portadas
# de integracao_mercado_livre/views.py::_construir_mensagens_mediacao,
# já validadas em produção no Hub de Consulta -- só que aqui meu_papel já
# vem pronto de ClaimMercadoLivre.meu_papel (cacheado pela varredura), sem
# precisar de uma chamada extra a /users/me pra descobrir.

def _formatar_data_mensagem(valor_iso):
    if not valor_iso or not isinstance(valor_iso, str):
        return None
    try:
        instante = datetime.fromisoformat(valor_iso)
    except ValueError:
        return valor_iso
    instante = instante.astimezone(FUSO_HORARIO_EXIBICAO_MSG)
    return instante.strftime("%d/%m/%Y %H:%M")


def _instante_mensagem(valor_iso):
    """Converte o date_created bruto (string ISO da API, com timezone) num
    datetime timezone-aware de verdade -- usado tanto pra achar a
    mensagem mais recente (calcular_ultima_mensagem) quanto pra decidir
    se uma mensagem é "nova" (comparação com mediacao_visualizada_em).
    Mesmo parse de _formatar_data_mensagem, só que devolvendo o datetime
    cru em vez de string formatada -- aqui o destino é comparação, não
    exibição. None em qualquer valor ausente ou não-parseável (nunca
    derruba a tela por causa de 1 data malformada). Decisão de Matheus,
    21/09/2026.

    [CORREÇÃO 21/09/2026] -> datetime.fromisoformat aceita de boa uma
    string ISO SEM timezone (ex: "2024-01-17T14:36:29", sem o "-04:00"
    no final) e devolve um datetime "naive" sem reclamar nada -- e um
    datetime naive comparado com mediacao_visualizada_em (timezone-aware,
    USE_TZ=True no settings, ver "ultima_mensagem_em > ..." em views.py e
    "instante_msg > desde" em _formatar_mensagens abaixo) explode com
    TypeError, sem nenhum try/except em volta nos dois lugares -- ou
    seja, 1 mensagem sem timezone na resposta do ML derrubava a tela de
    Mediações ML INTEIRA (erro 500 pra todo mundo, não só o detalhe
    daquela mediação). Nunca vimos isso acontecer na prática (API do ML
    sempre manda offset até hoje), mas o próprio docstring acima já
    prometia "nunca derruba a tela" -- assumir o fuso de Brasília quando
    falta um timezone é o que faz essa promessa valer de verdade, em vez
    de só cobrir o caso de data ilegível (ValueError)."""
    if not valor_iso or not isinstance(valor_iso, str):
        return None
    try:
        instante = datetime.fromisoformat(valor_iso)
    except ValueError:
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=FUSO_HORARIO_EXIBICAO_MSG)
    return instante


def _resumo_mensagem(texto_bruto):
    """Versão curta (sem HTML, truncada em ~90 caracteres) de message,
    pra pré-visualização de 1 linha na lista "Em acompanhamento" (estilo
    chat) -- a versão completa e sanitizada pra exibição continua sendo
    _preparar_mensagem_html, usada só no detalhe. Aqui é só texto pra
    lista, então um strip básico de tag HTML (mensagens do mediador às
    vezes vêm com <p>/<br>) já basta, sem precisar de bleach."""
    if not texto_bruto:
        return '(sem texto — mensagem só com anexo)'
    sem_tags = re.sub(r'<[^>]+>', ' ', texto_bruto)
    sem_tags = ' '.join(sem_tags.split())
    if len(sem_tags) > 90:
        sem_tags = sem_tags[:90].rstrip() + '…'
    return sem_tags or '(sem texto — mensagem só com anexo)'


def calcular_ultima_mensagem(mensagens_brutas, meu_papel):
    """A partir de mensagens já cacheadas (cache.mensagens, SEM nenhuma
    chamada nova de API -- mesmo espírito de formatar_mensagens_em_cache)
    ou recém buscadas, acha a mensagem mais recente e devolve
    (instante, quem_mandou, resumo) -- quem_mandou é 'ml'/'voce'/
    'cliente'/None (None quando não dá pra saber com certeza quem
    mandou -- ver correção abaixo), mesmo critério de _formatar_mensagens
    logo abaixo. (None, None, None) quando não existe mensagem nenhuma
    ainda (claim nunca sincronizado, ou reclamação sem nenhuma mensagem
    de fato) -- repare que isso é ambíguo com "tem mensagem mas
    quem_mandou é desconhecido" só de olhar quem_mandou sozinho: nesse 2º
    caso instante e resumo vêm preenchidos, só quem_mandou fica None;
    quem usa o retorno distingue os 2 casos pelos 3 valores juntos, não
    só por quem_mandou isolado.

    [DECISÃO 21/09/2026] -> usado tanto pra ordenar "Em acompanhamento"
    como um chat (mais recente primeiro) quanto pro indicador de
    mensagem nova na lista -- e de propósito só LÊ o que já está
    cacheado, nunca busca nada novo aqui: todo item de "Em
    acompanhamento" tem esta_acompanhando=True no ClaimMercadoLivre
    correspondente (casamento automático da varredura), e
    executar_atualizacao_acompanhados (botão "Atualizar itens em
    acompanhamento") já busca e grava cache.mensagens pra TODO item
    nesse estado -- por isso não precisa de nenhum campo novo no banco
    nem de nenhuma chamada de API extra pra essa ordenação existir.

    [CORREÇÃO 21/09/2026] -> cache.meu_papel fica None quando a busca do
    seu user_id falhou na hora que o claim foi resolvido (API fora do
    ar) ou você não apareceu na lista de "players" do claim -- e nesse
    caso, ANTES, toda mensagem (inclusive uma resposta SUA) caía no
    'else' e virava 'cliente' por eliminação, fazendo sua própria
    resposta aparecer como mensagem não lida do cliente (pontinho
    vermelho na lista + contador "Mensagens novas não vistas" do Painel
    Geral -- os 2 só olham "quem_mandou != voce"). Agora, sem saber quem
    mandou de verdade, devolve quem_mandou=None em vez de arriscar --
    None já é tratado como "não conta como não lida" em views.py (mesma
    checagem "quem_mandou and quem_mandou != 'voce'" já existente, None
    é falsy ali) sem precisar mudar nada lá; o template também para de
    rotular como "Cliente:" nesse caso (ver mediacoes_ml.html). Troca
    uma mensagem não lida de verdade que deixaria de alertar (só
    enquanto meu_papel continuar None) por parar de gritar "mensagem
    nova" toda vez que você mesmo responde -- avise se quiser um
    comportamento diferente pra esse caso."""
    if not mensagens_brutas:
        return None, None, None
    mais_recente = max(mensagens_brutas, key=lambda m: m.get('date_created') or '')
    instante = _instante_mensagem(mais_recente.get('date_created'))
    sender = mais_recente.get('sender_role')
    if sender == 'mediator':
        quem = 'ml'
    elif meu_papel is None:
        quem = None
    elif sender == meu_papel:
        quem = 'voce'
    else:
        quem = 'cliente'
    return instante, quem, _resumo_mensagem(mais_recente.get('message'))


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


def url_anexo_mensagem_fallback(cache, conta, anexo):
    """Monta o link direto (abre em nova guia, na sessão de navegador de
    quem clicar) pra abrir 1 anexo de mensagem na Central de Vendedores
    -- padrão de URL mapeado manualmente antes (vault,
    05_Integracao_Mercado_Livre/Referencia_API/Endpoints) e validado
    agora contra dado real do claim 5564889989. pack_id usa numero_pedido
    (só diverge quando o pedido faz parte de um pack com mais de 1
    pedido, caso ainda não visto na prática -- pior hipótese o link dá
    erro, não quebra a tela). seller_id vem de {CONTA}_USER_ID no .env
    (já existente, mesmo padrão de {CONTA}_ADDRESS_ID).

    Decisão de Matheus, 20/09/2026: não tenta renderizar a imagem
    embutida na própria tela -- essa URL exige cookie de sessão de
    navegador (confirmado testando: sem login, cai na tela de login do
    ML), não o token Bearer da API, e embed cross-site (<img src=...>)
    corre risco real de o navegador bloquear o cookie por política de
    SameSite.

    Atualização 21/09/2026: deixou de ser o link principal do ícone --
    virou só o alvo do redirect de devolucoes.views.proxy_anexo_mediacao,
    usado quando a tentativa via API (Bearer token) falha. Renomeada (sem
    underscore) porque agora é chamada de fora deste módulo, por
    views.py -- deixou de ser função privada."""
    filename = anexo.get('filename')
    seller_id = os.getenv(f'{conta}_USER_ID')
    if not filename or not seller_id:
        return None
    return (
        f'https://vendedores.mercadolivre.com.br/api/messages/packs/{cache.numero_pedido}'
        f'/sellers/{seller_id}/messages/attachments/{filename}'
        f'?siteId=MLB&tag=claim&claimId={cache.claim_id}&dispute=false'
    )


def _url_proxy_anexo(cache, anexo):
    """Monta a URL do proxy de anexo (devolucoes.views.proxy_anexo_mediacao).

    Troca de 21/09/2026: em vez de mandar o clique direto pro link
    cookie-auth de url_anexo_mensagem_fallback (acima), agora passa
    primeiro pelo backend, que tenta baixar o anexo com o Bearer token da
    API (post-purchase/v1/claims/.../download -- validado empírica e
    documentalmente, ver vault "Validação da Documentação Oficial do
    Endpoint de Download de Anexos"). Só se essa chamada falhar (claim
    antigo, erro de autenticação, qualquer outro erro) o proxy
    redireciona pro link antigo de url_anexo_mensagem_fallback -- o
    comportamento anterior continua existindo, só como rede de
    segurança, não como caminho principal. Sem cache em disco: o proxy
    só repassa os bytes, não salva nada."""
    filename = anexo.get('filename')
    if not filename:
        return None
    return reverse('proxy_anexo_mediacao', args=[cache.claim_id, filename])


def _formatar_mensagens(mensagens_brutas, cache, nome_cliente, conta, desde=None):
    """Extraído de atualizar_e_formatar_mensagens -- só formatação
    (papel/rótulo/iniciais/data/texto_html/anexos/nova), sem nenhuma
    chamada de API nova (attachments já vem dentro de mensagens_brutas).
    Reaproveitado tanto por quem busca mensagens frescas quanto por quem
    só formata o que já está em cache.mensagens (pré-visualização de
    'Encontrados pelo Sistema', decisão de Matheus 20/09/2026).

    'desde' (opcional) é o mediacao_visualizada_em ANTERIOR à abertura
    atual da tela (capturado por quem chama, antes de sobrescrever com
    "agora") -- uma mensagem vira 'nova' quando não é nossa E é mais
    recente que 'desde' (ou 'desde' é None, 1ª vez que essa mediação é
    aberta). Sem 'desde', nenhuma mensagem é marcada como nova -- é o
    caso da pré-visualização de 'Encontrados pelo Sistema', que ainda
    não é uma mediação acompanhada de verdade. Decisão de Matheus,
    21/09/2026 -- fecha a promessa de indicador de mensagem nova que a
    própria tela já fazia."""
    iniciais_cliente = (nome_cliente or '').strip()[:1].upper() or 'CL'
    mensagens_ordenadas = sorted(mensagens_brutas, key=lambda m: m.get('date_created') or '')

    resultado = []
    for m in mensagens_ordenadas:
        sender = m.get('sender_role')
        if sender == 'mediator':
            papel, rotulo, iniciais = 'ml', 'Mercado Livre', 'ML'
        elif cache.meu_papel is not None and sender == cache.meu_papel:
            papel, rotulo, iniciais = 'voce', 'Você', conta
        else:
            papel, rotulo, iniciais = 'cliente', 'Cliente', iniciais_cliente

        anexos = []
        for anexo in (m.get('attachments') or []):
            url = _url_proxy_anexo(cache, anexo)
            if url:
                anexos.append({'url': url})

        instante_msg = _instante_mensagem(m.get('date_created'))
        nova = bool(desde and papel != 'voce' and instante_msg and instante_msg > desde)

        resultado.append({
            'papel': papel,
            'rotulo': rotulo,
            'iniciais': iniciais,
            'data': _formatar_data_mensagem(m.get('date_created')),
            'texto_html': _preparar_mensagem_html(m.get('message')),
            'anexos': anexos,
            'nova': nova,
        })
    return resultado


def atualizar_e_formatar_mensagens(conta, cache, nome_cliente, desde=None):
    """Busca mensagens frescas da claim (1 chamada síncrona) e já devolve
    formatadas pra exibição (papel/rótulo/iniciais/data/texto_html/nova).
    Em caso de falha na busca, cai pro que já estava salvo na cache (pode
    ser None, se nunca buscou com sucesso antes) -- nunca perde o que já
    tinha por causa de 1 chamada que falhou agora. 'desde' só é usado pra
    marcar mensagens como 'nova' (ver _formatar_mensagens) -- passa
    direto. Devolve (mensagens_formatadas_ou_None, sucesso)."""
    mensagens_brutas = _buscar_mensagens_da_reclamacao(conta, cache.claim_id)
    sucesso = mensagens_brutas is not None

    if sucesso:
        ultima_mensagem_em, ultima_mensagem_de, ultima_mensagem_resumo = calcular_ultima_mensagem(mensagens_brutas, cache.meu_papel)

        cache.mensagens = mensagens_brutas
        cache.ultima_busca_em = timezone.now()
        cache.ultima_mensagem_em = ultima_mensagem_em
        cache.ultima_mensagem_de = ultima_mensagem_de
        cache.ultima_mensagem_resumo = ultima_mensagem_resumo
        cache.save(update_fields=[
            'mensagens', 'ultima_busca_em',
            'ultima_mensagem_em', 'ultima_mensagem_de', 'ultima_mensagem_resumo',
        ])
    else:
        mensagens_brutas = cache.mensagens

    if not mensagens_brutas:
        return ([] if sucesso else None), sucesso

    return _formatar_mensagens(mensagens_brutas, cache, nome_cliente, conta, desde=desde), sucesso


def formatar_mensagens_em_cache(cache, nome_cliente, conta, desde=None):
    """Formata só o que já está salvo em cache.mensagens -- SEM nenhuma
    chamada nova a API. Usado na pré-visualização de um item 'Encontrados
    pelo Sistema' (decisão de Matheus, 20/09/2026): a varredura já pagou
    por essas mensagens, abrir o mesmo claim de novo não deveria custar
    outra chamada -- só quando Ana clicar em 'Atualizar' de propósito é
    que atualizar_e_formatar_mensagens (acima) entra em ação. Devolve
    sempre uma lista (nunca None) -- vazia quando não tem nada em cache
    ainda. 'desde' segue o mesmo contrato de _formatar_mensagens (sem uso
    hoje -- pré-visualização não é mediação acompanhada, não tem
    'visualizada_em' pra comparar -- existe só pra manter a assinatura
    igual à de atualizar_e_formatar_mensagens)."""
    if not cache.mensagens:
        return []
    return _formatar_mensagens(cache.mensagens, cache, nome_cliente, conta, desde=desde)
