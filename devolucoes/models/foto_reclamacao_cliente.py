from django.db import models

from .devolucao import Devolucao


class FotoReclamacaoCliente(models.Model):
    # * [EXPLICAÇÃO] → fotos que o CLIENTE enviou pra plataforma/suporte
    #   pra provar a reclamação dele — diferente de FotoConferenciaPeca,
    #   que são fotos tiradas por nós na conferência física da devolução.
    devolucao = models.ForeignKey(Devolucao, on_delete=models.CASCADE, related_name='fotos_reclamacao_cliente')
    imagem = models.ImageField(upload_to='reclamacoes_cliente/')
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criada_em']

    def __str__(self):
        return f'Foto de reclamação — {self.devolucao}'