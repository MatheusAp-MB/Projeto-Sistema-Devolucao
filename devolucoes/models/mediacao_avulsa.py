from django.db import models


class MediacaoAvulsa(models.Model):
    # * [EXPLICAÇÃO] → mediação que a Ana quer acompanhar na tela
    #   "Mediações ML" mas que NÃO tem uma Devolucao registrada aqui
    #   (produto que nunca passou pelo fluxo de devolução normal, ou
    #   caso que ela só ficou sabendo pela mensagem do ML). Devolucao
    #   tem campos demais obrigatórios (produto, plataforma, tipo_venda,
    #   3 datas...) pra servir de registro "vazio" — por isso um model
    #   separado e enxuto, só com o que a mediação em si precisa.
    #   Decisão de Matheus (20/09/2026).
    numero_pedido = models.CharField('Número do pedido', max_length=100, unique=True)
    nome_cliente = models.CharField('Nome do cliente', max_length=200, blank=True)
    nome_produto = models.CharField(
        'Nome do produto', max_length=200, blank=True,
        help_text='Texto livre — essa mediação não está vinculada a um Produto cadastrado no catálogo.',
    )

    data_abertura_mediacao = models.DateField('Mediação aberta em', null=True, blank=True)
    data_finalizacao_mediacao = models.DateField('Mediação finalizada em', null=True, blank=True)
    reembolsado = models.BooleanField('Reembolsado pela plataforma?', null=True, blank=True)
    preco_produto = models.DecimalField('Preço do produto', max_digits=10, decimal_places=2, null=True, blank=True)
    valor_reembolsado = models.DecimalField('Valor reembolsado', max_digits=10, decimal_places=2, null=True, blank=True)
    motivo_reclamacao = models.TextField('Motivo da reclamação do cliente', blank=True)
    observacao = models.TextField(
        'Observação', blank=True,
        help_text='Por que essa mediação foi adicionada manualmente, contexto extra, etc.',
    )

    # * [EXPLICAÇÃO] → mesmo par de campos sendo adicionado em Devolucao
    #   nesta mesma leva (ver migration 0018) — de propósito com o MESMO
    #   nome e mesmo comportamento nos 2 models, pra tela de Mediações ML
    #   conseguir tratar uma Devolucao em mediação aberta e uma
    #   MediacaoAvulsa da mesma forma, sem caso especial.
    mediacao_visualizada_em = models.DateTimeField(
        'Mediação visualizada em', null=True, blank=True,
        help_text='Preenchido automaticamente sempre que alguém abre a conversa dessa mediação na tela "Mediações ML" — é o que decide se tem mensagem nova não vista. Não é por usuário (o sistema ainda não tem login), é 1 timestamp só, compartilhado.',
    )
    mediacao_atualizada_em = models.DateTimeField(
        'Mediação atualizada em', null=True, blank=True,
        help_text='Preenchido automaticamente sempre que o botão "Atualizar" (individual ou "Atualizar tudo") busca as mensagens dessa mediação na API do Mercado Livre. O sistema nunca atualiza sozinho — só nesse clique.',
    )
    claim_id = models.CharField(
        'ID da reclamação/mediação no ML', max_length=50, null=True, blank=True,
        help_text='ID da claim no Mercado Livre — preenchido automaticamente quando a busca de mensagens roda pela 1ª vez (ainda não implementada). Usado pra montar os links "Ver reclamação"/"Ver mediação" no site do ML.',
    )

    criado_em = models.DateTimeField(auto_now_add=True)

    STATUS_MEDIACAO_ABERTA = 'mediacao_aberta'
    STATUS_MEDIACAO_ENCERRADA = 'mediacao_encerrada'

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f'Mediação avulsa — pedido {self.numero_pedido}'

    @property
    def status_fluxo(self):
        # * [EXPLICAÇÃO] → espelha Devolucao.status_fluxo (mesmos valores
        #   STATUS_MEDIACAO_ABERTA/ENCERRADA), só que sem os outros passos
        #   do fluxo (aqui é sempre mediação, nunca aguardando/conferido/
        #   impresso) — é o que permite tratar os 2 models igual na tela.
        return self.STATUS_MEDIACAO_ENCERRADA if self.data_finalizacao_mediacao else self.STATUS_MEDIACAO_ABERTA

    @property
    def reembolsado_filtro(self):
        return 'sim' if self.reembolsado else 'nao'

    @property
    def diferenca_reembolso(self):
        if self.preco_produto is None or self.valor_reembolsado is None:
            return None
        return self.preco_produto - self.valor_reembolsado