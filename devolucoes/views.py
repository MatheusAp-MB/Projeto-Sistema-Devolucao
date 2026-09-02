# devolucoes/views.py

# Função Objetivo: views da tela de nova devolução (formulário estático,
# lógica real ainda por vir) e views do catálogo de peças — buscar/criar
# produto por código de barras, e adicionar/remover peça do catálogo.

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import Peca, Produto


def nova_devolucao(request):
    return render(request, 'devolucoes/nova_devolucao.html', {'pagina_ativa': 'nova_devolucao'})


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