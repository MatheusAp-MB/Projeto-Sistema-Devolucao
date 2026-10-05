from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Max

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
    quantidade_esperada = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    # * [EXPLICAÇÃO] → pedido de Matheus (05/10/2026): a ordem em que as peças deste produto aparecem
    #                  (Editar conferência, Visualizar devolução, relatório impresso). Quem define é a
    #                  pessoa, arrastando as peças na tela do produto. É uma posição RELATIVA dentro do
    #                  produto (1, 2, 3...): desvincular uma peça deixa um "buraco" que não atrapalha —
    #                  só a ordem entre elas importa. Peça vinculada agora entra no fim (ver save()).
    ordem = models.PositiveIntegerField('Ordem', default=0)

    class Meta:
        unique_together = [('peca', 'produto')]
        ordering = ['produto__nome', 'ordem', 'peca__nome_generico']

    def save(self, *args, **kwargs):
        if self._state.adding and not self.ordem:
            usando = kwargs.get('using') or self._state.db
            gerenciador = Compatibilidade._default_manager
            if usando:
                gerenciador = gerenciador.db_manager(usando)
            maior_ordem = gerenciador.filter(produto_id=self.produto_id).aggregate(maior=Max('ordem'))['maior'] or 0
            self.ordem = maior_ordem + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.peca.nome_generico} em {self.produto.nome}'
