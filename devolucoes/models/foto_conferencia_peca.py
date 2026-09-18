from django.db import models
from django.utils.text import slugify

from .conferencia_peca import ConferenciaPeca


def caminho_foto_conferencia(instance, filename):
    """Decide onde cada foto de evidência da conferência é salva em disco
    — agrupada por pedido (Devoluções/Pedido_<numero>/Fotos da
    conferencia/) com o nome do arquivo já identificando a peça, ex:
    "parafuso-m4_1.jpg". Isso é o que permite abrir a pasta de uma
    devolução direto no Explorer (MEDIA_ROOT é uma pasta local de
    verdade — ver settings.DADOS_DIR) e achar as fotos organizadas, sem
    precisar passar pelo sistema — pensado pra Ana conseguir pegar as
    fotos pra mediação com o Mercado Livre sem depender de nenhuma tela.

    [ATENÇÃO] → é uma função (não uma string fixa) porque o caminho muda
    por instância, dependendo de qual devolução/peça a foto pertence. O
    número no fim do nome (peca_1, peca_2...) é a posição dessa foto
    entre as fotos JÁ SALVAS daquela peça nessa conferência no momento
    do upload — se uma foto do meio for excluída depois, uma foto nova
    pode repetir um número já usado antes; isso é só cosmético, o
    Storage do Django nunca deixa sobrescrever um arquivo existente
    (sempre acrescenta um sufixo automático se colidir), então nada se
    perde — só o número pode não ficar perfeitamente sequencial depois
    de exclusões.

    Fotos que já existiam antes dessa mudança continuam nos caminhos
    antigos (essa função só vale pra fotos novas, a partir de agora) —
    ver o comando reorganizar_fotos_devolucao pra mover as antigas.
    """
    devolucao = instance.conferencia.devolucao
    peca_slug = slugify(instance.conferencia.peca.nome_generico) or 'peca'
    pedido_slug = slugify(devolucao.numero_pedido) or str(devolucao.pk)
    extensao = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'

    numero = FotoConferenciaPeca.objects.filter(conferencia=instance.conferencia).count() + 1

    return (
        f'Devoluções/Pedido_{pedido_slug}/Fotos da conferencia/'
        f'{peca_slug}_{numero}.{extensao}'
    )


class FotoConferenciaPeca(models.Model):
    # * [EXPLICAÇÃO] → fotos de EVIDÊNCIA tiradas durante a conferência da
    #   devolução (ex: peça com defeito, peça errada) — relação 1-N pois
    #   uma mesma peça pode precisar de mais de uma foto.
    conferencia = models.ForeignKey(ConferenciaPeca, on_delete=models.CASCADE, related_name='fotos')
    imagem = models.ImageField(upload_to=caminho_foto_conferencia)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criada_em']

    def __str__(self):
        return f'Foto de {self.conferencia}'