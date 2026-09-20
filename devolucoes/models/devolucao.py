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

    # * [EXPLICAÇÃO] → aba calculada em status_fluxo (mais abaixo), na
    #   ordem certa de prioridade — nunca guardada num campo à parte,
    #   mesma filosofia de destino_produto/ConferenciaPeca.situacao.
    #   Decisão de Matheus (18/09/2026): o fluxo real do produto é
    #   Aguardando Conferência → Conferidos → (Mediação Aberta →
    #   Mediação Encerrada, só quem precisa) → Impressos — sempre nessa
    #   ordem, sem caminho de volta.
    STATUS_AGUARDANDO_CONFERENCIA = 'aguardando_conferencia'
    STATUS_CONFERIDO = 'conferido'
    STATUS_MEDIACAO_ABERTA = 'mediacao_aberta'
    STATUS_MEDIACAO_ENCERRADA = 'mediacao_encerrada'
    STATUS_IMPRESSO = 'impresso'
    STATUS_CHOICES = [
        (STATUS_AGUARDANDO_CONFERENCIA, 'Aguardando Conferência'),
        (STATUS_CONFERIDO, 'Conferidos'),
        (STATUS_MEDIACAO_ABERTA, 'Mediações Abertas'),
        (STATUS_MEDIACAO_ENCERRADA, 'Mediações Encerradas'),
        (STATUS_IMPRESSO, 'Impressos'),
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

    # * [EXPLICAÇÃO] → 2 campos opcionais (pedido de Ana, via Matheus,
    #   19/09/2026): hoje o valor reembolsado ia parar dentro de
    #   anotacao_mediacao (texto livre) — isso não muda, essa anotação
    #   continua existindo do jeito que é. Esses 2 campos são adicionais,
    #   pra dar uma conta estruturada "preço do produto - valor
    #   reembolsado" em vez de precisar ler o texto livre. preco_produto
    #   não mora em Produto porque MB/SV são revendedores puros — o
    #   preço muda por pedido (desconto, cupom, promoção), não é um
    #   preço fixo do produto em si.
    preco_produto = models.DecimalField(
        'Preço do produto', max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Preço unitário pago pelo cliente (já com desconto) — vem da API do Mercado Livre pela tela Consultar Pedido, ou digitado manualmente.',
    )
    valor_reembolsado = models.DecimalField(
        'Valor reembolsado', max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Valor que a plataforma efetivamente reembolsou ao cliente na mediação — sempre digitado manualmente, não tem de onde puxar pela API.',
    )

    # * [EXPLICAÇÃO] → 2 campos pra tela "Mediações ML" (20/09/2026): o
    #   mesmo par existe em MediacaoAvulsa, com o mesmo nome e mesmo
    #   comportamento, pra tratar devolução-com-mediação-aberta e
    #   mediação avulsa da mesma forma na tela, sem caso especial.
    mediacao_visualizada_em = models.DateTimeField(
        'Mediação visualizada em', null=True, blank=True,
        help_text='Preenchido automaticamente sempre que alguém abre a conversa dessa mediação na tela "Mediações ML" — é o que decide se tem mensagem nova não vista. Não é por usuário (o sistema ainda não tem login), é 1 timestamp só, compartilhado.',
    )
    mediacao_atualizada_em = models.DateTimeField(
        'Mediação atualizada em', null=True, blank=True,
        help_text='Preenchido automaticamente sempre que o botão "Atualizar" (individual ou "Atualizar tudo") busca as mensagens dessa mediação na API do Mercado Livre. O sistema nunca atualiza sozinho — só nesse clique.',
    )

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

    # ===== Sobre a impressão do relatório (Fase 5/8) =====
    relatorio_impresso_em = models.DateTimeField(
        'Relatório impresso em', null=True, blank=True,
        help_text=(
            'Preenchido manualmente pela usuária ao confirmar que já '
            'imprimiu de verdade — de propósito não marca sozinho ao abrir '
            'a tela de impressão, porque às vezes a impressão sai errada e '
            'precisa repetir (decisão de Matheus, 18/09/2026).'
        ),
    )

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f'Devolução de {self.produto.nome} — pedido {self.numero_pedido}'

    @property
    def status_fluxo(self):
        # * [EXPLICAÇÃO] → pergunta sempre pelo passo mais avançado
        #   primeiro, e só desce pro passo anterior se não bateu —
        #   "Impresso" é sempre o destino final, tanto de quem nunca
        #   precisou de mediação (Conferido → Impresso direto) quanto de
        #   quem precisou (→ Mediação Aberta → Mediação Encerrada →
        #   Impresso). Não existe caminho de volta (decisão de Matheus,
        #   18/09/2026): uma vez impresso, é porque foi realmente
        #   finalizado.
        if self.relatorio_impresso_em:
            return self.STATUS_IMPRESSO
        if self.data_finalizacao_mediacao:
            return self.STATUS_MEDIACAO_ENCERRADA
        if self.data_abertura_mediacao:
            return self.STATUS_MEDIACAO_ABERTA
        if self.destino_produto:
            return self.STATUS_CONFERIDO
        return self.STATUS_AGUARDANDO_CONFERENCIA

    @property
    def status_fluxo_display(self):
        return dict(self.STATUS_CHOICES)[self.status_fluxo]

    @property
    def reembolsado_filtro(self):
        # * [EXPLICAÇÃO] → decisão de Matheus (18/09/2026): vazio conta
        #   como "não reembolsado" no filtro das abas Mediações Encerradas
        #   e Impressos — não existe um 3º grupo "não se aplica" na tela.
        return 'sim' if self.reembolsado else 'nao'

    @property
    def diferenca_reembolso(self):
        # * [EXPLICAÇÃO] → só calcula quando os 2 valores estão
        #   preenchidos (pedido de Ana, 19/09/2026: "preço do produto -
        #   valor reembolsado") — com qualquer um dos 2 em branco não
        #   tem conta pra fazer, e "None" aqui vira "não calculado" nos
        #   templates que exibem esse valor.
        if self.preco_produto is None or self.valor_reembolsado is None:
            return None
        return self.preco_produto - self.valor_reembolsado

    @property
    def dias_ate_reclamacao(self):
        # * [EXPLICAÇÃO] → quantos dias corridos entre o recebimento pelo
        #   cliente e a reclamação/solicitação de devolução dele. Os 2
        #   campos são obrigatórios no model, mas o "is None" fica de
        #   guarda mesmo assim — mesma filosofia defensiva já usada em
        #   diferenca_reembolso.
        if self.data_recebimento_cliente is None or self.data_reclamacao_cliente is None:
            return None
        return (self.data_reclamacao_cliente - self.data_recebimento_cliente).days

    @property
    def reclamacao_dentro_do_prazo(self):
        # * [EXPLICAÇÃO] → pedido de Matheus (19/09/2026): deixar visível
        #   se o cliente reclamou dentro de 7 dias corridos a partir do
        #   recebimento — usado pro badge "Dentro/Fora dos 7 dias" no
        #   Visualizar. True/False, ou None quando não dá pra calcular
        #   (ver dias_ate_reclamacao).
        dias = self.dias_ate_reclamacao
        if dias is None:
            return None
        return dias <= 7