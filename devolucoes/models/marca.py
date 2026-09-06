from django.db import models

from .grupo_fornecedor import GrupoFornecedor


class Marca(models.Model):
    nome = models.CharField(max_length=100, unique=True)

    # * [EXPLICAÇÃO] → Opcional: nem toda marca faz parte de um grupo.
    #                  SET_NULL — apagar um grupo não pode apagar as
    #                  marcas que apontavam pra ele, só desvincula.
    grupo_fornecedor = models.ForeignKey(
        GrupoFornecedor, on_delete=models.SET_NULL, null=True, blank=True, related_name='marcas',
    )

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome