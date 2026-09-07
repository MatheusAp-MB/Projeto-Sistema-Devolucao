from django.db import models

from .marca import Marca


class Produto(models.Model):
    codigo_barras = models.CharField(max_length=50, unique=True)
    nome = models.CharField(max_length=200)
    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name='produtos')
    sku = models.CharField('SKU', max_length=100, unique=True, null=True, blank=True)
    codigo_fabricante = models.CharField('Código do fabricante', max_length=100, unique=True, null=True, blank=True)
    foto = models.ImageField(upload_to='catalogo_produtos/', blank=True, null=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome