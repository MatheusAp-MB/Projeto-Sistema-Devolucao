# devolucoes/views.py

# Função Objetivo: views da tela de Nova Devolução (Fase 0 + busca/
# seleção de produto — salva a base da devolução no banco; a
# conferência de peças em si é um Objetivo separado, feita depois pelo
# celular) — views do catálogo de produtos e peças — criar/excluir
# produto e 3 telas próprias e separadas pra ele (Visualizar, só
# leitura; Editar, só os dados do produto; Vincular peças, tela
# dedicada que reaproveita a visão agrupada da Gaveta de Peças pra
# selecionar em massa quais peças ficam vinculadas e com que
# quantidade) — cadastrar/editar/excluir/desvincular peça — cadastro
# isolado de Marca/Grupo Fornecedor via AJAX (chamado de dentro da tela
# de produto) — e a tela própria de gerenciar Marcas e Grupos
# Fornecedores (criar/editar/excluir cada um, direto na lista).

import json
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from .models import (
    Compatibilidade, ConferenciaPeca, Devolucao, FotoConferenciaPeca,
    GrupoFornecedor, Marca, Peca, Produto,
)


def link_callback(uri, rel):
    """Traduz uma URL de /media/ ou /static/ pro caminho real no disco —
    o xhtml2pdf não tem servidor rodando, então não consegue buscar essas
    URLs sozinho na hora de montar o PDF."""
    if uri.startswith(settings.MEDIA_URL):
        return os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ''))
    if uri.startswith(settings.STATIC_URL):
        caminho = finders.find(uri.replace(settings.STATIC_URL, ''))
        return caminho or uri
    return uri


def gerar_relatorio_devolucao(request, devolucao_id):
    """Gera o relatório em PDF de 1 devolução (Objetivo 5/Finalizar) —
    busca tudo direto do banco (produto, peças conferidas); diferente do
    fluxo antigo (gerar_pdf_devolucao, removida aqui), que montava tudo
    na hora via querystring, de antes da devolução ser persistida. Pode
    ser gerado a qualquer momento, mas só faz sentido de verdade depois
    de conferida — por isso o botão que chama essa view
    (devolucoes_pendentes.html) só aparece quando destino_produto já
    está preenchido. request=request no render_to_string é de propósito
    — sem isso o context processor de empresa_ativa_nome (usado no
    cabeçalho do relatório) não roda."""
    devolucao = get_object_or_404(
        Devolucao.objects.select_related('produto__marca'), pk=devolucao_id,
    )
    pecas_conferidas = (
        devolucao.pecas_conferidas
        .select_related('peca__marca')
        .order_by('peca__nome_generico')
    )

    html = render_to_string('devolucoes/relatorio_devolucao_pdf.html', {
        'devolucao': devolucao,
        'pecas_conferidas': pecas_conferidas,
    }, request=request)

    resposta = HttpResponse(content_type='application/pdf')
    resposta['Content-Disposition'] = f'inline; filename="relatorio_devolucao_{devolucao.numero_pedido}.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=resposta, link_callback=link_callback)
    if pisa_status.err:
        return HttpResponse('Erro ao gerar o PDF.', status=500)

    return resposta


def _parse_data_opcional(valor):
    """Converte o valor de um <input type=date> pro DateField — string
    vazia vira None (campo realmente em branco, ex: mediação que nem
    abriu ainda), senão passa a string ISO adiante pro Django parsear
    na hora de salvar."""
    valor = (valor or '').strip()
    return valor or None


def _parse_reembolsado(valor):
    """Converte o <select> de reembolso (3 estados) pro BooleanField
    null=True do model: '' = ainda não sei/mediação em aberto, 'sim'/
    'nao' = já resolvido."""
    if valor == 'sim':
        return True
    if valor == 'nao':
        return False
    return None


def _contexto_nova_devolucao(valores=None, produto_selecionado=None, devolucao=None):
    """Monta o contexto da tela de Nova Devolução (Fase 0 + busca/
    seleção de produto) — usada tanto pro GET simples quanto pra
    re-exibir o formulário com o que a pessoa digitou quando a
    validação falha. 'devolucao' só vem preenchido quando é
    editar_devolucao reaproveitando este mesmo template — é o que o
    template usa pra virar "Editar devolução" (título, texto do botão)
    em vez de "Nova devolução"."""
    if valores is None:
        valores = {
            'nome_plataforma': '', 'tipo_venda': '',
            'numero_pedido': '', 'numero_nota_fiscal': '', 'nome_cliente': '',
            'data_venda': '',
            'data_recebimento_cliente': '', 'data_reclamacao_cliente': '', 'data_recebimento_por_nos': '',
            'data_abertura_mediacao': '', 'data_finalizacao_mediacao': '',
            'reembolsado': '', 'anotacao_mediacao': '',
            'motivo_reclamacao': '',
        }

    return {
        'valores': valores,
        'produto_selecionado': produto_selecionado,
        'devolucao': devolucao,
        'plataforma_choices': Devolucao.PLATAFORMA_CHOICES,
        'tipo_venda_choices': Devolucao.TIPO_VENDA_CHOICES,
        'pagina_ativa': 'nova_devolucao',
    }


def _valores_da_devolucao(devolucao):
    """Serializa uma Devolucao já salva pro dict 'valores' que o
    template de Nova Devolução espera — usado só por editar_devolucao
    (GET), pra pré-preencher o formulário com o que já está salvo."""
    return {
        'nome_plataforma': devolucao.nome_plataforma,
        'tipo_venda': devolucao.tipo_venda,
        'numero_pedido': devolucao.numero_pedido,
        'numero_nota_fiscal': devolucao.numero_nota_fiscal,
        'nome_cliente': devolucao.nome_cliente,
        'data_venda': devolucao.data_venda.isoformat(),
        'data_recebimento_cliente': devolucao.data_recebimento_cliente.isoformat(),
        'data_reclamacao_cliente': devolucao.data_reclamacao_cliente.isoformat(),
        'data_recebimento_por_nos': devolucao.data_recebimento_por_nos.isoformat(),
        'data_abertura_mediacao': devolucao.data_abertura_mediacao.isoformat() if devolucao.data_abertura_mediacao else '',
        'data_finalizacao_mediacao': devolucao.data_finalizacao_mediacao.isoformat() if devolucao.data_finalizacao_mediacao else '',
        'reembolsado': 'sim' if devolucao.reembolsado is True else 'nao' if devolucao.reembolsado is False else '',
        'anotacao_mediacao': devolucao.anotacao_mediacao,
        'motivo_reclamacao': devolucao.motivo_reclamacao,
    }


def nova_devolucao(request):
    """Tela de abertura da devolução — preenchida no PC. Reúne os dados
    da Fase 0 (plataforma, pedido, cliente, datas, mediação, reclamação
    do cliente) mais a busca/seleção do produto (Fases 1-2, via
    buscar_produtos_devolucao). Ao salvar, cria a Devolucao no banco já
    com o produto definido — mas ainda sem destino_produto nem peças
    conferidas, porque essa 2ª parte é feita depois, pelo celular (ver
    devolucoes_pendentes)."""
    if request.method == 'POST':
        valores = {
            'nome_plataforma': request.POST.get('nome_plataforma', '').strip(),
            'tipo_venda': request.POST.get('tipo_venda', '').strip(),
            'numero_pedido': request.POST.get('numero_pedido', '').strip(),
            'numero_nota_fiscal': request.POST.get('numero_nota_fiscal', '').strip(),
            'nome_cliente': request.POST.get('nome_cliente', '').strip(),
            'data_venda': request.POST.get('data_venda', '').strip(),
            'data_recebimento_cliente': request.POST.get('data_recebimento_cliente', '').strip(),
            'data_reclamacao_cliente': request.POST.get('data_reclamacao_cliente', '').strip(),
            'data_recebimento_por_nos': request.POST.get('data_recebimento_por_nos', '').strip(),
            'data_abertura_mediacao': request.POST.get('data_abertura_mediacao', '').strip(),
            'data_finalizacao_mediacao': request.POST.get('data_finalizacao_mediacao', '').strip(),
            'reembolsado': request.POST.get('reembolsado', '').strip(),
            'anotacao_mediacao': request.POST.get('anotacao_mediacao', '').strip(),
            'motivo_reclamacao': request.POST.get('motivo_reclamacao', '').strip(),
        }
        produto_id = request.POST.get('produto_id', '').strip()
        produto = Produto.objects.select_related('marca').filter(pk=produto_id).first() if produto_id else None

        rerenderizar = lambda: render(
            request, 'devolucoes/nova_devolucao.html',
            _contexto_nova_devolucao(valores, produto),
        )

        obrigatorios = [
            ('nome_plataforma', 'Plataforma'), ('tipo_venda', 'Tipo de venda'),
            ('numero_pedido', 'Número do pedido'), ('numero_nota_fiscal', 'Número da nota fiscal'),
            ('nome_cliente', 'Nome do cliente'),
            ('data_venda', 'Data da venda'),
            ('data_recebimento_cliente', 'Data de recebimento pelo cliente'),
            ('data_reclamacao_cliente', 'Data da reclamação'),
            ('data_recebimento_por_nos', 'Data de recebimento por nós'),
            ('motivo_reclamacao', 'Motivo da reclamação'),
        ]
        faltando = [rotulo for campo, rotulo in obrigatorios if not valores[campo]]
        if faltando:
            messages.error(request, f'Preencha: {", ".join(faltando)}.')
            return rerenderizar()

        if not produto:
            messages.error(request, 'Selecione um produto pela busca antes de salvar.')
            return rerenderizar()

        if valores['nome_plataforma'] not in dict(Devolucao.PLATAFORMA_CHOICES):
            messages.error(request, 'Plataforma inválida — selecione uma da lista.')
            return rerenderizar()

        if valores['tipo_venda'] not in dict(Devolucao.TIPO_VENDA_CHOICES):
            messages.error(request, 'Tipo de venda inválido.')
            return rerenderizar()

        if Devolucao.objects.filter(numero_pedido=valores['numero_pedido']).exists():
            messages.error(request, f'Já existe uma devolução registrada pro pedido {valores["numero_pedido"]}.')
            return rerenderizar()

        devolucao = Devolucao.objects.create(
            produto=produto,
            nome_plataforma=valores['nome_plataforma'],
            tipo_venda=valores['tipo_venda'],
            numero_pedido=valores['numero_pedido'],
            numero_nota_fiscal=valores['numero_nota_fiscal'],
            nome_cliente=valores['nome_cliente'],
            data_venda=valores['data_venda'],
            data_recebimento_cliente=valores['data_recebimento_cliente'],
            data_reclamacao_cliente=valores['data_reclamacao_cliente'],
            data_recebimento_por_nos=valores['data_recebimento_por_nos'],
            data_abertura_mediacao=_parse_data_opcional(valores['data_abertura_mediacao']),
            data_finalizacao_mediacao=_parse_data_opcional(valores['data_finalizacao_mediacao']),
            reembolsado=_parse_reembolsado(valores['reembolsado']),
            anotacao_mediacao=valores['anotacao_mediacao'],
            motivo_reclamacao=valores['motivo_reclamacao'],
        )
        messages.success(
            request,
            f'Devolução do pedido {devolucao.numero_pedido} criada — pendente de conferência das peças.',
        )
        return redirect('devolucoes_pendentes')

    return render(request, 'devolucoes/nova_devolucao.html', _contexto_nova_devolucao())


def editar_devolucao(request, devolucao_id):
    """Edição dos dados da Fase 0 de uma devolução já salva (plataforma,
    pedido, cliente, datas, mediação, reclamação do cliente, produto) —
    reaproveita o mesmo template e a mesma validação de nova_devolucao,
    só que atualiza a instância existente em vez de criar uma nova. Não
    mexe na conferência de peças — isso é conferir_devolucao."""
    devolucao = get_object_or_404(Devolucao, pk=devolucao_id)

    if request.method == 'POST':
        valores = {
            'nome_plataforma': request.POST.get('nome_plataforma', '').strip(),
            'tipo_venda': request.POST.get('tipo_venda', '').strip(),
            'numero_pedido': request.POST.get('numero_pedido', '').strip(),
            'numero_nota_fiscal': request.POST.get('numero_nota_fiscal', '').strip(),
            'nome_cliente': request.POST.get('nome_cliente', '').strip(),
            'data_venda': request.POST.get('data_venda', '').strip(),
            'data_recebimento_cliente': request.POST.get('data_recebimento_cliente', '').strip(),
            'data_reclamacao_cliente': request.POST.get('data_reclamacao_cliente', '').strip(),
            'data_recebimento_por_nos': request.POST.get('data_recebimento_por_nos', '').strip(),
            'data_abertura_mediacao': request.POST.get('data_abertura_mediacao', '').strip(),
            'data_finalizacao_mediacao': request.POST.get('data_finalizacao_mediacao', '').strip(),
            'reembolsado': request.POST.get('reembolsado', '').strip(),
            'anotacao_mediacao': request.POST.get('anotacao_mediacao', '').strip(),
            'motivo_reclamacao': request.POST.get('motivo_reclamacao', '').strip(),
        }
        produto_id = request.POST.get('produto_id', '').strip()
        produto = Produto.objects.select_related('marca').filter(pk=produto_id).first() if produto_id else None

        rerenderizar = lambda: render(
            request, 'devolucoes/nova_devolucao.html',
            _contexto_nova_devolucao(valores, produto, devolucao),
        )

        obrigatorios = [
            ('nome_plataforma', 'Plataforma'), ('tipo_venda', 'Tipo de venda'),
            ('numero_pedido', 'Número do pedido'), ('numero_nota_fiscal', 'Número da nota fiscal'),
            ('nome_cliente', 'Nome do cliente'),
            ('data_venda', 'Data da venda'),
            ('data_recebimento_cliente', 'Data de recebimento pelo cliente'),
            ('data_reclamacao_cliente', 'Data da reclamação'),
            ('data_recebimento_por_nos', 'Data de recebimento por nós'),
            ('motivo_reclamacao', 'Motivo da reclamação'),
        ]
        faltando = [rotulo for campo, rotulo in obrigatorios if not valores[campo]]
        if faltando:
            messages.error(request, f'Preencha: {", ".join(faltando)}.')
            return rerenderizar()

        if not produto:
            messages.error(request, 'Selecione um produto pela busca antes de salvar.')
            return rerenderizar()

        if valores['nome_plataforma'] not in dict(Devolucao.PLATAFORMA_CHOICES):
            messages.error(request, 'Plataforma inválida — selecione uma da lista.')
            return rerenderizar()

        if valores['tipo_venda'] not in dict(Devolucao.TIPO_VENDA_CHOICES):
            messages.error(request, 'Tipo de venda inválido.')
            return rerenderizar()

        if Devolucao.objects.exclude(pk=devolucao.pk).filter(numero_pedido=valores['numero_pedido']).exists():
            messages.error(request, f'Já existe uma devolução registrada pro pedido {valores["numero_pedido"]}.')
            return rerenderizar()

        devolucao.produto = produto
        devolucao.nome_plataforma = valores['nome_plataforma']
        devolucao.tipo_venda = valores['tipo_venda']
        devolucao.numero_pedido = valores['numero_pedido']
        devolucao.numero_nota_fiscal = valores['numero_nota_fiscal']
        devolucao.nome_cliente = valores['nome_cliente']
        devolucao.data_venda = valores['data_venda']
        devolucao.data_recebimento_cliente = valores['data_recebimento_cliente']
        devolucao.data_reclamacao_cliente = valores['data_reclamacao_cliente']
        devolucao.data_recebimento_por_nos = valores['data_recebimento_por_nos']
        devolucao.data_abertura_mediacao = _parse_data_opcional(valores['data_abertura_mediacao'])
        devolucao.data_finalizacao_mediacao = _parse_data_opcional(valores['data_finalizacao_mediacao'])
        devolucao.reembolsado = _parse_reembolsado(valores['reembolsado'])
        devolucao.anotacao_mediacao = valores['anotacao_mediacao']
        devolucao.motivo_reclamacao = valores['motivo_reclamacao']
        devolucao.save()

        messages.success(request, f'Devolução do pedido {devolucao.numero_pedido} atualizada.')
        return redirect('devolucoes_pendentes')

    valores = _valores_da_devolucao(devolucao)
    return render(
        request, 'devolucoes/nova_devolucao.html',
        _contexto_nova_devolucao(valores, devolucao.produto, devolucao),
    )


def excluir_devolucao(request, devolucao_id):
    """Exclui a devolução inteira (e em cascata: peças conferidas e fotos
    dela, se já tiver alguma) — usada tanto pra corrigir um cadastro
    feito por engano quanto por uma devolução de teste."""
    devolucao = get_object_or_404(Devolucao, pk=devolucao_id)

    if request.method == 'POST':
        numero_pedido = devolucao.numero_pedido
        devolucao.delete()
        messages.success(request, f'Devolução do pedido {numero_pedido} excluída.')

    return redirect('devolucoes_pendentes')


def _produto_para_busca(produto):
    return {
        'id': produto.id,
        'nome': produto.nome,
        'codigo_barras': produto.codigo_barras,
        'sku': produto.sku or '',
        'marca_nome': produto.marca.nome,
        'foto_url': produto.foto.url if produto.foto else None,
    }


def buscar_produtos_devolucao(request):
    """Busca de produto pra abrir uma nova devolução — aceita tanto
    digitação livre e robusta (várias palavras, em qualquer ordem,
    batendo em nome/SKU/cód. fabricante/marca — ex: 'pulv 9121
    brudden') quanto a leitura direta de um leitor de código de barras
    no mesmo campo: se o termo digitado bate exatamente com um código
    de barras, esse produto volta sozinho e marcado como match_exato,
    pra tela já selecionar ele sem precisar clicar."""
    termo = request.GET.get('q', '').strip()

    if not termo:
        return JsonResponse({'resultados': [], 'match_exato': False})

    match_exato = Produto.objects.select_related('marca').filter(codigo_barras=termo).first()
    if match_exato:
        return JsonResponse({'resultados': [_produto_para_busca(match_exato)], 'match_exato': True})

    produtos = Produto.objects.select_related('marca')
    for token in termo.split():
        produtos = produtos.filter(
            Q(nome__icontains=token)
            | Q(sku__icontains=token)
            | Q(codigo_fabricante__icontains=token)
            | Q(codigo_barras__icontains=token)
            | Q(marca__nome__icontains=token)
        )

    resultados = [_produto_para_busca(produto) for produto in produtos.distinct()[:8]]
    return JsonResponse({'resultados': resultados, 'match_exato': False})


def devolucoes_pendentes(request):
    """Listagem de TODAS as devoluções — nome ficou de antes da
    conferência existir, quando só listava as pendentes; hoje continua
    trazendo as já conferidas também, com acesso a editar a conferência
    (em caso de erro ao gravar) e a editar/excluir a devolução em si.
    destino_produto vazio é o sinal de 'ainda não conferida' (ver
    comentário em Devolucao.destino_produto no model — mesma filosofia
    de estado derivado usada em ConferenciaPeca.situacao, sem duplicar
    num campo de status à parte) — é o que o template usa pra decidir
    entre mostrar 'Continuar conferência' ou 'Editar conferência'."""
    lista = (
        Devolucao.objects.select_related('produto__marca')
        .order_by('-criado_em')
    )
    contexto = {
        'devolucoes': lista,
        'pagina_ativa': 'devolucoes_pendentes',
    }
    return render(request, 'devolucoes/devolucoes_pendentes.html', contexto)


def _pecas_para_conferencia(devolucao):
    """Monta a lista de peças pra tela de conferência — parte das peças
    ATUALMENTE compatíveis com o produto (Compatibilidade) e sobrepõe
    com o que já foi conferido antes (ConferenciaPeca), se for edição de
    uma conferência já existente. A união com o que já foi conferido é
    de propósito: garante que, ao editar, uma peça que não é mais
    compatível com o produto (cadastro mudou depois) mas já tinha sido
    registrada nessa devolução continue aparecendo — sem sumir dado já
    gravado. quantidade_esperada de uma peça já conferida vem congelada
    dela mesma (ConferenciaPeca), não da Compatibilidade atual — mesma
    ideia documentada no model. 'ja_registrada' é o que o template usa
    pra decidir se pré-marca o toggle Veio/Não veio — uma peça nova
    (nunca conferida) começa sem nenhum dos 2 marcado, pra não sugerir
    uma resposta que ninguém deu ainda. 'fotos' são as fotos de
    evidência já salvas (FotoConferenciaPeca) — uma peça nova não tem
    nenhuma ainda, porque só dá pra anexar foto numa ConferenciaPeca que
    já existe."""
    conferencias_existentes = {
        c.peca_id: c for c in
        devolucao.pecas_conferidas.select_related('peca__marca').prefetch_related('fotos').all()
    }
    compatibilidades = devolucao.produto.compatibilidades.select_related('peca__marca')

    pecas_por_id = {}
    for compat in compatibilidades:
        pecas_por_id[compat.peca_id] = {
            'peca': compat.peca,
            'quantidade_esperada': compat.quantidade_esperada,
            'quantidade_recebida': 0,
            'anotacao': '',
            'ja_registrada': False,
            'fotos': [],
        }
    for peca_id, conferencia in conferencias_existentes.items():
        pecas_por_id[peca_id] = {
            'peca': conferencia.peca,
            'quantidade_esperada': conferencia.quantidade_esperada,
            'quantidade_recebida': conferencia.quantidade_recebida,
            'anotacao': conferencia.anotacao,
            'ja_registrada': True,
            'fotos': list(conferencia.fotos.all()),
    }

    return sorted(pecas_por_id.values(), key=lambda p: p['peca'].nome_generico)


def conferir_devolucao(request, devolucao_id):
    """Tela de conferência de peças — preenchida no celular (Fase 3).
    Reúne as peças a conferir (_pecas_para_conferencia) e deixa marcar
    quantidade recebida + anotação por peça, além do destino final do
    produto e uma observação geral. Serve tanto pra conferir pela 1ª vez
    (destino_produto ainda vazio) quanto pra corrigir uma conferência já
    feita — mesma tela, os dados vêm pré-preenchidos e salvar sobrescreve
    o que já existia (ver 'ja_conferida' no contexto)."""
    devolucao = get_object_or_404(Devolucao.objects.select_related('produto__marca'), pk=devolucao_id)
    ja_conferida = devolucao.destino_produto != ''

    if request.method == 'POST':
        destino_produto = request.POST.get('destino_produto', '').strip()
        observacao_geral = request.POST.get('observacao_geral', '').strip()

        contexto_erro = lambda: render(request, 'devolucoes/conferir_devolucao.html', {
            'devolucao': devolucao,
            'ja_conferida': ja_conferida,
            'pecas': _pecas_para_conferencia(devolucao),
            'destino_choices': Devolucao.DESTINO_CHOICES,
            'pagina_ativa': 'devolucoes_pendentes',
        })

        if destino_produto not in dict(Devolucao.DESTINO_CHOICES):
            messages.error(request, 'Selecione o destino do produto.')
            return contexto_erro()

        compatibilidades = {c.peca_id: c.quantidade_esperada for c in devolucao.produto.compatibilidades.all()}
        conferencias_existentes = {c.peca_id: c for c in devolucao.pecas_conferidas.all()}
        # peça pode vir tanto de uma Compatibilidade atual quanto de uma
        # ConferenciaPeca já existente (peça que não é mais compatível
        # mas já tinha sido registrada antes) — mesma união feita em
        # _pecas_para_conferencia.
        ids_peca = set(compatibilidades.keys()) | set(conferencias_existentes.keys())

        with transaction.atomic():
            for peca_id in ids_peca:
                conferencia_existente = conferencias_existentes.get(peca_id)
                quantidade_esperada = (
                    conferencia_existente.quantidade_esperada if conferencia_existente
                    else compatibilidades[peca_id]
                )

                try:
                    quantidade_recebida = int(request.POST.get(f'quantidade_recebida_{peca_id}', '0'))
                except ValueError:
                    quantidade_recebida = 0
                quantidade_recebida = max(0, min(quantidade_recebida, quantidade_esperada))

                anotacao = request.POST.get(f'anotacao_{peca_id}', '').strip()

                if conferencia_existente:
                    conferencia_existente.quantidade_recebida = quantidade_recebida
                    conferencia_existente.anotacao = anotacao
                    conferencia_existente.save(update_fields=['quantidade_recebida', 'anotacao'])
                    conferencia = conferencia_existente
                else:
                    conferencia = ConferenciaPeca.objects.create(
                        devolucao=devolucao, peca_id=peca_id,
                        quantidade_esperada=quantidade_esperada,
                        quantidade_recebida=quantidade_recebida,
                        anotacao=anotacao,
                    )

                # * [EXPLICAÇÃO] → funciona tanto na 1ª conferência quanto
                #   numa edição — 'conferencia' aponta pro registro certo
                #   nos 2 casos (recém criado ou já existente), então dá
                #   pra anexar foto logo na 1ª vez, sem precisar salvar a
                #   conferência antes pra só depois anexar foto.
                for foto in request.FILES.getlist(f'fotos_{peca_id}'):
                    FotoConferenciaPeca.objects.create(conferencia=conferencia, imagem=foto)

            devolucao.destino_produto = destino_produto
            devolucao.observacao_geral = observacao_geral
            devolucao.save(update_fields=['destino_produto', 'observacao_geral'])

        messages.success(request, f'Conferência do pedido {devolucao.numero_pedido} salva.')
        return redirect('devolucoes_pendentes')

    contexto = {
        'devolucao': devolucao,
        'ja_conferida': ja_conferida,
        'pecas': _pecas_para_conferencia(devolucao),
        'destino_choices': Devolucao.DESTINO_CHOICES,
        'pagina_ativa': 'devolucoes_pendentes',
    }
    return render(request, 'devolucoes/conferir_devolucao.html', contexto)


def excluir_foto_conferencia(request, foto_id):
    """Exclui 1 foto de evidência tirada durante a conferência de uma
    peça (Objetivo 4) — ação isolada, disparada de dentro da própria
    tela de conferência (cada foto já salva tem seu próprio botão/form
    de excluir). Sempre volta pra tela de conferência da devolução dona
    da foto, tenha dado certo ou não (GET nessa URL só redireciona sem
    fazer nada — a exclusão em si é POST-only)."""
    foto = get_object_or_404(
        FotoConferenciaPeca.objects.select_related('conferencia__devolucao'), pk=foto_id,
    )
    devolucao_id = foto.conferencia.devolucao_id

    if request.method == 'POST':
        foto.delete()
        messages.success(request, 'Foto excluída.')

    return redirect('conferir_devolucao', devolucao_id)


def produtos(request):
    """Lista todos os produtos agrupados por Marca/Grupo Fornecedor —
    marca sem grupo vira uma seção própria; marca com grupo fica dentro
    da seção do grupo dela. A busca em si (Nome/SKU/EAN/Cód. Fabricante/
    Marca) é só client-side, feita pelo script_produtos.js."""
    lista_produtos = (
        Produto.objects.select_related('marca__grupo_fornecedor')
        .order_by('marca__nome', 'nome')
    )

    grupos_por_id = {}
    marcas_sem_grupo_por_id = {}

    for produto in lista_produtos:
        marca = produto.marca
        grupo = marca.grupo_fornecedor

        if grupo:
            grupo_entry = grupos_por_id.setdefault(grupo.id, {'grupo': grupo, 'marcas_por_id': {}})
            marca_entry = grupo_entry['marcas_por_id'].setdefault(marca.id, {'marca': marca, 'produtos': []})
        else:
            marca_entry = marcas_sem_grupo_por_id.setdefault(marca.id, {'marca': marca, 'produtos': []})

        marca_entry['produtos'].append(produto)

    grupos = sorted(
        (
            {
                'grupo': g['grupo'],
                'marcas': sorted(g['marcas_por_id'].values(), key=lambda m: m['marca'].nome.lower()),
            }
            for g in grupos_por_id.values()
        ),
        key=lambda g: g['grupo'].nome.lower(),
    )
    marcas_sem_grupo = sorted(marcas_sem_grupo_por_id.values(), key=lambda m: m['marca'].nome.lower())

    contexto = {
        'marcas_sem_grupo': marcas_sem_grupo,
        'grupos': grupos,
        'tem_produtos': bool(grupos_por_id or marcas_sem_grupo_por_id),
        'pagina_ativa': 'produtos',
    }
    return render(request, 'devolucoes/produtos.html', contexto)


def _contexto_form_produto(produto=None, valores=None):
    """Monta o contexto da tela de cadastro/edição de produto — usada
    tanto pra 'Novo produto' (GET simples) quanto pra 'Editar produto'
    (GET com produto já preenchido), e também pra re-exibir o formulário
    com o que a pessoa digitou quando a validação falha. Só os campos do
    produto em si — peça vinculada não aparece mais aqui, isso ficou pra
    visualizar_produto (visualização) e vincular_pecas_produto (a tela
    dedicada de vincular/desvincular)."""
    if valores is None:
        if produto:
            valores = {
                'nome': produto.nome,
                'codigo_barras': produto.codigo_barras,
                'sku': produto.sku or '',
                'codigo_fabricante': produto.codigo_fabricante or '',
                'marca_id': produto.marca_id,
                'marca_nome': produto.marca.nome if produto.marca else '',
            }
        else:
            valores = {
                'nome': '', 'codigo_barras': '', 'sku': '',
                'codigo_fabricante': '', 'marca_id': '', 'marca_nome': '',
            }

    return {
        'produto': produto,
        'valores': valores,
        'marcas_json': _marcas_json(),
        'grupos': GrupoFornecedor.objects.all(),
        'pagina_ativa': 'produtos',
    }

def _criar_marca(nome, grupo_id):
    """Cria (ou reaproveita, se já existir) uma Marca. Usada tanto pelo
    endpoint AJAX da tela de produto quanto pelo formulário comum da
    tela de Marcas e Grupos Fornecedores."""
    nome = nome.strip()
    if not nome:
        return None, 'Nome da marca é obrigatório.'

    grupo = GrupoFornecedor.objects.filter(pk=grupo_id).first() if grupo_id else None
    marca, _ = Marca.objects.get_or_create(nome=nome, defaults={'grupo_fornecedor': grupo})
    return marca, None


def _criar_grupo_fornecedor(nome):
    """Cria (ou reaproveita) um Grupo Fornecedor — mesma ideia de
    _criar_marca, usada nos 2 lugares que cadastram grupo."""
    nome = nome.strip()
    if not nome:
        return None, 'Nome do grupo é obrigatório.'

    grupo, _ = GrupoFornecedor.objects.get_or_create(nome=nome)
    return grupo, None


def _marcas_json():
    """JSON com todas as Marcas cadastradas, pro widget de seletor de
    marca (reaproveitado em Produto e Peça — ver script_marca_widget.js).
    Vai pro template como atributo data-marcas de um elemento HTML; o
    widget nunca lê marca de variável JS global, só do próprio DOM."""
    marcas = Marca.objects.select_related('grupo_fornecedor')
    return json.dumps([
        {
            'id': marca.id,
            'nome': marca.nome,
            'grupo': marca.grupo_fornecedor.nome if marca.grupo_fornecedor else None,
        }
        for marca in marcas
    ])

def _agrupar_pecas_por_marca_grupo(pecas):
    """Agrupa uma lista/queryset de Peca por Grupo Fornecedor/Marca — marca
    sem grupo vira uma seção própria; marca com grupo fica dentro da seção
    do grupo dela. Extraído de dentro de gaveta_pecas() pra também ser
    reaproveitado por vincular_pecas_produto() — as 2 telas mostram a
    mesma visão agrupada do catálogo de peças (a 2ª com um subconjunto
    marcado como já vinculado ao produto em questão). Retorna
    (grupos, marcas_sem_grupo, tem_pecas)."""
    grupos_por_id = {}
    marcas_sem_grupo_por_id = {}

    for peca in pecas:
        marca = peca.marca
        grupo = marca.grupo_fornecedor

        if grupo:
            grupo_entry = grupos_por_id.setdefault(grupo.id, {'grupo': grupo, 'marcas_por_id': {}})
            marca_entry = grupo_entry['marcas_por_id'].setdefault(marca.id, {'marca': marca, 'pecas': []})
        else:
            marca_entry = marcas_sem_grupo_por_id.setdefault(marca.id, {'marca': marca, 'pecas': []})

        marca_entry['pecas'].append(peca)

    grupos = sorted(
        (
            {
                'grupo': g['grupo'],
                'marcas': sorted(g['marcas_por_id'].values(), key=lambda m: m['marca'].nome.lower()),
            }
            for g in grupos_por_id.values()
        ),
        key=lambda g: g['grupo'].nome.lower(),
    )
    marcas_sem_grupo = sorted(marcas_sem_grupo_por_id.values(), key=lambda m: m['marca'].nome.lower())

    return grupos, marcas_sem_grupo, bool(grupos_por_id or marcas_sem_grupo_por_id)


def cadastrar_grupo_fornecedor(request):
    """Endpoint AJAX (JSON) — chamado de dentro da tela de produto."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    grupo, erro = _criar_grupo_fornecedor(request.POST.get('nome', ''))
    if erro:
        return JsonResponse({'erro': erro}, status=400)

    return JsonResponse({'id': grupo.id, 'nome': grupo.nome})


def cadastrar_marca(request):
    """Endpoint AJAX (JSON) — chamado de dentro da tela de produto."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    marca, erro = _criar_marca(request.POST.get('nome', ''), request.POST.get('grupo_fornecedor_id', '').strip())
    if erro:
        return JsonResponse({'erro': erro}, status=400)

    return JsonResponse({
        'id': marca.id,
        'nome': marca.nome,
        'grupo': {'id': marca.grupo_fornecedor.id, 'nome': marca.grupo_fornecedor.nome} if marca.grupo_fornecedor else None,
    })


def cadastrar_produto(request):
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        codigo_barras = request.POST.get('codigo_barras', '').strip()
        sku = request.POST.get('sku', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        marca_id = request.POST.get('marca_id', '').strip()
        foto = request.FILES.get('foto')

        valores_digitados = {
            'nome': nome, 'codigo_barras': codigo_barras,
            'sku': sku, 'codigo_fabricante': codigo_fabricante,
            'marca_id': marca_id,
            'marca_nome': Marca.objects.filter(pk=marca_id).values_list('nome', flat=True).first() or '' if marca_id else '',
        }
        rerenderizar = lambda: render(request, 'devolucoes/produto_form.html', _contexto_form_produto(valores=valores_digitados))

        if not (nome and codigo_barras and marca_id):
            messages.error(request, 'Nome, Marca e EAN são obrigatórios.')
            return rerenderizar()

        marca = Marca.objects.filter(pk=marca_id).first()
        if not marca:
            messages.error(request, 'Marca inválida — selecione uma marca da lista.')
            return rerenderizar()

        if Produto.objects.filter(codigo_barras=codigo_barras).exists():
            messages.error(request, f'Já existe um produto cadastrado com o código de barras {codigo_barras}.')
            return rerenderizar()

        if sku and Produto.objects.filter(sku=sku).exists():
            messages.error(request, f'Já existe um produto cadastrado com o SKU {sku}.')
            return rerenderizar()

        if codigo_fabricante and Produto.objects.filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe um produto cadastrado com o código do fabricante {codigo_fabricante}.')
            return rerenderizar()

        produto = Produto.objects.create(
            codigo_barras=codigo_barras, nome=nome, marca=marca,
            sku=sku or None, codigo_fabricante=codigo_fabricante or None, foto=foto,
        )
        messages.success(request, f'Produto "{nome}" cadastrado.')
        return redirect('visualizar_produto', produto_id=produto.id)

    return render(request, 'devolucoes/produto_form.html', _contexto_form_produto())


def visualizar_produto(request, produto_id):
    """Tela de visualização do produto — só leitura. É o "hub" do fluxo:
    mostra os dados do produto e a lista de peças vinculadas, e de lá
    partem as 3 ações irmãs (Editar produto / Vincular peças / Excluir
    produto). Vincular e desvincular peça não acontece mais aqui —
    virou responsabilidade exclusiva de vincular_pecas_produto."""
    produto = get_object_or_404(Produto, pk=produto_id)
    compatibilidades = produto.compatibilidades.select_related('peca__marca').order_by('peca__nome_generico')

    contexto = {
        'produto': produto,
        'compatibilidades': compatibilidades,
        'pagina_ativa': 'produtos',
    }
    return render(request, 'devolucoes/produto_visualizar.html', contexto)


def editar_produto(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        codigo_barras = request.POST.get('codigo_barras', '').strip()
        sku = request.POST.get('sku', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        marca_id = request.POST.get('marca_id', '').strip()
        foto = request.FILES.get('foto')

        valores_digitados = {
            'nome': nome, 'codigo_barras': codigo_barras,
            'sku': sku, 'codigo_fabricante': codigo_fabricante,
            'marca_id': marca_id,
            'marca_nome': Marca.objects.filter(pk=marca_id).values_list('nome', flat=True).first() or '' if marca_id else '',
        }
        rerenderizar = lambda: render(request, 'devolucoes/produto_form.html', _contexto_form_produto(produto, valores_digitados))

        if not (nome and codigo_barras and marca_id):
            messages.error(request, 'Nome, Marca e EAN são obrigatórios.')
            return rerenderizar()

        marca = Marca.objects.filter(pk=marca_id).first()
        if not marca:
            messages.error(request, 'Marca inválida — selecione uma marca da lista.')
            return rerenderizar()

        if Produto.objects.exclude(pk=produto.pk).filter(codigo_barras=codigo_barras).exists():
            messages.error(request, f'Já existe outro produto com o código de barras {codigo_barras}.')
            return rerenderizar()

        if sku and Produto.objects.exclude(pk=produto.pk).filter(sku=sku).exists():
            messages.error(request, f'Já existe outro produto com o SKU {sku}.')
            return rerenderizar()

        if codigo_fabricante and Produto.objects.exclude(pk=produto.pk).filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe outro produto com o código do fabricante {codigo_fabricante}.')
            return rerenderizar()

        produto.marca = marca
        produto.nome = nome
        produto.codigo_barras = codigo_barras
        produto.sku = sku or None
        produto.codigo_fabricante = codigo_fabricante or None
        if foto:
            produto.foto = foto
        produto.save()
        messages.success(request, 'Dados do produto atualizados.')
        return redirect('visualizar_produto', produto_id=produto.id)

    return render(request, 'devolucoes/produto_form.html', _contexto_form_produto(produto))


def excluir_produto(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        nome = produto.nome
        produto.delete()
        messages.success(request, f'Produto "{nome}" excluído.')

    return redirect('produtos')


def buscar_pecas(request, produto_id):
    """[ATENÇÃO] → Não é mais chamada por nenhum fluxo da tela de produto
    (o antigo Modal de Vínculo do lado do produto saiu de cena no
    Objetivo 0). Mantida só porque _modal_vinculo.html — componente
    compartilhado, ainda ativo no lado da peça (Gaveta de Peças,
    abrirComPeca) — referencia essa URL incondicionalmente; removê-la
    quebraria o render da Gaveta. Decisão de manter, não de limpar,
    nesta rodada."""
    termo = request.GET.get('q', '').strip()

    resultados = []
    if len(termo) >= 2:
        pecas = (
            Peca.objects.filter(nome_generico__icontains=termo)
            .exclude(compatibilidades__produto_id=produto_id)
            .prefetch_related('compatibilidades__produto')[:8]
        )

        for peca in pecas:
            resultados.append({
                'id': peca.id,
                'nome': peca.nome_generico,
                'foto_url': peca.imagem.url if peca.imagem else None,
                'usada_em': [c.produto.nome for c in peca.compatibilidades.all()],
            })

    return JsonResponse({'resultados': resultados})


def _ler_quantidade_do_post(request, peca_id):
    """Lê o campo quantidade_<id> do POST de vincular_pecas_produto — cada
    peça da grade tem o seu próprio campo de quantidade, então não dá pra
    usar request.POST.get('quantidade_esperada') fixo como nas telas de
    peça única. Cai pra 1 se vier vazio/inválido (input number no HTML já
    evita isso na prática, isso aqui é só a rede de segurança do
    servidor)."""
    try:
        valor = int(request.POST.get(f'quantidade_{peca_id}', '1'))
    except (TypeError, ValueError):
        valor = 1
    return max(1, valor)


def vincular_pecas_produto(request, produto_id):
    """Tela dedicada de vincular/desvincular peças de um produto —
    substitui o antigo Modal de Vínculo do lado do produto (Objetivo 0).
    Reaproveita a mesma visão agrupada por Grupo Fornecedor/Marca da
    Gaveta de Peças (_agrupar_pecas_por_marca_grupo), mas aqui cada peça
    vem marcada com ja_vinculada/quantidade_vinculada — o card já nasce
    marcado (checkbox) se a peça já é compatível com este produto.

    É um formulário clássico só, sem AJAX: marcar uma peça nova = vincular,
    desmarcar uma já vinculada = desvincular, mudar o número da quantidade
    = atualiza. Um "Salvar vínculos" só aplica a diferença toda de uma vez,
    dentro de uma transação — funciona inteiro mesmo com JS desligado (a
    busca/filtro da tela é que são só enfeite client-side)."""
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        ids_selecionados = {
            int(valor) for valor in request.POST.getlist('peca_id') if valor.isdigit()
        }
        vinculos_atuais = {c.peca_id: c for c in produto.compatibilidades.all()}
        ids_atuais = set(vinculos_atuais.keys())

        ids_para_desvincular = ids_atuais - ids_selecionados
        ids_para_vincular = ids_selecionados - ids_atuais
        ids_para_atualizar = ids_selecionados & ids_atuais

        with transaction.atomic():
            if ids_para_desvincular:
                Compatibilidade.objects.filter(produto=produto, peca_id__in=ids_para_desvincular).delete()

            for peca_id in ids_para_vincular:
                Compatibilidade.objects.create(
                    produto=produto, peca_id=peca_id,
                    quantidade_esperada=_ler_quantidade_do_post(request, peca_id),
                )

            for peca_id in ids_para_atualizar:
                nova_quantidade = _ler_quantidade_do_post(request, peca_id)
                compatibilidade = vinculos_atuais[peca_id]
                if compatibilidade.quantidade_esperada != nova_quantidade:
                    compatibilidade.quantidade_esperada = nova_quantidade
                    compatibilidade.save(update_fields=['quantidade_esperada'])

        messages.success(request, 'Vínculos de peças atualizados.')
        return redirect('visualizar_produto', produto_id=produto.id)

    vinculos = {c.peca_id: c.quantidade_esperada for c in produto.compatibilidades.all()}
    pecas = Peca.objects.select_related('marca__grupo_fornecedor').order_by('nome_generico')
    for peca in pecas:
        peca.ja_vinculada = peca.id in vinculos
        peca.quantidade_vinculada = vinculos.get(peca.id, 1)

    pecas_grupos, pecas_marcas_sem_grupo, tem_pecas = _agrupar_pecas_por_marca_grupo(pecas)

    contexto = {
        'produto': produto,
        'pecas_grupos': pecas_grupos,
        'pecas_marcas_sem_grupo': pecas_marcas_sem_grupo,
        'tem_pecas': tem_pecas,
        'qtd_vinculada_inicial': len(vinculos),
        'marcas': Marca.objects.all(),
        'pagina_ativa': 'produtos',
    }
    return render(request, 'devolucoes/produto_vincular_pecas.html', contexto)


def cadastrar_peca_avulsa(request):
    if request.method == 'POST':
        nome_generico = request.POST.get('nome', '').strip()
        nome_tecnico = request.POST.get('nome_tecnico', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        marca_id = request.POST.get('marca_id', '').strip()
        imagem = request.FILES.get('imagem')

        if not nome_generico:
            messages.error(request, 'Nome da peça é obrigatório.')
            return redirect('gaveta_pecas')

        if not imagem:
            messages.error(request, 'Foto da peça é obrigatória.')
            return redirect('gaveta_pecas')

        if not marca_id:
            messages.error(request, 'Marca é obrigatória — selecione uma marca da lista.')
            return redirect('gaveta_pecas')

        marca = Marca.objects.filter(pk=marca_id).first()
        if not marca:
            messages.error(request, 'Marca inválida — selecione uma marca da lista.')
            return redirect('gaveta_pecas')

        if codigo_fabricante and Peca.objects.filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe uma peça cadastrada com o código do fabricante {codigo_fabricante}.')
            return redirect('gaveta_pecas')

        Peca.objects.create(
            nome_generico=nome_generico,
            nome_tecnico=nome_tecnico or '',
            codigo_fabricante=codigo_fabricante or None,
            marca=marca,
            imagem=imagem,
        )
        messages.success(request, f'Peça "{nome_generico}" cadastrada — ainda sem produto vinculado. Vincule ela depois pela busca dentro de um produto.')

    return redirect('gaveta_pecas')


def desvincular_peca(request, compatibilidade_id):
    """Desfaz o vínculo peça-produto — usado pelo card expandido da Gaveta
    de Peças (POST via AJAX, com resposta em JSON, pra atualizar o card na
    hora). Do lado do produto, desvincular virou responsabilidade
    exclusiva de vincular_pecas_produto (desmarcar o checkbox da peça) —
    esta view não é mais chamada de lá, então o fallback sem JS volta pra
    Gaveta de Peças, de onde o form realmente vem."""
    compatibilidade = get_object_or_404(Compatibilidade, pk=compatibilidade_id)
    produto_id = compatibilidade.produto_id

    if request.method == 'POST':
        eh_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        nome_peca = compatibilidade.peca.nome_generico
        peca_id = compatibilidade.peca_id
        compatibilidade.delete()

        if eh_ajax:
            return JsonResponse({
                'peca_id': peca_id,
                'produto_id': produto_id,
                'qtd_produtos_vinculados': Peca.objects.get(pk=peca_id).compatibilidades.count(),
            })

        messages.success(request, f'"{nome_peca}" desvinculada deste produto.')

    return redirect('gaveta_pecas')


def excluir_peca(request, peca_id):
    """Exclui a peça — reaproveitado tanto pelo card na tela de produto
    (POST clássico, com redirect) quanto pelo card na Gaveta de Peças
    (POST via AJAX, com resposta em JSON, pra sumir da grade sem
    recarregar a página). O fallback não-AJAX volta pra Gaveta de Peças
    — a peça já não pertence mais a uma tela de produto específica."""
    peca = get_object_or_404(Peca, pk=peca_id)

    if request.method == 'POST':
        eh_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        nome = peca.nome_generico
        peca.delete()

        if eh_ajax:
            return JsonResponse({'id': peca_id, 'nome': nome})

        messages.success(request, f'Peça "{nome}" excluída do sistema.')

    return redirect('gaveta_pecas')


def _contexto_form_peca(peca=None, valores=None):
    """Monta o contexto da tela de edição de peça — só 'Editar peça'
    existe por enquanto (cadastro acontece dentro do produto ou na
    tela/painel de peça avulsa, não aqui)."""
    if valores is None:
        valores = {
            'nome': peca.nome_generico,
            'nome_tecnico': peca.nome_tecnico,
            'codigo_fabricante': peca.codigo_fabricante,
            'marca_id': peca.marca_id or '',
            'marca_nome': peca.marca.nome if peca.marca else '',
        }

    return {
        'peca': peca,
        'valores': valores,
        'qtd_produtos_vinculados': peca.compatibilidades.count(),
        'marcas_json': _marcas_json(),
        'grupos': GrupoFornecedor.objects.all(),
        'pagina_ativa': 'gaveta_pecas',
    }

def editar_peca(request, peca_id):
    peca = get_object_or_404(Peca, pk=peca_id)

    if request.method == 'POST':
        nome_generico = request.POST.get('nome', '').strip()
        nome_tecnico = request.POST.get('nome_tecnico', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        marca_id = request.POST.get('marca_id', '').strip()
        imagem = request.FILES.get('imagem')

        valores_digitados = {
            'nome': nome_generico, 'nome_tecnico': nome_tecnico, 'codigo_fabricante': codigo_fabricante,
            'marca_id': marca_id,
            'marca_nome': Marca.objects.filter(pk=marca_id).values_list('nome', flat=True).first() or '' if marca_id else '',
        }
        rerenderizar = lambda: render(request, 'devolucoes/peca_form.html', _contexto_form_peca(peca, valores_digitados))

        if not nome_generico:
            messages.error(request, 'Nome da peça é obrigatório.')
            return rerenderizar()

        if not marca_id:
            messages.error(request, 'Marca é obrigatória — selecione uma marca da lista.')
            return rerenderizar()

        marca = Marca.objects.filter(pk=marca_id).first()
        if not marca:
            messages.error(request, 'Marca inválida — selecione uma marca da lista.')
            return rerenderizar()

        if codigo_fabricante and Peca.objects.exclude(pk=peca.pk).filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe outra peça com o código do fabricante {codigo_fabricante}.')
            return rerenderizar()

        peca.marca = marca
        peca.nome_generico = nome_generico
        peca.nome_tecnico = nome_tecnico
        peca.codigo_fabricante = codigo_fabricante or None
        if imagem:
            peca.imagem = imagem
        peca.save()
        messages.success(request, 'Dados da peça atualizados.')
        return redirect('gaveta_pecas')

    return render(request, 'devolucoes/peca_form.html', _contexto_form_peca(peca))


def gaveta_pecas(request):
    """Tela própria de Peça — objeto autossuficiente, com CRUD completo
    independente de vínculo. A busca/filtro (nome, marca, status) é
    client-side, feita por script_gaveta_pecas.js — mesmo padrão já
    usado em produtos() e marcas_grupos().

    Os cards vêm agrupados por Grupo Fornecedor/Marca — mesma lógica de
    agrupamento de produtos() (marca sem grupo vira seção própria; marca
    com grupo fica dentro da seção do grupo dela), só que aqui cada marca
    virou um carrossel horizontal em vez de uma fileira só. Os nomes das
    chaves de contexto são "pecas_..." pra não colidir com 'grupos' (a
    lista simples de GrupoFornecedor que já ia pro <select> de "novo
    grupo" dentro do Modal de Peça — ver _modal_peca.html)."""
    pecas = (
        Peca.objects.select_related('marca__grupo_fornecedor')
        .prefetch_related('compatibilidades__produto')
        .annotate(qtd_produtos_vinculados=Count('compatibilidades', distinct=True))
        .order_by('nome_generico')
    )

    pecas_grupos, pecas_marcas_sem_grupo, tem_pecas = _agrupar_pecas_por_marca_grupo(pecas)

    contexto = {
        'pecas_grupos': pecas_grupos,
        'pecas_marcas_sem_grupo': pecas_marcas_sem_grupo,
        'tem_pecas': tem_pecas,
        'marcas': Marca.objects.all(),
        'marcas_json': _marcas_json(),
        'grupos': GrupoFornecedor.objects.all(),
        'pagina_ativa': 'gaveta_pecas',
    }
    return render(request, 'devolucoes/gaveta_pecas.html', contexto)


def cadastrar_peca_gaveta(request):
    """Endpoint AJAX (JSON) — cadastro de peça pelo Modal de Peça na
    Gaveta. Toda peça nasce avulsa aqui; vincular a um produto é uma
    ação separada e posterior (Objetivo 2)."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    nome_generico = request.POST.get('nome', '').strip()
    nome_tecnico = request.POST.get('nome_tecnico', '').strip()
    codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
    marca_id = request.POST.get('marca_id', '').strip()
    imagem = request.FILES.get('imagem')

    if not nome_generico:
        return JsonResponse({'erro': 'Nome da peça é obrigatório.', 'campo': 'nome'}, status=400)

    if not imagem:
        return JsonResponse({'erro': 'Foto da peça é obrigatória.', 'campo': 'imagem'}, status=400)

    if not marca_id:
        return JsonResponse({'erro': 'Marca é obrigatória — selecione uma marca da lista.', 'campo': 'marca'}, status=400)

    marca = Marca.objects.filter(pk=marca_id).first()
    if not marca:
        return JsonResponse({'erro': 'Marca inválida — selecione uma marca da lista.', 'campo': 'marca'}, status=400)

    if codigo_fabricante and Peca.objects.filter(codigo_fabricante=codigo_fabricante).exists():
        return JsonResponse({
            'erro': f'Já existe uma peça cadastrada com o código do fabricante {codigo_fabricante}.',
            'campo': 'codigo_fabricante',
        }, status=400)

    peca = Peca.objects.create(
        nome_generico=nome_generico,
        nome_tecnico=nome_tecnico or '',
        codigo_fabricante=codigo_fabricante or None,
        marca=marca,
        imagem=imagem,
    )

    return JsonResponse({
        'id': peca.id,
        'nome': peca.nome_generico,
        'nome_tecnico': peca.nome_tecnico,
        'codigo_fabricante': peca.codigo_fabricante or '',
        'marca_id': peca.marca_id,
        'marca_nome': peca.marca.nome,
        'marca_grupo': peca.marca.grupo_fornecedor.nome if peca.marca.grupo_fornecedor else None,
        'imagem_url': peca.imagem.url if peca.imagem else None,
        'qtd_produtos_vinculados': 0,
    })


def editar_peca_gaveta(request, peca_id):
    """Endpoint AJAX (JSON) — edição de peça pelo Modal de Peça na
    Gaveta. Mesma validação de editar_peca (tela própria antiga), só
    que devolve JSON em vez de re-renderizar a página inteira."""
    peca = get_object_or_404(Peca, pk=peca_id)

    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    nome_generico = request.POST.get('nome', '').strip()
    nome_tecnico = request.POST.get('nome_tecnico', '').strip()
    codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
    marca_id = request.POST.get('marca_id', '').strip()
    imagem = request.FILES.get('imagem')

    if not nome_generico:
        return JsonResponse({'erro': 'Nome da peça é obrigatório.', 'campo': 'nome'}, status=400)

    if not marca_id:
        return JsonResponse({'erro': 'Marca é obrigatória — selecione uma marca da lista.', 'campo': 'marca'}, status=400)

    marca = Marca.objects.filter(pk=marca_id).first()
    if not marca:
        return JsonResponse({'erro': 'Marca inválida — selecione uma marca da lista.', 'campo': 'marca'}, status=400)

    if codigo_fabricante and Peca.objects.exclude(pk=peca.pk).filter(codigo_fabricante=codigo_fabricante).exists():
        return JsonResponse({
            'erro': f'Já existe outra peça com o código do fabricante {codigo_fabricante}.',
            'campo': 'codigo_fabricante',
        }, status=400)

    peca.marca = marca
    peca.nome_generico = nome_generico
    peca.nome_tecnico = nome_tecnico
    peca.codigo_fabricante = codigo_fabricante or None
    if imagem:
        peca.imagem = imagem
    peca.save()

    return JsonResponse({
        'id': peca.id,
        'nome': peca.nome_generico,
        'nome_tecnico': peca.nome_tecnico,
        'codigo_fabricante': peca.codigo_fabricante or '',
        'marca_id': peca.marca_id,
        'marca_nome': peca.marca.nome,
        'marca_grupo': peca.marca.grupo_fornecedor.nome if peca.marca.grupo_fornecedor else None,
        'imagem_url': peca.imagem.url if peca.imagem else None,
        'qtd_produtos_vinculados': peca.compatibilidades.count(),
    })


def vincular_peca_gaveta(request):
    """Endpoint AJAX (JSON) — cria (ou atualiza) o vínculo entre uma
    peça e um produto. Chamado tanto do Modal de Vínculo aberto a
    partir da Gaveta de Peças (peça travada) quanto do aberto a partir
    da página de Produto (produto travado) — é o mesmo componente dos
    dois lados.

    Se o vínculo já existir, não cria duplicado — devolve a quantidade
    atual pro modal mostrar o aviso de duplicidade. Só atualiza de
    fato quando o pedido chega com confirmar_atualizacao=1 (segunda
    chamada, depois que a pessoa confirma no modal)."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    peca_id = request.POST.get('peca_id', '').strip()
    produto_id = request.POST.get('produto_id', '').strip()
    confirmar_atualizacao = request.POST.get('confirmar_atualizacao') == '1'

    try:
        quantidade_esperada = int(request.POST.get('quantidade_esperada') or '0')
    except ValueError:
        quantidade_esperada = 0

    if not peca_id or not produto_id:
        return JsonResponse({'erro': 'Selecione a peça e o produto.'}, status=400)

    peca = Peca.objects.filter(pk=peca_id).first()
    if not peca:
        return JsonResponse({'erro': 'Peça inválida.'}, status=400)

    produto = Produto.objects.filter(pk=produto_id).first()
    if not produto:
        return JsonResponse({'erro': 'Produto inválido.'}, status=400)

    if quantidade_esperada < 1:
        return JsonResponse({'erro': 'Quantidade esperada precisa ser 1 ou mais.', 'campo': 'quantidade_esperada'}, status=400)

    existente = Compatibilidade.objects.filter(peca=peca, produto=produto).first()

    if existente and not confirmar_atualizacao:
        return JsonResponse({
            'duplicidade': True,
            'quantidade_atual': existente.quantidade_esperada,
        })

    if existente:
        existente.quantidade_esperada = quantidade_esperada
        existente.save()
        compatibilidade = existente
        criada = False
    else:
        compatibilidade = Compatibilidade.objects.create(
            peca=peca, produto=produto, quantidade_esperada=quantidade_esperada,
        )
        criada = True

    return JsonResponse({
        'id': compatibilidade.id,
        'peca_id': peca.id,
        'peca_nome': peca.nome_generico,
        'produto_id': produto.id,
        'produto_nome': produto.nome,
        'quantidade_esperada': compatibilidade.quantidade_esperada,
        'criada': criada,
    })


def buscar_produtos(request, peca_id):
    """Busca de produtos pra vincular a esta peça — simétrico ao
    buscar_pecas (busca de peças pra vincular a um produto). Exclui
    produtos já vinculados a esta peça, pelo mesmo motivo: quem já
    está vinculado já aparece na lista, a busca é só pra achar algo
    novo pra adicionar."""
    termo = request.GET.get('q', '').strip()

    resultados = []
    if len(termo) >= 2:
        produtos = (
            Produto.objects.filter(nome__icontains=termo)
            .exclude(compatibilidades__peca_id=peca_id)
            .select_related('marca')[:8]
        )

        for produto in produtos:
            resultados.append({
                'id': produto.id,
                'nome': produto.nome,
                'foto_url': produto.foto.url if produto.foto else None,
                'marca_nome': produto.marca.nome,
            })

    return JsonResponse({'resultados': resultados})


def marcas_grupos(request):
    contexto = {
        'marcas': Marca.objects.select_related('grupo_fornecedor'),
        'grupos': GrupoFornecedor.objects.all(),
        'pagina_ativa': 'marcas_grupos',
    }
    return render(request, 'devolucoes/marcas_grupos.html', contexto)


def cadastrar_marca_avulsa(request):
    if request.method == 'POST':
        marca, erro = _criar_marca(request.POST.get('nome', ''), request.POST.get('grupo_fornecedor_id', '').strip())
        if erro:
            messages.error(request, erro)
        else:
            messages.success(request, f'Marca "{marca.nome}" cadastrada.')

    return redirect('marcas_grupos')


def editar_marca(request, marca_id):
    marca = get_object_or_404(Marca, pk=marca_id)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        grupo_id = request.POST.get('grupo_fornecedor_id', '').strip()

        if nome:
            if Marca.objects.exclude(pk=marca.pk).filter(nome=nome).exists():
                messages.error(request, f'Já existe outra marca chamada "{nome}".')
                return redirect('marcas_grupos')

            marca.nome = nome
            marca.grupo_fornecedor = GrupoFornecedor.objects.filter(pk=grupo_id).first() if grupo_id else None
            marca.save()
            messages.success(request, f'Marca "{nome}" atualizada.')

    return redirect('marcas_grupos')


def excluir_marca(request, marca_id):
    marca = get_object_or_404(Marca, pk=marca_id)

    if request.method == 'POST':
        if marca.produtos.exists() or marca.pecas.exists():
            messages.error(request, f'A marca "{marca.nome}" tem produtos ou peças vinculados e não pode ser excluída.')
            return redirect('marcas_grupos')

        marca.delete()
        messages.success(request, f'Marca "{marca.nome}" excluída.')

    return redirect('marcas_grupos')


def cadastrar_grupo_fornecedor_avulso(request):
    if request.method == 'POST':
        grupo, erro = _criar_grupo_fornecedor(request.POST.get('nome', ''))
        if erro:
            messages.error(request, erro)
        else:
            messages.success(request, f'Grupo "{grupo.nome}" cadastrado.')

    return redirect('marcas_grupos')


def editar_grupo_fornecedor(request, grupo_id):
    grupo = get_object_or_404(GrupoFornecedor, pk=grupo_id)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()

        if nome:
            if GrupoFornecedor.objects.exclude(pk=grupo.pk).filter(nome=nome).exists():
                messages.error(request, f'Já existe outro grupo chamado "{nome}".')
                return redirect('marcas_grupos')

            grupo.nome = nome
            grupo.save()
            messages.success(request, f'Grupo "{nome}" atualizado.')

    return redirect('marcas_grupos')


def excluir_grupo_fornecedor(request, grupo_id):
    grupo = get_object_or_404(GrupoFornecedor, pk=grupo_id)

    if request.method == 'POST':
        nome = grupo.nome
        grupo.delete()
        messages.success(request, f'Grupo "{nome}" excluído.')

    return redirect('marcas_grupos')