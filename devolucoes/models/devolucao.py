from django.db import models

from .produto import Produto


class Devolucao(models.Model):
    # * [EXPLICAÇÃO] → foco de hoje é 1 devolução = 1 produto (FK direta).
    #   Devolução com mais de 1 produto (ex: kit "pulverizador + chapéu
    #   napoleão") ficou decidida como melhoria futura — quando chegar a
    #   hora, a mudança é trocar essa FK direta por uma tabela
    #   intermediária (Devolução 1-N Produto), sem precisar remodelar o
    #   resto (peças conferidas continuam apontando pro item certo).
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name='devolucoes')

    TIPO_VENDA_COMUM = 'comum'
    TIPO_VENDA_FULL = 'full'
    TIPO_VENDA_CHOICES = [
        (TIPO_VENDA_COMUM, 'Venda comum'),
        (TIPO_VENDA_FULL, 'Venda FULL'),
    ]

    # * [EXPLICAÇÃO] → o 3º caminho possível (venda comum, produto voltou
    #   em perfeito estado) não precisa de um destino aqui — esse caminho
    #   não gera a dor que esse sistema resolve, então não passa por
    #   devolução registrada. Só os 2 caminhos com problema real (ver nota
    #   no vault "Processo de Devolução de Produtos e os 3 Caminhos
    #   Possíveis").
    DESTINO_TROCA = 'troca'
    DESTINO_USADO = 'usado'
    DESTINO_CHOICES = [
        (DESTINO_TROCA, 'Troca'),
        (DESTINO_USADO, 'Venda como usado'),
    ]

    PLATAFORMA_AMAZON = 'Amazon'
    PLATAFORMA_MAGALU = 'Magalu'
    PLATAFORMA_MAIS_CORREIOS = 'Mais correios'
    PLATAFORMA_MERCADO_LIVRE = 'Mercado Livre'
    PLATAFORMA_RAIA = 'Raia'
    PLATAFORMA_SHOPEE = 'Shopee'
    PLATAFORMA_TIKTOK_SHOP = 'Tiktok Shop'
    PLATAFORMA_CHOICES = [
        (PLATAFORMA_AMAZON, 'Amazon'),
        (PLATAFORMA_MAGALU, 'Magalu'),
        (PLATAFORMA_MAIS_CORREIOS, 'Mais correios'),
        (PLATAFORMA_MERCADO_LIVRE, 'Mercado Livre'),
        (PLATAFORMA_RAIA, 'Raia'),
        (PLATAFORMA_SHOPEE, 'Shopee'),
        (PLATAFORMA_TIKTOK_SHOP, 'Tiktok Shop'),
    ]

    # ===== Sobre a plataforma (Fase 0, preenchido no PC) =====
    nome_plataforma = models.CharField('Plataforma', max_length=100, choices=PLATAFORMA_CHOICES)
    tipo_venda = models.CharField('Tipo de venda', max_length=10, choices=TIPO_VENDA_CHOICES)

    # ===== Sobre o pedido =====
    # * [EXPLICAÇÃO] → 1 pedido gera 1 devolução, mesmo se o pedido tinha
    #   mais de 1 produto — por isso numero_pedido sozinho já é único.
    numero_pedido = models.CharField('Número do pedido', max_length=100, unique=True)
    numero_nota_fiscal = models.CharField('Número da nota fiscal', max_length=100)
    nome_cliente = models.CharField('Nome do cliente', max_length=200)

    # ===== Sobre datas da devolução em si =====
    data_venda = models.DateField('Data da venda')
    data_recebimento_cliente = models.DateField('Recebido pelo cliente em')
    data_reclamacao_cliente = models.DateField('Reclamação/solicitação aberta em')
    data_recebimento_por_nos = models.DateField('Recebido por nós em')

    # ===== Sobre a mediação — nulos de propósito: a mediação pode
    #   continuar em aberto depois da devolução já estar salva, e esses
    #   campos ficam disponíveis pra edição futura (tela de consulta). =====
    data_abertura_mediacao = models.DateField('Mediação aberta em', null=True, blank=True)
    data_finalizacao_mediacao = models.DateField('Mediação finalizada em', null=True, blank=True)
    reembolsado = models.BooleanField('Reembolsado pela plataforma?', null=True, blank=True)
    anotacao_mediacao = models.TextField('Anotações sobre a mediação', blank=True)

    # ===== Sobre a reclamação feita pelo cliente =====
    motivo_reclamacao = models.TextField('Motivo da reclamação do cliente')
    # * [EXPLICAÇÃO] → as imagens do cliente moram em FotoReclamacaoCliente
    #   (relação 1-N) — ver esse model pra mais contexto.

    # ===== Sobre o estado físico real do produto (Fase 3, celular) =====
    observacao_geral = models.TextField(
        'Observação geral do produto', blank=True,
        help_text='Algo que não é sobre nenhuma peça específica — ex: "veio outro produto no lugar".',
    )
    # * [EXPLICAÇÃO] → fica em branco até a conferência (Fase 3, celular)
    #   ser concluída — a devolução é salva em 2 momentos (base no PC,
    #   conferência depois no celular), e só na 2ª parte dá pra saber o
    #   destino real do produto. Uma devolução com destino_produto vazio
    #   é o sinal de "ainda pendente de conferência" (ver
    #   devolucoes_pendentes em views.py) — não existe um campo de
    #   status à parte pra isso.
    destino_produto = models.CharField(
        'Destino do produto', max_length=10, choices=DESTINO_CHOICES, blank=True,
    )
    # * [EXPLICAÇÃO] → o estado de cada peça (recebida/incompleta/não
    #   recebida) mora em ConferenciaPeca (relação 1-N), não aqui. 

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f'Devolução de {self.produto.nome} — pedido {self.numero_pedido}'