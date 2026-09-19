from django.db import models
from django.utils.text import slugify

from .devolucao import Devolucao


def caminho_foto_reclamacao_cliente(instance, filename):
    """Mesma lógica de caminho_foto_conferencia (ver
    foto_conferencia_peca.py) — agrupa por pedido, só que na subpasta
    "Fotos do cliente" em vez de "Fotos da conferencia". Já deixa isso
    pronto mesmo sem nenhuma tela de upload existir ainda pra esse
    modelo — quando essa tela existir, as fotos já caem organizadas."""
    pedido_slug = slugify(instance.devolucao.numero_pedido) or str(instance.devolucao.pk)
    extensao = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'

    numero = FotoReclamacaoCliente.objects.filter(devolucao=instance.devolucao).count() + 1

    return f'Devoluções/Pedido_{pedido_slug}/Fotos do cliente/foto_{numero}.{extensao}'


class FotoReclamacaoCliente(models.Model):
    # * [EXPLICAÇÃO] → fotos que o CLIENTE enviou pra plataforma/suporte
    #   pra provar a reclamação dele — diferente de FotoConferenciaPeca,
    #   que são fotos tiradas por nós na conferência física da devolução.
    devolucao = models.ForeignKey(Devolucao, on_delete=models.CASCADE, related_name='fotos_reclamacao_cliente')
    imagem = models.ImageField(upload_to=caminho_foto_reclamacao_cliente)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criada_em']

    def __str__(self):
        return f'Foto de reclamação — {self.devolucao}'

    @property
    def nome_arquivo(self):
        """Só o nome do arquivo (sem o caminho de pastas) — usado na tela
        de visualização da devolução, mesmo padrão de FotoConferenciaPeca
        e FotoObservacaoGeral."""
        return self.imagem.name.rsplit('/', 1)[-1]