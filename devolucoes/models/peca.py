from django.db import models


class Peca(models.Model):
    nome_generico = models.CharField('Nome genérico', max_length=200)
    nome_tecnico = models.CharField('Nome técnico', max_length=200, blank=True)
    codigo_fabricante = models.CharField('Código do fabricante', max_length=100, unique=True, null=True, blank=True)
    imagem = models.ImageField(upload_to='catalogo_pecas/')

    class Meta:
        ordering = ['nome_generico']

    def __str__(self):
        return self.nome_generico