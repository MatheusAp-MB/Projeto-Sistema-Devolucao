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
    nome_cliente = models.CharField(
        'Nome do cliente', max_length=200, blank=True,
        help_text='Buscado junto com a reclamação na varredura completa (GET /orders/{numero_pedido}) — existe pra mostrar/buscar em "Encontrados pelo Sistema", antes de virar MediacaoAvulsa/Devolucao.',
    )
    nome_produto = models.CharField(
        'Nome do produto', max_length=200, blank=True,
        help_text='Mesmo texto livre do MediacaoAvulsa.nome_produto — buscado junto do nome do cliente.',
    )
    meu_papel = models.CharField(
        'Nosso papel nesta reclamação', max_length=20, null=True, blank=True,
        help_text='"respondent" ou "complainant" — vem de qual busca (players.role) encontrou o claim. '
                   'Pode ficar None quando a resolução falha (API fora do ar na hora, ou o usuário não '
                   'apareceu na lista de "players" do claim) — None aqui significa "não sabemos ainda", '
                   'nunca deve ser tratado como equivalente a "complainant" (comprador). CORREÇÃO '
                   '21/09/2026: antes esse campo não aceitava null, e uma resolução que falhasse tentava '
                   'gravar None mesmo assim — IntegrityError, derrubando a tela de detalhe daquele pedido.',
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
    # * [EXPLICACAO] -> CORREÇÃO 21/09/2026: os 3 campos abaixo são um
    #   resumo denormalizado da mensagem mais recente dentro de
    #   `mensagens` (mesmo formato que calcular_ultima_mensagem sempre
    #   devolveu) -- calculados 1x só nos 3 lugares que gravam `mensagens`
    #   de verdade (executar_varredura_completa, executar_atualizacao_
    #   acompanhados e atualizar_e_formatar_mensagens, varredura_mediacoes
    #   .py), em vez de recalculados do zero (desserializando o JSON
    #   inteiro de `mensagens` e rodando max() nele) TODA VEZ que a tela
    #   de Mediações ML renderiza a barra lateral "Em acompanhamento" --
    #   que é o que a versão anterior fazia, pra CADA item acompanhado,
    #   em TODA requisição (até só pra abrir o detalhe de 1 mediação,
    #   já que a barra lateral sempre renderiza junto). Ler 3 colunas
    #   leves é ordens de magnitude mais barato que reprocessar o
    #   histórico inteiro de mensagens de cada claim aberto a cada
    #   carregamento de página.
    ultima_mensagem_em = models.DateTimeField(
        'Data/hora da última mensagem', null=True, blank=True,
        help_text='Denormalizado de mensagens -- ver comentário acima. Usado pra ordenar "Em acompanhamento" como um chat (mais recente primeiro) e pro indicador de mensagem não lida.',
    )
    ultima_mensagem_de = models.CharField(
        'Quem mandou a última mensagem', max_length=10, null=True, blank=True,
        help_text='"ml" / "voce" / "cliente", ou None quando não dá pra saber com certeza (ex: meu_papel ainda não resolvido) -- mesmo critério de _formatar_mensagens. Denormalizado de mensagens.',
    )
    ultima_mensagem_resumo = models.TextField(
        'Resumo da última mensagem', null=True, blank=True,
        help_text='Versão curta (sem HTML, truncada) do texto da última mensagem, pra pré-visualização de 1 linha na lista. Denormalizado de mensagens.',
    )
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
