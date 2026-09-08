from django.db import models

from .conferencia_peca import ConferenciaPeca


class FotoConferenciaPeca(models.Model):
    # * [EXPLICAÇÃO] → fotos de EVIDÊNCIA tiradas durante a conferência da
    #   devolução (ex: peça com defeito, peça errada) — relação 1-N pois
    #   uma mesma peça pode precisar de mais de uma foto.
    conferencia = models.ForeignKey(ConferenciaPeca, on_delete=models.CASCADE, related_name='fotos')
    imagem = models.ImageField(upload_to='conferencia_devolucao/pecas/')
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criada_em']

    def __str__(self):
        return f'Foto de {self.conferencia}'