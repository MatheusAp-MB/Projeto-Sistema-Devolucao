from django.db import models


class Peca(models.Model):
    nome = models.CharField(max_length=200)
    imagem = models.ImageField(upload_to='catalogo_pecas/', blank=True, null=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome