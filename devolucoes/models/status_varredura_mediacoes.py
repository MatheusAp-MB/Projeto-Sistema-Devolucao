from django.db import models


class StatusVarreduraMediacoes(models.Model):
    # * [EXPLICACAO] -> registro unico (sempre pk=1, nunca historico) do
    #   estado da varredura de mediacoes em segundo plano -- sobrescrito a
    #   cada nova execucao, nunca 1 linha por execucao (decisao de
    #   Matheus, 20/09/2026: nao da pra debugar remotamente no PC da Ana,
    #   entao so importa o estado atual/ultimo). Travado contra clique
    #   duplo via UPDATE...WHERE atomico direto no banco (ver
    #   devolucoes/views.py::iniciar_varredura_mediacoes), nao
    #   select_for_update()/transaction.atomic(). Roteada pelas 2 bases
    #   (MB/SV) via EmpresaRouter, como todo o resto do app `devolucoes`
    #   -- cada empresa tem sua propria linha singleton, migrada e semeada
    #   nas 2 (--database magazine/--database samvale).
    TIPO_COMPLETA = 'completa'
    TIPO_ACOMPANHADOS = 'acompanhados'
    TIPO_EXECUCAO_CHOICES = [
        (TIPO_COMPLETA, 'Varredura completa'),
        (TIPO_ACOMPANHADOS, 'Atualização de itens em acompanhamento'),
    ]

    rodando = models.BooleanField('Rodando agora?', default=False)
    tipo_execucao = models.CharField('Tipo de execução', max_length=20, choices=TIPO_EXECUCAO_CHOICES, null=True, blank=True)
    fase_atual = models.CharField('Fase atual', max_length=100, null=True, blank=True)
    processados = models.IntegerField('Processados', default=0)
    total = models.IntegerField('Total', default=0)
    itens_nao_confirmados = models.IntegerField(
        'Itens não confirmados', default=0,
        help_text='Soma de erros pontuais (devolução física e/ou mensagens) que não pararam o loop — mesmo padrão do script de exploração.',
    )
    iniciado_em = models.DateTimeField('Iniciado em', null=True, blank=True)
    finalizado_em = models.DateTimeField('Finalizado em', null=True, blank=True)
    erro = models.TextField(
        'Erro técnico (debug)', blank=True,
        help_text='Mensagem técnica crua da falha, só pra debug do Matheus (banco/logs) — NUNCA exibida pra Ana. A tela mostra sempre o mesmo texto fixo e amigável quando este campo não está vazio.',
    )

    def __str__(self):
        return f'Status da varredura de mediações (rodando={self.rodando})'
