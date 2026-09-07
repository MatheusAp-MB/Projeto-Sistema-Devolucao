# devolucoes/views.py

# Função Objetivo: views da tela de nova devolução — busca produto/peças
# reais do catálogo por código de barras e gera o PDF do relatório na
# hora (sem salvar nada no banco) — views do catálogo de produtos e
# peças — criar/consultar/editar/excluir produto (tela própria,
# reaproveitada pros 2 casos), buscar/vincular/cadastrar/desvincular/
# excluir peça — cadastro isolado de Marca/Grupo Fornecedor via AJAX
# (chamado de dentro da tela de produto) — e a tela própria de gerenciar
# Marcas e Grupos Fornecedores (criar/editar/excluir cada um, direto na
# lista).
#
# * [ATENÇÃO] → nova_devolucao ainda usa produto.pecas.all(), que não
#               existe mais depois dessa mudança (peça deixou de
#               pertencer a um produto só). Isso é esperado — combinado
#               deixar quebrado por enquanto, a reforma dessa tela fica
#               pra depois.

import os

from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from xhtml2pdf import pisa

from .models import Compatibilidade, GrupoFornecedor, Marca, Peca, Produto


def formatar_data_br(valor_iso):
    """Converte uma data no formato do input HTML (aaaa-mm-dd) pro
    formato usado no relatório (dd/mm/aaaa). Se vier vazia ou num
    formato inesperado, devolve o valor original sem quebrar o PDF."""
    if not valor_iso:
        return ''
    try:
        return datetime.strptime(valor_iso, '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return valor_iso


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


def gerar_pdf_devolucao(request, dados, produto, pecas):
    pecas_conferidas = []

    for peca in pecas:
        if peca.quantidade_esperada == 1:
            recebido = 1 if request.GET.get(f'peca_recebido_{peca.id}') else 0
        else:
            try:
                recebido = int(request.GET.get(f'peca_recebido_{peca.id}', '0'))
            except ValueError:
                recebido = 0
            recebido = max(0, min(recebido, peca.quantidade_esperada))

        anotacao = request.GET.get(f'peca_anotacao_{peca.id}', '').strip()

        if recebido == 0:
            situacao = 'Não recebida'
        elif recebido < peca.quantidade_esperada:
            situacao = f'Parcial — faltam {peca.quantidade_esperada - recebido}'
        elif anotacao:
            situacao = 'Completa (ver anotação)'
        else:
            situacao = 'Completa'

        pecas_conferidas.append({
            'peca': peca,
            'recebido': recebido,
            'situacao': situacao,
            'anotacao': anotacao,
        })

    dados_pdf = dict(dados)
    dados_pdf['data_recebimento'] = formatar_data_br(dados['data_recebimento'])
    dados_pdf['data_chamado_ml'] = formatar_data_br(dados['data_chamado_ml'])

    html = render_to_string('devolucoes/relatorio_devolucao_pdf.html', {
        'dados': dados_pdf,
        'produto': produto,
        'pecas_conferidas': pecas_conferidas,
    })

    resposta = HttpResponse(content_type='application/pdf')
    resposta['Content-Disposition'] = 'inline; filename="relatorio_devolucao.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=resposta, link_callback=link_callback)
    if pisa_status.err:
        return HttpResponse('Erro ao gerar o PDF.', status=500)

    return resposta


def nova_devolucao(request):
    dados = {
        'nf': '',
        'pedido': '',
        'cliente': '',
        'data_recebimento': '',
        'data_chamado_ml': '',
        'codigo_barras': '',
    }
    produto = None
    pecas = []
    buscou = False

    acao = request.GET.get('acao')

    if acao:
        for campo in dados:
            dados[campo] = request.GET.get(campo, '').strip()
        buscou = True
        if dados['codigo_barras']:
            produto = Produto.objects.filter(codigo_barras=dados['codigo_barras']).first()
            if produto:
                pecas = produto.pecas.all()

        if produto and acao == 'gerar_pdf':
            return gerar_pdf_devolucao(request, dados, produto, pecas)

    contexto = {
        'dados': dados,
        'produto': produto,
        'pecas': pecas,
        'buscou': buscou,
        'pagina_ativa': 'nova_devolucao',
    }
    return render(request, 'devolucoes/nova_devolucao.html', contexto)


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


def catalogo(request):
    codigo_barras = request.GET.get('codigo_barras', '').strip()
    produto = None
    compatibilidades = []

    if codigo_barras:
        produto = Produto.objects.filter(codigo_barras=codigo_barras).first()
        if produto:
            compatibilidades = produto.compatibilidades.select_related('peca').prefetch_related(
                Prefetch(
                    'peca__compatibilidades',
                    queryset=Compatibilidade.objects.exclude(produto=produto).select_related('produto'),
                    to_attr='outras_compatibilidades',
                )
            )

    contexto = {
        'codigo_barras': codigo_barras,
        'produto': produto,
        'compatibilidades': compatibilidades,
        'buscou': bool(codigo_barras),
        'pagina_ativa': 'produtos',
    }
    return render(request, 'devolucoes/catalogo.html', contexto)


def _contexto_form_produto(produto=None, valores=None):
    """Monta o contexto da tela de cadastro/edição de produto — usada
    tanto pra 'Novo produto' (GET simples) quanto pra 'Editar produto'
    (GET com produto já preenchido), e também pra re-exibir o formulário
    com o que a pessoa digitou quando a validação falha."""
    if valores is None:
        if produto:
            valores = {
                'nome': produto.nome,
                'codigo_barras': produto.codigo_barras,
                'sku': produto.sku,
                'codigo_fabricante': produto.codigo_fabricante,
                'marca_id': produto.marca_id or '',
                'marca_nome': produto.marca.nome if produto.marca else '',
            }
        else:
            valores = {
                'nome': '', 'codigo_barras': '', 'sku': '', 'codigo_fabricante': '',
                'marca_id': '', 'marca_nome': '',
            }

    return {
        'produto': produto,
        'valores': valores,
        'marcas': Marca.objects.select_related('grupo_fornecedor'),
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
        return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")

    return render(request, 'devolucoes/produto_form.html', _contexto_form_produto())


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
        return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")

    return render(request, 'devolucoes/produto_form.html', _contexto_form_produto(produto))


def excluir_produto(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        nome = produto.nome
        produto.delete()
        messages.success(request, f'Produto "{nome}" excluído.')

    return redirect('produtos')


def buscar_pecas(request, produto_id):
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


def vincular_peca(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        peca_id = request.POST.get('peca_id')
        quantidade_esperada = int(request.POST.get('quantidade_esperada') or '1')
        peca = get_object_or_404(Peca, pk=peca_id)

        if quantidade_esperada < 1:
            messages.error(request, 'Quantidade esperada precisa ser 1 ou mais.')
            return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")

        _, criada = Compatibilidade.objects.get_or_create(
            peca=peca, produto=produto,
            defaults={'quantidade_esperada': quantidade_esperada},
        )
        if criada:
            messages.success(request, f'"{peca.nome_generico}" vinculada a este produto.')
        else:
            messages.warning(request, f'"{peca.nome_generico}" já estava vinculada a este produto.')

    return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")


def cadastrar_peca(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        nome_generico = request.POST.get('nome', '').strip()
        nome_tecnico = request.POST.get('nome_tecnico', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        quantidade_esperada = int(request.POST.get('quantidade_esperada') or '1')
        imagem = request.FILES.get('imagem')

        if not nome_generico:
            messages.error(request, 'Nome da peça é obrigatório.')
            return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")

        if quantidade_esperada < 1:
            messages.error(request, 'Quantidade esperada precisa ser 1 ou mais.')
            return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")

        if codigo_fabricante and Peca.objects.filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe uma peça cadastrada com o código do fabricante {codigo_fabricante}.')
            return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")

        with transaction.atomic():
            peca = Peca.objects.create(
                nome_generico=nome_generico,
                nome_tecnico=nome_tecnico or '',
                codigo_fabricante=codigo_fabricante or None,
                imagem=imagem,
            )
            Compatibilidade.objects.create(
                peca=peca, produto=produto,
                quantidade_esperada=quantidade_esperada,
            )
        messages.success(request, f'Peça "{nome_generico}" cadastrada e vinculada.')

    return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")


def desvincular_peca(request, compatibilidade_id):
    compatibilidade = get_object_or_404(Compatibilidade, pk=compatibilidade_id)
    codigo_barras = compatibilidade.produto.codigo_barras

    if request.method == 'POST':
        nome_peca = compatibilidade.peca.nome_generico
        compatibilidade.delete()
        messages.success(request, f'"{nome_peca}" desvinculada deste produto.')

    return redirect(f"{reverse('catalogo')}?codigo_barras={codigo_barras}")


def excluir_peca(request, peca_id):
    peca = get_object_or_404(Peca, pk=peca_id)

    if request.method == 'POST':
        codigo_barras = request.POST.get('codigo_barras_origem', '')
        nome = peca.nome_generico
        peca.delete()
        messages.success(request, f'Peça "{nome}" excluída do sistema.')

        if codigo_barras:
            return redirect(f"{reverse('catalogo')}?codigo_barras={codigo_barras}")

    return redirect('produtos')


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
        if marca.produtos.exists():
            messages.error(request, f'A marca "{marca.nome}" tem produtos vinculados e não pode ser excluída.')
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