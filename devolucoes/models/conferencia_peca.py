from django.db import models

from .devolucao import Devolucao
from .peca import Peca


class ConferenciaPeca(models.Model):
    # * [EXPLICAÇÃO] → 1 linha por peça esperada dentro de uma devolução.
    #   quantidade_esperada é uma FOTOGRAFIA do que a Compatibilidade dizia
    #   no momento da devolução — se o cadastro do produto mudar depois
    #   (ex: passou a levar mais peças), essa devolução antiga não pode
    #   mudar junto. Por isso não referenciamos Compatibilidade aqui, só
    #   guardamos o número já resolvido.
    devolucao = models.ForeignKey(Devolucao, on_delete=models.CASCADE, related_name='pecas_conferidas')
    peca = models.ForeignKey(Peca, on_delete=models.PROTECT, related_name='conferencias')

    quantidade_esperada = models.PositiveIntegerField('Quantidade esperada')
    quantidade_recebida = models.PositiveIntegerField('Quantidade recebida', default=0)

    anotacao = models.TextField('Anotação sobre esta peça', blank=True)
    # * [EXPLICAÇÃO] → cobre os 2 modos de anotação combinados com o
    #   usuário: uma observação livre por peça (ex: "veio arranhada") e
    #   também o caso de peça errada/trocada, que também vira texto livre
    #   aqui (ex: "veio o parafuso errado, era pra ser M4 e veio M3").

    class Meta:
        ordering = ['peca__nome_generico']
        unique_together = [('devolucao', 'peca')]

    def __str__(self):
        return f'{self.peca.nome_generico} — {self.devolucao}'

    @property
    def situacao(self):
        # * [EXPLICAÇÃO] → nunca armazenado, sempre calculado a partir das
        #   quantidades — mesma filosofia usada em vincular_pecas_produto
        #   (estado derivado, não guardado em duplicidade).
        if self.quantidade_recebida <= 0:
            return 'nao_recebida'
        if self.quantidade_recebida < self.quantidade_esperada:
            return 'incompleta'
        return 'completa'

    @property
    def deficit(self):
        return max(0, self.quantidade_esperada - self.quantidade_recebida)