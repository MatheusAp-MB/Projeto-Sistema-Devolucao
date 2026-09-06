from django.db import models


class GrupoFornecedor(models.Model):
    # * [EXPLICAÇÃO] → Marcas "irmãs" do mesmo fabricante/distribuidor
    #                  (ex: MTX e DENZEL fazem parte do grupo ToolsWorld).
    #                  Existe pensando em módulos futuros que vão precisar
    #                  agrupar produtos por fornecedor, não só por marca.
    nome = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome