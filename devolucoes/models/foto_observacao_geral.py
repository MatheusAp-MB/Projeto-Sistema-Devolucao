from django.db import models
from django.utils.text import slugify

from .devolucao import Devolucao


def caminho_foto_observacao_geral(instance, filename):
    """Mesma lógica de caminho_foto_conferencia (ver foto_conferencia_peca.py)
    e caminho_foto_reclamacao_cliente (ver foto_reclamacao_cliente.py) —
    agrupa por pedido, só que na subpasta "Fotos gerais", pra fotos do
    estado geral do produto (ex: produto recebido já montado) que não são
    de nenhuma peça específica — mesmo assunto de Devolucao.observacao_geral,
    só que em foto."""
    pedido_slug = slugify(instance.devolucao.numero_pedido) or str(instance.devolucao.pk)
    extensao = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'

    numero = FotoObservacaoGeral.objects.filter(devolucao=instance.devolucao).count() + 1

    return f'Devoluções/Pedido_{pedido_slug}/Fotos gerais/foto_{numero}.{extensao}'


class FotoObservacaoGeral(models.Model):
    # * [EXPLICAÇÃO] → fotos do estado GERAL do produto (ex: produto
    #   recebido já montado, sem ser sobre nenhuma peça específica) —
    #   complementa Devolucao.observacao_geral (texto), que antes não
    #   tinha campo de foto nenhum. Diferente de FotoConferenciaPeca (que
    #   é sempre de UMA peça) e de FotoReclamacaoCliente (que é do
    #   CLIENTE, não de nós).
    devolucao = models.ForeignKey(Devolucao, on_delete=models.CASCADE, related_name='fotos_observacao_geral')
    imagem = models.ImageField(upload_to=caminho_foto_observacao_geral)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criada_em']

    def __str__(self):
        return f'Foto geral — {self.devolucao}'

    @property
    def nome_arquivo(self):
        """Só o nome do arquivo (sem o caminho de pastas) — usado na tela
        de visualização da devolução, mesmo padrão de FotoConferenciaPeca."""
        return self.imagem.name.rsplit('/', 1)[-1]  