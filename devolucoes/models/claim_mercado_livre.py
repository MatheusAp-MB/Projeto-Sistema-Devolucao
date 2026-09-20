from django.db import models


class ClaimMercadoLivre(models.Model):
    # * [EXPLICACAO] -> cache generica de toda reclamacao (claim) que
    #   qualquer varredura ja encontrou na API do Mercado Livre -- 1
    #   registro por claim_id, independente de virar "Em Acompanhamento"
    #   ou nao. Existe porque cada chamada de API e "cara" (rate limit +
    #   tempo real, ver cronometragem em cronometrar_refresh_individual.py
    #   e buscar_mediacoes_abertas_recentes.py) -- um dado ja buscado nao
    #   pode ser jogado fora. Roteada pelas 2 bases (MB/SV) via
    #   EmpresaRouter, como todo o resto do app `devolucoes`.
    #   Decisao de Matheus (20/09/2026) -- ver vault "Redesenho do Painel
    #   de Mediacoes -- Encontrados pelo Sistema, Em Acompanhamento e
    #   Varredura em Segundo Plano".
    claim_id = models.CharField('ID da reclamação/mediação no ML', max_length=50, primary_key=True)
    numero_pedido = models.CharField(
        'Número do pedido', max_length=100, db_index=True,
        help_text='Chave de casamento com Devolucao.numero_pedido — não é única aqui (mais de 1 claim pode existir pro mesmo pedido ao longo do tempo).',
    )
    meu_papel = models.CharField(
        'Nosso papel nesta reclamação', max_length=20,
        help_text='"respondent" ou "complainant" — vem de qual busca (players.role) encontrou o claim.',
    )
    dados_brutos = models.JSONField(
        'Dados brutos do claim',
        help_text='Resposta bruta da API (stage, type, date_created, players...) — usada pra recalcular a combinação Reclamação/Mediação/Devolução via categoria_slug().',
    )
    tem_devolucao_fisica = models.BooleanField(
        'Tem devolução física associada?', null=True,
        help_text='True/False confirmado via GET /post-purchase/v2/claims/{id}/returns — None quando não deu pra confirmar (erro que não foi um 404 limpo).',
    )
    mensagens = models.JSONField('Mensagens da reclamação', null=True, blank=True)
    esta_acompanhando = models.BooleanField(
        'Está em acompanhamento?', default=False,
        help_text='Liga automaticamente (casa com Devolucao pelo numero_pedido) ou manualmente ("Acompanhar") — só desliga por ação explícita ("Deixar de acompanhar"), nunca reativa sozinha numa varredura futura.',
    )
    ultima_busca_em = models.DateTimeField('Última busca em')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ultima_busca_em']

    def __str__(self):
        return f'Claim {self.claim_id} — pedido {self.numero_pedido}'
