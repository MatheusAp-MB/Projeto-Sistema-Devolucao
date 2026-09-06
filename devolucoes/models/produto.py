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