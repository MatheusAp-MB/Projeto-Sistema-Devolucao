# devolucoes/models.py

# Função Objetivo: modelos de dado permanente do catálogo — Produto e
# Peca guardam o que cada produto DEVERIA ter (nome, foto de referência,
# quantidade esperada). Não guardam nada sobre uma devolução específica
# (isso é responsabilidade de um model futuro, ainda não criado).

from django.db import models


class Produto(models.Model):
    codigo_barras = models.CharField(max_length=50, unique=True)
    nome = models.CharField(max_length=200)
    marca = models.CharField(max_length=100, blank=True)
    foto = models.ImageField(upload_to='catalogo_produtos/', blank=True, null=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Peca(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='pecas')
    nome = models.CharField(max_length=200)
    imagem = models.ImageField(upload_to='catalogo_pecas/', blank=True, null=True)
    quantidade_esperada = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.produto.nome})'