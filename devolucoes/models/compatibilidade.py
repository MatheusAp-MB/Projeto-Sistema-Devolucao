from django.db import models

from .peca import Peca
from .produto import Produto


class Compatibilidade(models.Model):
    # * [EXPLICAÇÃO] → Uma peça pode ter várias dessas (compatível com
    #                  vários produtos), cada uma com sua própria
    #                  quantidade esperada — o mesmo kit de bico pode
    #                  vir em quantidades diferentes em produtos
    #                  diferentes.
    peca = models.ForeignKey(Peca, on_delete=models.CASCADE, related_name='compatibilidades')
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='compatibilidades')
    quantidade_esperada = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [('peca', 'produto')]
        ordering = ['produto__nome', 'peca__nome']

    def __str__(self):
        return f'{self.peca.nome} em {self.produto.nome}'