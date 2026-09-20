#!/usr/bin/env python
# aplicar_mediacoes_varredura.py
#
# Aplica TODAS as mudanças do redesenho do Painel de Mediações (varredura
# em segundo plano, cache ClaimMercadoLivre, grupos "Encontrados pelo
# Sistema"/"Em Acompanhamento", 4 chips de categoria) de uma vez só.
#
# Rode a partir da RAIZ do repositório (onde fica o manage.py):
#   python aplicar_mediacoes_varredura.py
#
# Só mexe em arquivos — não roda migration nenhuma sozinho. Os comandos
# de migration (nas 2 bases, magazine e samvale) ficam no resumo impresso
# no final, pra você rodar quando quiser.

import io
from pathlib import Path

RAIZ = Path.cwd()

if not (RAIZ / 'manage.py').exists():
    raise SystemExit(
        'Não achei manage.py em ' + str(RAIZ) + ' — rode este script a partir '
        'da raiz do repositório (Projeto-Sistema-Devolucao).'
    )


def ler(caminho):
    with io.open(RAIZ / caminho, 'r', encoding='utf-8') as f:
        return f.read()


def escrever(caminho, texto):
    with io.open(RAIZ / caminho, 'w', encoding='utf-8', newline='\n') as f:
        f.write(texto)


def substituir(caminho, antigo, novo, esperado=1):
    texto = ler(caminho)
    contagem = texto.count(antigo)
    if contagem != esperado:
        raise AssertionError(
            '[{}] esperava encontrar o trecho-ancora {}x, encontrei {}x -- '
            'o arquivo ja foi alterado antes (script rodado 2x?) ou o '
            'conteudo real diverge do esperado. Abortando sem tocar em mais '
            'nada.'.format(caminho, esperado, contagem)
        )
    escrever(caminho, texto.replace(antigo, novo))
    print('  OK -- ' + caminho)


def criar(caminho, conteudo):
    destino = RAIZ / caminho
    if destino.exists():
        print('  JA EXISTE, pulando -- ' + caminho)
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    escrever(caminho, conteudo)
    print('  CRIADO -- ' + caminho)


print('1/9 -- Novos arquivos de model')

criar('devolucoes/models/claim_mercado_livre.py', '''from django.db import models


class ClaimMercadoLivre(models.Model):
    # * [EXPLICACAO] -> cache generica de toda reclamacao (claim) que
    #   qualquer varredura ja encontrou na API do Mercado Livre -- 1
    #   registro por claim_id, independente de virar "Em Acompanhamento"
    #   ou nao. Existe porque cada chamada de API e "cara" (rate limit +
    #   tempo real, ver cronometragem em cronometrar_refresh_individual.py
    #   e buscar_mediacoes_abertas_recentes.py) -- um dado ja buscado nao
    #   pode ser jogado fora. Roteada pelas 2 bases (MB/SV) via
    #   EmpresaRouter, como todo o resto do app `devolucoes`.
    #   Decisao de Matheus (20/09/2026) -- ver vault "Redesenho do Painel
    #   de Mediacoes -- Encontrados pelo Sistema, Em Acompanhamento e
    #   Varredura em Segundo Plano".
    claim_id = models.CharField('ID da reclamação/mediação no ML', max_length=50, primary_key=True)
    numero_pedido = models.CharField(
        'Número do pedido', max_length=100, db_index=True,
        help_text='Chave de casamento com Devolucao.numero_pedido — não é única aqui (mais de 1 claim pode existir pro mesmo pedido ao longo do tempo).',
    )
    meu_papel = models.CharField(
        'Nosso papel nesta reclamação', max_length=20,
        help_text='"respondent" ou "complainant" — vem de qual busca (players.role) encontrou o claim.',
    )
    dados_brutos = models.JSONField(
        'Dados brutos do claim',
        help_text='Resposta bruta da API (stage, type, date_created, players...) — usada pra recalcular a combinação Reclamação/Mediação/Devolução via categoria_slug().',
    )
    tem_devolucao_fisica = models.BooleanField(
        'Tem devolução física associada?', null=True,
        help_text='True/False confirmado via GET /post-purchase/v2/claims/{id}/returns — None quando não deu pra confirmar (erro que não foi um 404 limpo).',
    )
    mensagens = models.JSONField('Mensagens da reclamação', null=True, blank=True)
    esta_acompanhando = models.BooleanField(
        'Está em acompanhamento?', default=False,
        help_text='Liga automaticamente (casa com Devolucao pelo numero_pedido) ou manualmente ("Acompanhar") — só desliga por ação explícita ("Deixar de acompanhar"), nunca reativa sozinha numa varredura futura.',
    )
    ultima_busca_em = models.DateTimeField('Última busca em')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ultima_busca_em']

    def __str__(self):
        return f'Claim {self.claim_id} — pedido {self.numero_pedido}'
''')

criar('devolucoes/models/status_varredura_mediacoes.py', '''from django.db import models


class StatusVarreduraMediacoes(models.Model):
    # * [EXPLICACAO] -> registro unico (sempre pk=1, nunca historico) do
    #   estado da varredura de mediacoes em segundo plano -- sobrescrito a
    #   cada nova execucao, nunca 1 linha por execucao (decisao de
    #   Matheus, 20/09/2026: nao da pra debugar remotamente no PC da Ana,
    #   entao so importa o estado atual/ultimo). Travado contra clique
    #   duplo via UPDATE...WHERE atomico direto no banco (ver
    #   devolucoes/views.py::iniciar_varredura_mediacoes), nao
    #   select_for_update()/transaction.atomic(). Roteada pelas 2 bases
    #   (MB/SV) via EmpresaRouter, como todo o resto do app `devolucoes`
    #   -- cada empresa tem sua propria linha singleton, migrada e semeada
    #   nas 2 (--database magazine/--database samvale).
    TIPO_COMPLETA = 'completa'
    TIPO_ACOMPANHADOS = 'acompanhados'
    TIPO_EXECUCAO_CHOICES = [
        (TIPO_COMPLETA, 'Varredura completa'),
        (TIPO_ACOMPANHADOS, 'Atualização de itens em acompanhamento'),
    ]

    rodando = models.BooleanField('Rodando agora?', default=False)
    tipo_execucao = models.CharField('Tipo de execução', max_length=20, choices=TIPO_EXECUCAO_CHOICES, null=True, blank=True)
    fase_atual = models.CharField('Fase atual', max_length=100, null=True, blank=True)
    processados = models.IntegerField('Processados', default=0)
    total = models.IntegerField('Total', default=0)
    itens_nao_confirmados = models.IntegerField(
        'Itens não confirmados', default=0,
        help_text='Soma de erros pontuais (devolução física e/ou mensagens) que não pararam o loop — mesmo padrão do script de exploração.',
    )
    iniciado_em = models.DateTimeField('Iniciado em', null=True, blank=True)
    finalizado_em = models.DateTimeField('Finalizado em', null=True, blank=True)
    erro = models.TextField(
        'Erro técnico (debug)', blank=True,
        help_text='Mensagem técnica crua da falha, só pra debug do Matheus (banco/logs) — NUNCA exibida pra Ana. A tela mostra sempre o mesmo texto fixo e amigável quando este campo não está vazio.',
    )

    def __str__(self):
        return f'Status da varredura de mediações (rodando={self.rodando})'
''')


print('2/9 -- devolucoes/models/__init__.py')

substituir(
    'devolucoes/models/__init__.py',
    "from .mediacao_avulsa import MediacaoAvulsa",
    "from .mediacao_avulsa import MediacaoAvulsa\n"
    "from .claim_mercado_livre import ClaimMercadoLivre\n"
    "from .status_varredura_mediacoes import StatusVarreduraMediacoes",
)


print('3/9 -- Migration 0020')

ja_tem_0020 = any(
    p.name.startswith('0020_')
    for p in (RAIZ / 'devolucoes' / 'migrations').glob('0020_*.py')
)
if ja_tem_0020:
    print('  JA EXISTE um arquivo 0020_*.py em devolucoes/migrations/, pulando a criacao da migration.')
else:
    criar('devolucoes/migrations/0020_claim_mercado_livre_status_varredura_mediacoes.py', '''from django.db import migrations, models


def semear_status_varredura(apps, schema_editor):
    StatusVarreduraMediacoes = apps.get_model('devolucoes', 'StatusVarreduraMediacoes')
    StatusVarreduraMediacoes.objects.get_or_create(pk=1)


def remover_status_varredura(apps, schema_editor):
    StatusVarreduraMediacoes = apps.get_model('devolucoes', 'StatusVarreduraMediacoes')
    StatusVarreduraMediacoes.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0019_devolucao_claim_id_mediacaoavulsa_claim_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClaimMercadoLivre',
            fields=[
                ('claim_id', models.CharField(max_length=50, primary_key=True, serialize=False, verbose_name='ID da reclamação/mediação no ML')),
                ('numero_pedido', models.CharField(db_index=True, help_text='Chave de casamento com Devolucao.numero_pedido — não é única aqui (mais de 1 claim pode existir pro mesmo pedido ao longo do tempo).', max_length=100, verbose_name='Número do pedido')),
                ('meu_papel', models.CharField(help_text='"respondent" ou "complainant" — vem de qual busca (players.role) encontrou o claim.', max_length=20, verbose_name='Nosso papel nesta reclamação')),
                ('dados_brutos', models.JSONField(help_text='Resposta bruta da API (stage, type, date_created, players...) — usada pra recalcular a combinação Reclamação/Mediação/Devolução via categoria_slug().', verbose_name='Dados brutos do claim')),
                ('tem_devolucao_fisica', models.BooleanField(help_text='True/False confirmado via GET /post-purchase/v2/claims/{id}/returns — None quando não deu pra confirmar (erro que não foi um 404 limpo).', null=True, verbose_name='Tem devolução física associada?')),
                ('mensagens', models.JSONField(blank=True, null=True, verbose_name='Mensagens da reclamação')),
                ('esta_acompanhando', models.BooleanField(default=False, help_text='Liga automaticamente (casa com Devolucao pelo numero_pedido) ou manualmente ("Acompanhar") — só desliga por ação explícita ("Deixar de acompanhar"), nunca reativa sozinha numa varredura futura.', verbose_name='Está em acompanhamento?')),
                ('ultima_busca_em', models.DateTimeField(verbose_name='Última busca em')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-ultima_busca_em'],
            },
        ),
        migrations.CreateModel(
            name='StatusVarreduraMediacoes',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rodando', models.BooleanField(default=False, verbose_name='Rodando agora?')),
                ('tipo_execucao', models.CharField(blank=True, choices=[('completa', 'Varredura completa'), ('acompanhados', 'Atualização de itens em acompanhamento')], max_length=20, null=True, verbose_name='Tipo de execução')),
                ('fase_atual', models.CharField(blank=True, max_length=100, null=True, verbose_name='Fase atual')),
                ('processados', models.IntegerField(default=0, verbose_name='Processados')),
                ('total', models.IntegerField(default=0, verbose_name='Total')),
                ('itens_nao_confirmados', models.IntegerField(default=0, help_text='Soma de erros pontuais (devolução física e/ou mensagens) que não pararam o loop — mesmo padrão do script de exploração.', verbose_name='Itens não confirmados')),
                ('iniciado_em', models.DateTimeField(blank=True, null=True, verbose_name='Iniciado em')),
                ('finalizado_em', models.DateTimeField(blank=True, null=True, verbose_name='Finalizado em')),
                ('erro', models.TextField(blank=True, help_text='Mensagem técnica crua da falha, só pra debug do Matheus (banco/logs) — NUNCA exibida pra Ana. A tela mostra sempre o mesmo texto fixo e amigável quando este campo não está vazio.', verbose_name='Erro técnico (debug)')),
            ],
        ),
        migrations.RunPython(semear_status_varredura, remover_status_varredura),
    ]
''')


print('4/9 -- devolucoes/varredura_mediacoes.py (logica da varredura em segundo plano)')

criar('devolucoes/varredura_mediacoes.py', '''# devolucoes/varredura_mediacoes.py

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

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI
from core.empresa import definir_empresa_ativa
from integracao_mercado_livre.views import CONTA_POR_EMPRESA, PASTA_LOGS_ML

from .models import ClaimMercadoLivre, Devolucao, StatusVarreduraMediacoes

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
    existente pelo numero_pedido (gatilho: presença da Devolucao, não a
    categoria encontrada — decisão de Matheus, 20/09/2026). A thread
    precisa chamar definir_empresa_ativa() ela mesma logo no início —
    threading.local() não herda da requisição que disparou a thread."""
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

            _atualizar_status(fase_atual='Buscando e classificando mensagens...')
            mensagens = _buscar_mensagens_da_reclamacao(conta, claim_id)
            if mensagens is None:
                itens_nao_confirmados += 1

            cache, _criado = ClaimMercadoLivre.objects.update_or_create(
                claim_id=claim_id,
                defaults={
                    'numero_pedido': numero_pedido,
                    'meu_papel': papel,
                    'dados_brutos': claim,
                    'tem_devolucao_fisica': tem_devolucao,
                    'mensagens': mensagens,
                    'ultima_busca_em': timezone.now(),
                },
            )

            # * [EXPLICACAO] -> casamento automatico com Devolucao
            #   existente -- so liga a flag, nunca desliga sozinho.
            #   Preenche o claim_id da Devolucao, que ja esperava por isso
            #   desde a migration 0019.
            if not cache.esta_acompanhando:
                devolucao_correspondente = Devolucao.objects.filter(numero_pedido=numero_pedido).first()
                if devolucao_correspondente:
                    cache.esta_acompanhando = True
                    cache.save(update_fields=['esta_acompanhando'])
                    if not devolucao_correspondente.claim_id:
                        devolucao_correspondente.claim_id = claim_id
                        devolucao_correspondente.save(update_fields=['claim_id'])

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

            cache.tem_devolucao_fisica = tem_devolucao
            cache.mensagens = mensagens
            cache.ultima_busca_em = timezone.now()
            cache.save(update_fields=['tem_devolucao_fisica', 'mensagens', 'ultima_busca_em'])

            _atualizar_status(processados=indice, itens_nao_confirmados=itens_nao_confirmados)

        _concluir_varredura(itens_nao_confirmados)
    except Exception as erro:
        _falhar_varredura(str(erro))
''')


print('5/9 -- devolucoes/views.py (imports)')

substituir(
    'devolucoes/views.py',
    """import json
import re
import subprocess
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from core.empresa import obter_alias_banco_ativo

from .models import (
    Compatibilidade, ConferenciaPeca, Devolucao, FotoConferenciaPeca,
    FotoObservacaoGeral, FotoReclamacaoCliente, GrupoFornecedor, Marca,
    MediacaoAvulsa, ModeloAnotacao, Peca, Produto,
)
from .reorganizacao_fotos import reorganizar_fotos_devolucao""",
    """import json
import re
import subprocess
import threading
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from core.empresa import obter_alias_banco_ativo, obter_empresa_ativa
from integracao_mercado_livre.views import CONTA_POR_EMPRESA

from .models import (
    ClaimMercadoLivre, Compatibilidade, ConferenciaPeca, Devolucao,
    FotoConferenciaPeca, FotoObservacaoGeral, FotoReclamacaoCliente,
    GrupoFornecedor, Marca, MediacaoAvulsa, ModeloAnotacao, Peca, Produto,
    StatusVarreduraMediacoes,
)
from .reorganizacao_fotos import reorganizar_fotos_devolucao
from .varredura_mediacoes import (
    buscar_nome_cliente_e_produto, categoria_slug, contagem_por_categoria,
    executar_atualizacao_acompanhados, executar_varredura_completa,
)""",
)


print('6/9 -- devolucoes/views.py (_serializar_mediacao, mediacoes_ml, 5 views novas)')

substituir(
    'devolucoes/views.py',
    """    return {
        'tipo': tipo,
        'id': obj.id,
        'numero_pedido': obj.numero_pedido,
        'nome_cliente': obj.nome_cliente,
        'nome_produto': obj.produto.nome if tipo == 'devolucao' else obj.nome_produto,
        'reembolsado_filtro': obj.reembolsado_filtro,
        'data_abertura_mediacao': obj.data_abertura_mediacao,
        'data_finalizacao_mediacao': obj.data_finalizacao_mediacao,
    }""",
    """    return {
        'tipo': tipo,
        'id': obj.id,
        'claim_id': obj.claim_id,
        'numero_pedido': obj.numero_pedido,
        'nome_cliente': obj.nome_cliente,
        'nome_produto': obj.produto.nome if tipo == 'devolucao' else obj.nome_produto,
        'reembolsado_filtro': obj.reembolsado_filtro,
        'data_abertura_mediacao': obj.data_abertura_mediacao,
        'data_finalizacao_mediacao': obj.data_finalizacao_mediacao,
    }""",
)

substituir(
    'devolucoes/views.py',
    """    mediacoes_encerradas = sorted(
        [_serializar_mediacao(d, 'devolucao') for d in devolucoes_encerradas]
        + [_serializar_mediacao(a, 'avulsa') for a in avulsas_encerradas],
        key=lambda m: m['data_finalizacao_mediacao'] or date.min,
        reverse=True,
    )

    mediacao_selecionada = None""",
    """    mediacoes_encerradas = sorted(
        [_serializar_mediacao(d, 'devolucao') for d in devolucoes_encerradas]
        + [_serializar_mediacao(a, 'avulsa') for a in avulsas_encerradas],
        key=lambda m: m['data_finalizacao_mediacao'] or date.min,
        reverse=True,
    )

    # * [EXPLICACAO] -> categoria (Reclamacao/+Mediacao/+Devolucao/+
    #   Mediacao+Devolucao) de cada item de "Em Acompanhamento" -- so
    #   resolve pra quem ja tem claim_id (casado por uma varredura alguma
    #   vez); quem ainda nao foi casado fica sem badge de categoria
    #   (mostra o badge "Aberta" de sempre) em vez de arriscar uma
    #   classificacao errada -- e continua sempre visivel nos 4 chips
    #   (so item com categoria resolvida e escondido pelo filtro).
    cache_por_claim_id = {
        c.claim_id: c
        for c in ClaimMercadoLivre.objects.filter(
            claim_id__in=[m['claim_id'] for m in mediacoes_abertas if m['claim_id']]
        )
    }
    for item in mediacoes_abertas:
        cache = cache_por_claim_id.get(item['claim_id'])
        item['categoria_slug'] = categoria_slug(cache.dados_brutos.get('stage'), cache.tem_devolucao_fisica) if cache else None

    # * [EXPLICACAO] -> "Encontrados pelo Sistema" -- resultado bruto da
    #   ultima varredura, so o que ainda NAO esta em acompanhamento (quem
    #   ja esta, aparece do lado de "Em Acompanhamento" acima). Nunca
    #   aparece em "Encerradas" -- a varredura so busca status "opened".
    #   Decisao de Matheus, 20/09/2026.
    encontrados = [
        {
            'claim_id': c.claim_id,
            'numero_pedido': c.numero_pedido,
            'categoria_slug': categoria_slug(c.dados_brutos.get('stage'), c.tem_devolucao_fisica),
        }
        for c in ClaimMercadoLivre.objects.filter(esta_acompanhando=False)
    ]

    contagem_encontrados = contagem_por_categoria(encontrados)
    contagem_acompanhamento = contagem_por_categoria(mediacoes_abertas)

    mediacao_selecionada = None""",
)

substituir(
    'devolucoes/views.py',
    """    contexto = {
        'mediacoes_abertas': mediacoes_abertas,
        'mediacoes_encerradas': mediacoes_encerradas,
        'mediacao_selecionada': mediacao_selecionada,
        'tipo_selecionado': tipo_selecionado,
        'aba_ativa': aba_ativa,
        'pagina_ativa': 'mediacoes_ml',
    }
    return render(request, 'devolucoes/mediacoes_ml.html', contexto)""",
    """    contexto = {
        'mediacoes_abertas': mediacoes_abertas,
        'mediacoes_encerradas': mediacoes_encerradas,
        'encontrados': encontrados,
        'contagem_encontrados': contagem_encontrados,
        'contagem_acompanhamento': contagem_acompanhamento,
        'mediacao_selecionada': mediacao_selecionada,
        'tipo_selecionado': tipo_selecionado,
        'aba_ativa': aba_ativa,
        'pagina_ativa': 'mediacoes_ml',
    }
    return render(request, 'devolucoes/mediacoes_ml.html', contexto)""",
)

substituir(
    'devolucoes/views.py',
    """    if request.method == 'POST':
        numero_pedido = avulsa.numero_pedido
        avulsa.delete()
        messages.success(request, f'Mediação avulsa do pedido {numero_pedido} removida da lista.')

    return redirect('mediacoes_ml')


def _pecas_para_conferencia(devolucao):""",
    """    if request.method == 'POST':
        numero_pedido = avulsa.numero_pedido
        avulsa.delete()
        messages.success(request, f'Mediação avulsa do pedido {numero_pedido} removida da lista.')

    return redirect('mediacoes_ml')


def iniciar_varredura_mediacoes(request):
    \"\"\"Dispara em segundo plano a varredura completa (6 meses, empresa
    ativa da sessão) de reclamações abertas na API do Mercado Livre --
    trava contra clique duplo via UPDATE...WHERE atômico (não
    select_for_update()), 1 só por vez entre os 2 botões de varredura.
    Sempre POST, sempre AJAX (a tela faz polling em
    status_varredura_mediacoes enquanto isso roda). Decisão de Matheus,
    20/09/2026 -- ver vault 'Redesenho do Painel de Mediações'.\"\"\"
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    linhas = StatusVarreduraMediacoes.objects.filter(pk=1, rodando=False).update(
        rodando=True, tipo_execucao=StatusVarreduraMediacoes.TIPO_COMPLETA,
        fase_atual='Iniciando...', processados=0, total=0, itens_nao_confirmados=0,
        iniciado_em=timezone.now(), finalizado_em=None, erro='',
    )
    if not linhas:
        return JsonResponse({'erro': 'Já existe uma varredura em andamento.'}, status=409)

    empresa = obter_empresa_ativa()
    threading.Thread(target=executar_varredura_completa, args=(empresa,), daemon=True).start()
    return JsonResponse({'ok': True})


def iniciar_atualizacao_acompanhados(request):
    \"\"\"Mesmo mecanismo de iniciar_varredura_mediacoes, mas só atualiza
    devolução física + mensagens dos itens já marcados
    esta_acompanhando=True (não busca reclamações novas) -- tipicamente
    ~6 itens, no extremo ~25 (dado por Matheus, 20/09/2026).\"\"\"
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    linhas = StatusVarreduraMediacoes.objects.filter(pk=1, rodando=False).update(
        rodando=True, tipo_execucao=StatusVarreduraMediacoes.TIPO_ACOMPANHADOS,
        fase_atual='Iniciando...', processados=0, total=0, itens_nao_confirmados=0,
        iniciado_em=timezone.now(), finalizado_em=None, erro='',
    )
    if not linhas:
        return JsonResponse({'erro': 'Já existe uma varredura em andamento.'}, status=409)

    empresa = obter_empresa_ativa()
    threading.Thread(target=executar_atualizacao_acompanhados, args=(empresa,), daemon=True).start()
    return JsonResponse({'ok': True})


def status_varredura_mediacoes(request):
    \"\"\"Estado atual (ou da última execução) da varredura de mediações --
    alimenta tanto o polling durante a execução quanto a checagem no
    carregamento da página (pra mostrar o aviso na hora se Ana sair e
    voltar, ou der F5, com uma varredura em andamento). Nunca devolve o
    texto técnico cru de `erro` -- só se existe ou não; a tela sempre
    mostra a mesma mensagem fixa e amigável (decisão de Matheus,
    20/09/2026: ela é usuária comum, nada técnico pra ela).\"\"\"
    status = StatusVarreduraMediacoes.objects.filter(pk=1).first()
    if status is None:
        return JsonResponse({'rodando': False, 'tipo_execucao': None, 'fase_atual': None, 'processados': 0, 'total': 0, 'tem_erro': False})

    return JsonResponse({
        'rodando': status.rodando,
        'tipo_execucao': status.tipo_execucao,
        'fase_atual': status.fase_atual,
        'processados': status.processados,
        'total': status.total,
        'itens_nao_confirmados': status.itens_nao_confirmados,
        'tem_erro': bool(status.erro),
    })


def acompanhar_claim(request, claim_id):
    \"\"\"Caminho manual do mecanismo 'está acompanhando' -- Ana clica
    'Acompanhar' num item de 'Encontrados pelo Sistema'. Cria uma
    MediacaoAvulsa (mesmo padrão de adicionar_mediacao_avulsa) só quando
    o pedido ainda não tem Devolucao nem MediacaoAvulsa cadastrada; se já
    tiver (ex: o casamento automático da varredura chegou primeiro, ou
    ela deixou de acompanhar antes e mudou de ideia), só liga a flag da
    cache de novo, sem duplicar nada. Decisão de Matheus, 20/09/2026.\"\"\"
    cache = get_object_or_404(ClaimMercadoLivre, pk=claim_id)

    if request.method == 'POST' and not cache.esta_acompanhando:
        ja_existe = (
            Devolucao.objects.filter(numero_pedido=cache.numero_pedido).exists()
            or MediacaoAvulsa.objects.filter(numero_pedido=cache.numero_pedido).exists()
        )
        if not ja_existe:
            conta = CONTA_POR_EMPRESA.get(obter_empresa_ativa())
            nome_cliente, nome_produto = buscar_nome_cliente_e_produto(conta, cache.numero_pedido) if conta else ('', '')
            MediacaoAvulsa.objects.create(
                numero_pedido=cache.numero_pedido,
                claim_id=cache.claim_id,
                nome_cliente=nome_cliente,
                nome_produto=nome_produto,
            )
        cache.esta_acompanhando = True
        cache.save(update_fields=['esta_acompanhando'])
        messages.success(request, f'Pedido {cache.numero_pedido} agora está em acompanhamento.')

    return redirect('mediacoes_ml')


def deixar_de_acompanhar_claim(request, claim_id):
    \"\"\"Desliga a flag 'está acompanhando' -- sempre não destrutivo (não
    apaga Devolucao/MediacaoAvulsa nem a linha de cache), mesmo mecanismo
    pros 2 tipos de mediação. O 'Excluir mediação avulsa' que já existe
    (excluir_mediacao_avulsa, apaga de vez) continua disponível como ação
    separada, mais forte. Decisão de Matheus, 20/09/2026.\"\"\"
    cache = get_object_or_404(ClaimMercadoLivre, pk=claim_id)

    if request.method == 'POST':
        cache.esta_acompanhando = False
        cache.save(update_fields=['esta_acompanhando'])
        messages.success(request, f'Pedido {cache.numero_pedido} não está mais em acompanhamento.')

    return redirect('mediacoes_ml')


def _pecas_para_conferencia(devolucao):""",
)


print('7/9 -- devolucoes/urls.py')

substituir(
    'devolucoes/urls.py',
    """    path('mediacoes/avulsa/<int:avulsa_id>/excluir/', views.excluir_mediacao_avulsa, name='excluir_mediacao_avulsa'),

    path('produtos/', views.produtos, name='produtos'),""",
    """    path('mediacoes/avulsa/<int:avulsa_id>/excluir/', views.excluir_mediacao_avulsa, name='excluir_mediacao_avulsa'),
    path('mediacoes/varredura/iniciar/', views.iniciar_varredura_mediacoes, name='iniciar_varredura_mediacoes'),
    path('mediacoes/varredura/atualizar-acompanhados/', views.iniciar_atualizacao_acompanhados, name='iniciar_atualizacao_acompanhados'),
    path('mediacoes/varredura/status/', views.status_varredura_mediacoes, name='status_varredura_mediacoes'),
    path('mediacoes/claim/<str:claim_id>/acompanhar/', views.acompanhar_claim, name='acompanhar_claim'),
    path('mediacoes/claim/<str:claim_id>/deixar-de-acompanhar/', views.deixar_de_acompanhar_claim, name='deixar_de_acompanhar_claim'),

    path('produtos/', views.produtos, name='produtos'),""",
)


print('8/9 -- template mediacoes_ml.html')

substituir(
    'devolucoes/templates/devolucoes/mediacoes_ml.html',
    """        <div class="dp-campo-busca">
            <i class="fas fa-magnifying-glass"></i>
            <input type="text" id="busca-mediacoes" placeholder="Buscar por pedido, cliente ou produto...">
        </div>

        <div class="dp-abas-nav">""",
    """        <div class="dp-campo-busca">
            <i class="fas fa-magnifying-glass"></i>
            <input type="text" id="busca-mediacoes" placeholder="Buscar por pedido, cliente ou produto...">
        </div>

        <div class="med-linha-varredura">
            <button type="button" class="dp-btn dp-btn--principal med-btn-varredura" id="btn-varredura-completa">
                <i class="fas fa-arrows-rotate"></i> Fazer varredura completa (6 meses)
            </button>
            <button type="button" class="dp-btn med-btn-varredura" id="btn-atualizar-acompanhados">
                <i class="fas fa-arrows-rotate"></i> Atualizar itens em acompanhamento
            </button>
        </div>

        <div class="med-banner-progresso" id="med-banner-progresso" hidden>
            <div class="med-banner-progresso-topo">
                <i class="fas fa-arrows-rotate"></i>
                <span id="med-banner-fase">Iniciando...</span>
                <span class="med-banner-progresso-contagem" id="med-banner-contagem"></span>
            </div>
            <div class="med-banner-progresso-barra-trilho"><div class="med-banner-progresso-barra-preenchida" id="med-banner-barra"></div></div>
        </div>

        <div class="med-toast-concluido" id="med-toast-concluido">
            <i class="fas fa-circle-check"></i>
            <span id="med-toast-texto"></span>
        </div>

        <div class="med-banner-erro" id="med-banner-erro" hidden>
            <i class="fas fa-triangle-exclamation"></i>
            <span class="med-banner-erro-texto" id="med-banner-erro-texto"></span>
            <button type="button" class="med-banner-erro-fechar" id="med-banner-erro-fechar" title="Fechar aviso">
                <i class="fas fa-xmark"></i>
            </button>
        </div>

        <div class="dp-abas-nav">""",
)

substituir(
    'devolucoes/templates/devolucoes/mediacoes_ml.html',
    """        <div class="dp-tab-panel{% if aba_ativa == 'abertas' %} dp-tab-panel--ativa{% endif %}" data-painel="abertas">
            <div class="med-lista-scroll">
                {% for item in mediacoes_abertas %}
                <a href="{% if item.tipo == 'devolucao' %}{% url 'mediacoes_ml_devolucao' item.id %}{% else %}{% url 'mediacoes_ml_avulsa' item.id %}{% endif %}"
                   class="med-item{% if tipo_selecionado == item.tipo and mediacao_selecionada.id == item.id %} med-item--selecionada{% endif %}"
                   data-busca="{{ item.nome_cliente|lower }} {{ item.numero_pedido|lower }} {{ item.nome_produto|lower }}">
                    <span class="med-item-foto"><i class="fas fa-comments"></i></span>
                    <span class="med-item-corpo">
                        <span class="med-item-topo">
                            <span class="med-item-produto">{{ item.nome_produto|default:"Produto não informado" }}</span>
                        </span>
                        <span class="med-item-rodape">
                            <span class="med-item-pedido">Pedido {{ item.numero_pedido }} — {{ item.nome_cliente|default:"cliente não informado" }}</span>
                            <span class="dp-badge dp-badge--mediacao-aberta">Aberta</span>
                        </span>
                    </span>
                </a>
                {% empty %}
                <div class="med-lista-vazia">Nenhuma mediação aberta no momento.</div>
                {% endfor %}
                <div class="med-lista-vazia-busca">Nenhuma mediação aberta encontrada com esse termo.</div>
            </div>
        </div>""",
    """        <div class="dp-tab-panel{% if aba_ativa == 'abertas' %} dp-tab-panel--ativa{% endif %}" data-painel="abertas">
            <div class="med-lista-scroll">

                <div class="med-grupo" data-grupo="encontrados" data-recolhido="true">
                    <button type="button" class="med-grupo-cabecalho med-grupo-cabecalho--toggle" data-toggle-grupo="encontrados" aria-expanded="false">
                        <span class="med-grupo-cabecalho-esquerda">
                            <i class="fas fa-chevron-right med-grupo-chevron"></i>
                            <span class="med-grupo-titulo">Encontrados pelo sistema</span>
                            <span class="med-grupo-contagem-resumo">{{ contagem_encontrados.todas }}</span>
                        </span>
                        <span class="med-grupo-subtitulo">varredura de 6 meses — ainda não vinculados</span>
                    </button>
                    <div class="med-grupo-conteudo" data-conteudo="encontrados" hidden>
                        <div class="dp-filtro-secundario" data-chips="encontrados">
                            <button type="button" class="dp-chip-filtro dp-chip-filtro--ativa" data-filtro="todas">Todas ({{ contagem_encontrados.todas }})</button>
                            <button type="button" class="dp-chip-filtro" data-filtro="reclamacao">Só reclamação ({{ contagem_encontrados.reclamacao }})</button>
                            <button type="button" class="dp-chip-filtro" data-filtro="mediacao">+ Mediação ({{ contagem_encontrados.mediacao }})</button>
                            <button type="button" class="dp-chip-filtro" data-filtro="devolucao">+ Devolução ({{ contagem_encontrados.devolucao }})</button>
                            <button type="button" class="dp-chip-filtro" data-filtro="mediacao-devolucao">+ Mediação + Devolução ({{ contagem_encontrados.mediacao_devolucao }})</button>
                        </div>
                        <div class="med-lista-scroll" data-lista="encontrados">
                            {% for item in encontrados %}
                            <div class="med-enc-item" data-combinacao="{{ item.categoria_slug }}">
                                <span class="med-item-foto"><i class="fas fa-comments"></i></span>
                                <span class="med-item-corpo">
                                    <span class="med-item-topo">
                                        <span class="med-item-produto">Pedido {{ item.numero_pedido }}</span>
                                    </span>
                                    <span class="med-item-rodape">
                                        <span class="med-item-pedido">Claim {{ item.claim_id }} · cliente ainda não identificado</span>
                                        {% if item.categoria_slug == 'mediacao' %}
                                        <span class="dp-badge dp-badge--categ-mediacao">Mediação</span>
                                        {% elif item.categoria_slug == 'devolucao' %}
                                        <span class="dp-badge dp-badge--categ-devolucao">Devolução</span>
                                        {% elif item.categoria_slug == 'mediacao-devolucao' %}
                                        <span class="dp-badge dp-badge--categ-mediacao">Mediação</span>
                                        <span class="dp-badge dp-badge--categ-devolucao">Devolução</span>
                                        {% else %}
                                        <span class="dp-badge dp-badge--categ-reclamacao">Só reclamação</span>
                                        {% endif %}
                                    </span>
                                </span>
                                <form method="post" action="{% url 'acompanhar_claim' item.claim_id %}" class="dp-form-inline">
                                    {% csrf_token %}
                                    <button type="submit" class="med-item-acao" title="Acompanhar este item">
                                        <i class="fas fa-star"></i>
                                    </button>
                                </form>
                            </div>
                            {% empty %}
                            <div class="med-lista-vazia">Nenhum resultado de varredura ainda — clique em "Fazer varredura completa" acima.</div>
                            {% endfor %}
                        </div>
                    </div>
                </div>

                <div class="med-grupo" data-grupo="acompanhamento">
                    <div class="med-grupo-cabecalho">
                        <span class="med-grupo-titulo med-grupo-titulo--acompanhamento">Em acompanhamento</span>
                        <span class="med-grupo-contagem-resumo">{{ contagem_acompanhamento.todas }}</span>
                    </div>
                    <div class="dp-filtro-secundario" data-chips="acompanhamento">
                        <button type="button" class="dp-chip-filtro dp-chip-filtro--ativa" data-filtro="todas">Todas ({{ contagem_acompanhamento.todas }})</button>
                        <button type="button" class="dp-chip-filtro" data-filtro="reclamacao">Só reclamação ({{ contagem_acompanhamento.reclamacao }})</button>
                        <button type="button" class="dp-chip-filtro" data-filtro="mediacao">+ Mediação ({{ contagem_acompanhamento.mediacao }})</button>
                        <button type="button" class="dp-chip-filtro" data-filtro="devolucao">+ Devolução ({{ contagem_acompanhamento.devolucao }})</button>
                        <button type="button" class="dp-chip-filtro" data-filtro="mediacao-devolucao">+ Mediação + Devolução ({{ contagem_acompanhamento.mediacao_devolucao }})</button>
                    </div>
                    <div class="med-lista-scroll" data-lista="acompanhamento">
                        {% for item in mediacoes_abertas %}
                        <a href="{% if item.tipo == 'devolucao' %}{% url 'mediacoes_ml_devolucao' item.id %}{% else %}{% url 'mediacoes_ml_avulsa' item.id %}{% endif %}"
                           class="med-item{% if tipo_selecionado == item.tipo and mediacao_selecionada.id == item.id %} med-item--selecionada{% endif %}"
                           data-busca="{{ item.nome_cliente|lower }} {{ item.numero_pedido|lower }} {{ item.nome_produto|lower }}"
                           {% if item.categoria_slug %}data-combinacao="{{ item.categoria_slug }}"{% endif %}>
                            <span class="med-item-foto"><i class="fas fa-comments"></i></span>
                            <span class="med-item-corpo">
                                <span class="med-item-topo">
                                    <span class="med-item-produto">{{ item.nome_produto|default:"Produto não informado" }}</span>
                                </span>
                                <span class="med-item-rodape">
                                    <span class="med-item-pedido">Pedido {{ item.numero_pedido }} — {{ item.nome_cliente|default:"cliente não informado" }}</span>
                                    {% if item.categoria_slug == 'mediacao' %}
                                    <span class="dp-badge dp-badge--categ-mediacao">Mediação</span>
                                    {% elif item.categoria_slug == 'devolucao' %}
                                    <span class="dp-badge dp-badge--categ-devolucao">Devolução</span>
                                    {% elif item.categoria_slug == 'mediacao-devolucao' %}
                                    <span class="dp-badge dp-badge--categ-mediacao">Mediação</span>
                                    <span class="dp-badge dp-badge--categ-devolucao">Devolução</span>
                                    {% else %}
                                    <span class="dp-badge dp-badge--mediacao-aberta">Aberta</span>
                                    {% endif %}
                                </span>
                            </span>
                        </a>
                        {% empty %}
                        <div class="med-lista-vazia">Nenhuma mediação aberta no momento.</div>
                        {% endfor %}
                        <div class="med-lista-vazia-busca">Nenhuma mediação aberta encontrada com esse termo.</div>
                    </div>
                </div>

            </div>
        </div>""",
)


print('9/9 -- CSS e JS')

substituir(
    'devolucoes/static/devolucoes/css/layout_mediacoes_ml.css',
    """@media (max-width: 980px) {
    .med-shell {
        grid-template-columns: 1fr;
    }
}""",
    """/* ===== varredura de mediacoes em segundo plano -- linha de botoes,
   banner de progresso, toast de conclusao e banner de erro amigavel
   (decisao de Matheus, 20/09/2026 -- ver vault "Redesenho do Painel de
   Mediacoes") ===== */

.med-linha-varredura {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.med-btn-varredura {
    flex: 1;
    justify-content: center;
}

.med-btn-varredura.rodando i {
    animation: med-girar 0.9s linear infinite;
}

@keyframes med-girar {
    to { transform: rotate(360deg); }
}

.med-banner-progresso {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px 14px;
    background: #fef3c7;
    border: 1px solid #fde3a8;
    border-radius: 8px;
}

.med-banner-progresso[hidden] {
    display: none;
}

.med-banner-progresso-topo {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    font-weight: 700;
    color: #92400e;
}

.med-banner-progresso-topo i {
    animation: med-girar 0.9s linear infinite;
}

.med-banner-progresso-contagem {
    margin-left: auto;
    font-variant-numeric: tabular-nums;
    font-weight: 700;
}

.med-banner-progresso-barra-trilho {
    height: 6px;
    border-radius: 20px;
    background: #fde3a8;
    overflow: hidden;
}

.med-banner-progresso-barra-preenchida {
    height: 100%;
    width: 0%;
    background: var(--cor-alerta);
    border-radius: 20px;
    transition: width .35s ease;
}

.med-toast-concluido {
    font-size: 12px;
    color: var(--cor-positivo);
    display: flex;
    align-items: center;
    gap: 6px;
    opacity: 0;
    height: 0;
    overflow: hidden;
    transition: opacity .3s;
}

.med-toast-concluido.mostrar {
    opacity: 1;
    height: auto;
}

.med-banner-erro {
    display: flex;
    align-items: flex-start;
    gap: 9px;
    padding: 12px 14px;
    background: #fde8e8;
    border: 1px solid #f6b8b8;
    border-radius: 8px;
    color: var(--cor-negativo);
    font-size: 12.5px;
    line-height: 1.45;
}

.med-banner-erro[hidden] {
    display: none;
}

.med-banner-erro-texto {
    flex: 1;
}

.med-banner-erro-fechar {
    flex-shrink: 0;
    background: none;
    border: none;
    color: var(--cor-negativo);
    opacity: .7;
    cursor: pointer;
    padding: 2px;
    border-radius: 4px;
}

.med-banner-erro-fechar:hover {
    opacity: 1;
    background: rgba(220, 53, 69, .12);
}

/* ===== grupos (Encontrados pelo Sistema / Em Acompanhamento) dentro da
   aba "Abertas" ===== */

.med-grupo {
    display: flex;
    flex-direction: column;
    gap: 9px;
}

.med-grupo-cabecalho {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
}

.med-grupo-cabecalho--toggle {
    border: none;
    background: none;
    padding: 5px 6px;
    margin: -5px -6px 0;
    width: calc(100% + 12px);
    font: inherit;
    color: inherit;
    text-align: left;
    cursor: pointer;
    border-radius: 6px;
}

.med-grupo-cabecalho--toggle:hover {
    background: var(--cor-fundo-pagina);
}

.med-grupo-cabecalho-esquerda {
    display: flex;
    align-items: center;
    gap: 7px;
}

.med-grupo-chevron {
    font-size: 11px;
    color: var(--cor-texto-muted);
    transition: transform .18s ease;
}

.med-grupo[data-recolhido="false"] .med-grupo-chevron {
    transform: rotate(90deg);
}

.med-grupo-contagem-resumo {
    background: #eceef1;
    color: var(--cor-texto-muted);
    font-size: 11px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 20px;
    font-variant-numeric: tabular-nums;
}

.med-grupo-titulo {
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .04em;
    color: var(--cor-texto-muted);
}

.med-grupo-titulo--acompanhamento {
    color: var(--cor-primaria-clara);
}

.med-grupo-subtitulo {
    font-size: 11px;
    color: var(--cor-texto-muted);
}

.med-grupo-conteudo {
    display: flex;
    flex-direction: column;
    gap: 9px;
}

.med-grupo-conteudo[hidden] {
    display: none;
}

.med-enc-item {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px;
    border: 1px solid var(--cor-borda);
    border-radius: 8px;
    background: #fff;
}

.med-item-acao {
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    border-radius: 7px;
    border: 1px solid var(--cor-borda);
    background: #fff;
    color: var(--cor-texto-muted);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
}

.med-item-acao:hover {
    border-color: var(--cor-alerta);
    color: var(--cor-alerta);
}

/* ===== badges de categoria -- reaproveita a mesma paleta ja usada por
   dp-badge--mediacao-aberta/--conferido/--mediacao-encerrada, so com
   outro significado aqui ===== */

.dp-badge--categ-mediacao {
    background: #fde8e8;
    color: var(--cor-negativo);
}

.dp-badge--categ-devolucao {
    background: #e7f0fa;
    color: var(--cor-primaria-clara);
}

.dp-badge--categ-reclamacao {
    background: #eceef1;
    color: var(--cor-texto-muted);
}

@media (max-width: 980px) {
    .med-shell {
        grid-template-columns: 1fr;
    }
}""",
)

substituir(
    'devolucoes/static/devolucoes/js/script_mediacoes_ml.js',
    """(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList || !form.classList.contains('dp-form-excluir')) return;

        var botao = form.querySelector('.dp-btn--perigo');
        var numeroPedido = botao ? botao.getAttribute('data-nome') : 'esta mediação';
        if (!window.confirm('Remover a mediação avulsa do pedido ' + numeroPedido + ' desta lista? Essa ação não pode ser desfeita.')) {
            evento.preventDefault();
        }
    });
})();""",
    """(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList || !form.classList.contains('dp-form-excluir')) return;

        var botao = form.querySelector('.dp-btn--perigo');
        var numeroPedido = botao ? botao.getAttribute('data-nome') : 'esta mediação';
        if (!window.confirm('Remover a mediação avulsa do pedido ' + numeroPedido + ' desta lista? Essa ação não pode ser desfeita.')) {
            evento.preventDefault();
        }
    });
})();

// Varredura de mediacoes em segundo plano -- 2 botoes (varredura completa
// e atualizacao dos itens em acompanhamento), banner de progresso com
// poll periodico, toast de conclusao e banner de erro 100% amigavel (sem
// nada tecnico -- a mensagem crua fica so no banco/logs, nunca aqui).
// Decisao de Matheus, 20/09/2026.
(function () {
    var btnVarredura = document.getElementById('btn-varredura-completa');
    var btnAtualizar = document.getElementById('btn-atualizar-acompanhados');
    if (!btnVarredura || !btnAtualizar) return;

    var banner = document.getElementById('med-banner-progresso');
    var bannerFase = document.getElementById('med-banner-fase');
    var bannerContagem = document.getElementById('med-banner-contagem');
    var bannerBarra = document.getElementById('med-banner-barra');
    var toast = document.getElementById('med-toast-concluido');
    var toastTexto = document.getElementById('med-toast-texto');
    var bannerErro = document.getElementById('med-banner-erro');
    var bannerErroTexto = document.getElementById('med-banner-erro-texto');
    var btnFecharErro = document.getElementById('med-banner-erro-fechar');

    var URL_STATUS = '/mediacoes/varredura/status/';
    var URL_INICIAR = '/mediacoes/varredura/iniciar/';
    var URL_ATUALIZAR = '/mediacoes/varredura/atualizar-acompanhados/';

    var ROTULO_POR_TIPO = {
        completa: 'a varredura completa',
        acompanhados: 'a atualização dos itens em acompanhamento',
    };

    var rodandoAntes = false;

    function obterCsrfTokenMediacoes() {
        var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }

    function aplicarEstado(estado) {
        btnVarredura.disabled = estado.rodando;
        btnAtualizar.disabled = estado.rodando;
        btnVarredura.classList.toggle('rodando', estado.rodando);
        btnAtualizar.classList.toggle('rodando', estado.rodando);

        if (estado.rodando) {
            banner.hidden = false;
            bannerFase.textContent = estado.fase_atual || 'Processando...';
            bannerContagem.textContent = estado.total ? (estado.processados + ' de ' + estado.total + ' processados') : '';
            var fracao = estado.total ? Math.min(100, (estado.processados / estado.total) * 100) : 0;
            bannerBarra.style.width = fracao + '%';
        } else {
            banner.hidden = true;
        }

        if (rodandoAntes && !estado.rodando) {
            // * [EXPLICACAO] -> acabou de terminar (transicao true ->
            //   false) -- mostra o desfecho certo. Em vez de tentar
            //   atualizar os cards ao vivo, recarrega a pagina (mais
            //   simples e robusto) -- "a lista atualiza sozinha" fica
            //   resolvido pelo F5 automatico.
            var rotulo = ROTULO_POR_TIPO[estado.tipo_execucao] || 'a atualização';
            if (estado.tem_erro) {
                bannerErroTexto.textContent = 'Não foi possível concluir ' + rotulo + '. Os itens já processados foram salvos normalmente — clique no botão pra tentar de novo.';
                bannerErro.hidden = false;
            } else {
                bannerErro.hidden = true;
                if (estado.itens_nao_confirmados) {
                    toastTexto.textContent = 'Concluído — ' + estado.itens_nao_confirmados + ' item(ns) não puderam ser conferidos, serão tentados na próxima.';
                } else {
                    toastTexto.textContent = 'Concluído — lista atualizada.';
                }
                toast.classList.add('mostrar');
                setTimeout(function () { window.location.reload(); }, 900);
            }
        }
        rodandoAntes = estado.rodando;
    }

    function consultarStatus() {
        fetch(URL_STATUS, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resposta) { return resposta.json(); })
            .then(aplicarEstado)
            .catch(function () {});
    }

    function iniciar(url) {
        bannerErro.hidden = true;
        fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': obterCsrfTokenMediacoes(), 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function () { consultarStatus(); })
            .catch(function () {});
    }

    btnVarredura.addEventListener('click', function () { iniciar(URL_INICIAR); });
    btnAtualizar.addEventListener('click', function () { iniciar(URL_ATUALIZAR); });

    if (btnFecharErro) {
        btnFecharErro.addEventListener('click', function () { bannerErro.hidden = true; });
    }

    consultarStatus();
    setInterval(consultarStatus, 3000);
})();

// Recolher/expandir "Encontrados pelo sistema" (comeca sempre recolhido).
(function () {
    document.querySelectorAll('[data-toggle-grupo]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var nome = btn.getAttribute('data-toggle-grupo');
            var grupo = document.querySelector('.med-grupo[data-grupo="' + nome + '"]');
            var conteudo = document.querySelector('.med-grupo-conteudo[data-conteudo="' + nome + '"]');
            var expandido = grupo.getAttribute('data-recolhido') === 'false';
            grupo.setAttribute('data-recolhido', expandido ? 'true' : 'false');
            conteudo.hidden = expandido;
            btn.setAttribute('aria-expanded', String(!expandido));
        });
    });
})();

// Chips de filtro por categoria (Reclamacao/+Mediacao/+Devolucao/+
// Mediacao+Devolucao) -- independentes por grupo (Encontrados/Em
// Acompanhamento), mesmo padrao validado no mockup aprovado.
(function () {
    document.querySelectorAll('[data-chips]').forEach(function (grupoChips) {
        var nomeGrupo = grupoChips.getAttribute('data-chips');
        var lista = document.querySelector('[data-lista="' + nomeGrupo + '"]');
        if (!lista) return;
        grupoChips.querySelectorAll('.dp-chip-filtro').forEach(function (chip) {
            chip.addEventListener('click', function () {
                grupoChips.querySelectorAll('.dp-chip-filtro').forEach(function (c) { c.classList.remove('dp-chip-filtro--ativa'); });
                chip.classList.add('dp-chip-filtro--ativa');
                var filtro = chip.getAttribute('data-filtro');
                lista.querySelectorAll('.med-item, .med-enc-item').forEach(function (item) {
                    var combinacao = item.getAttribute('data-combinacao');
                    if (!combinacao) return; // sem categoria ainda -- sempre visivel, nunca escondido pelo filtro
                    item.style.display = (filtro === 'todas' || combinacao === filtro) ? '' : 'none';
                });
            });
        });
    });
})();""",
)

print()
print('Tudo aplicado. Proximos passos (voce mesmo, fora deste script):')
print()
print('  1) Migrar as 2 bases:')
print('       python manage.py migrate devolucoes 0020 --database magazine')
print('       python manage.py migrate devolucoes 0020 --database samvale')
print('  2) Reiniciar o servidor (runserver/launcher) e abrir a tela de Mediacoes.')
print('  3) 1a varredura completa ainda nao rodou -- "Encontrados pelo Sistema" comeca vazio ate voce clicar no botao.')