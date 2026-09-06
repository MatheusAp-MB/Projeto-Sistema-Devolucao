# devolucoes/views.py

# Função Objetivo: views da tela de nova devolução — busca produto/peças
# reais do catálogo por código de barras e gera o PDF do relatório na
# hora (sem salvar nada no banco) — views do catálogo de peças —
# buscar/criar produto por código de barras, e adicionar/remover peça.

import os

from datetime import datetime

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from xhtml2pdf import pisa

from .models import Peca, Produto


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
    lista_produtos = Produto.objects.all()
    return render(request, 'devolucoes/produtos.html', {'produtos': lista_produtos, 'pagina_ativa': 'produtos'})


def catalogo(request):
    codigo_barras = request.GET.get('codigo_barras', '').strip()
    produto = None
    pecas = []

    if codigo_barras:
        produto = Produto.objects.filter(codigo_barras=codigo_barras).first()
        if produto:
            pecas = produto.pecas.all()

    contexto = {
        'codigo_barras': codigo_barras,
        'produto': produto,
        'pecas': pecas,
        'buscou': bool(codigo_barras),
        'pagina_ativa': 'produtos',
    }
    return render(request, 'devolucoes/catalogo.html', contexto)


def editar_produto(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        marca = request.POST.get('marca', '').strip()
        codigo_barras = request.POST.get('codigo_barras', '').strip()
        foto = request.FILES.get('foto')

        if nome and codigo_barras:
            produto.nome = nome
            produto.marca = marca
            produto.codigo_barras = codigo_barras
            if foto:
                produto.foto = foto
            produto.save()

    return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")


def cadastrar_produto(request):
    codigo_barras = request.POST.get('codigo_barras', '').strip()

    if request.method == 'POST' and codigo_barras:
        nome = request.POST.get('nome', '').strip()
        marca = request.POST.get('marca', '').strip()
        foto = request.FILES.get('foto')
        if nome:
            Produto.objects.get_or_create(
                codigo_barras=codigo_barras,
                defaults={'nome': nome, 'marca': marca, 'foto': foto},
            )

    return redirect('produtos')


def adicionar_peca(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        quantidade_esperada = request.POST.get('quantidade_esperada') or '1'
        imagem = request.FILES.get('imagem')
        if nome:
            Peca.objects.create(
                produto=produto,
                nome=nome,
                quantidade_esperada=int(quantidade_esperada),
                imagem=imagem,
            )

    return redirect(f"{reverse('catalogo')}?codigo_barras={produto.codigo_barras}")


def remover_peca(request, peca_id):
    peca = get_object_or_404(Peca, pk=peca_id)
    codigo_barras = peca.produto.codigo_barras

    if request.method == 'POST':
        peca.delete()

    return redirect(f"{reverse('catalogo')}?codigo_barras={codigo_barras}")
