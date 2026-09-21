from django.db import models


class TravaChatMediacao(models.Model):
    # * [EXPLICACAO] -> registro unico (sempre pk=1, nunca historico) que
    #   trava/libera a caixa de resposta do chat de Mediacoes ML -- mesmo
    #   padrao de StatusVarreduraMediacoes (singleton, sem CRUD). Roteada
    #   pelas 2 bases (MB/SV) via EmpresaRouter, como todo o resto do app
    #   `devolucoes` -- cada empresa tem seu proprio estado, independente
    #   da outra. Comeca sempre liberado=False (travado e o padrao
    #   seguro). So vira True via views.liberar_chat_mediacao, que exige
    #   a senha fixa (SENHA_TRAVA_CHAT_MEDIACAO, sem .env/CRUD) -- qualquer
    #   falha nesse caminho (senha errada, erro de qualquer tipo) mantem
    #   liberado=False. Decisao de Matheus, 21/09/2026: protecao pro envio
    #   de mensagem pro Mercado Livre (ainda nao implementado nesta tela)
    #   nao disparar por acidente quando existir.
    liberado = models.BooleanField('Chat de resposta liberado?', default=False)

    def __str__(self):
        return f'Trava do chat de Mediações ML (liberado={self.liberado})'
