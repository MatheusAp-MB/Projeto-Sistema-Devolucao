from django.db import models

from .devolucao import Devolucao


class PreferenciaTela(models.Model):
    # * [EXPLICAÇÃO] → "Padrão salvo" da tela Devoluções e da tela Análise
    #   (pedido de Matheus, 05/10/2026): guarda como a Ana gosta de ver cada
    #   aba — ordem + filtros — pra tela já abrir assim. Uma linha por aba
    #   (chave = 'aguardando_conferencia', 'conferido', 'mediacao_aberta',
    #   'mediacao_encerrada', 'impresso') mais uma pra tela Análise
    #   ('analise'). Como o sistema ainda não tem login, o padrão é da
    #   EMPRESA, não de uma pessoa — e, como todo model do app
    #   `devolucoes`, a linha mora no banco da empresa ativa (EmpresaRouter):
    #   Magazine e Samvale têm padrões independentes, sem nenhum código
    #   extra aqui.
    #   O conteúdo (`configuracao`) é só o que a tela precisa pra se
    #   remontar (ordem e filtros escolhidos) — nenhuma regra do sistema
    #   depende dele, e apagar uma linha só faz a aba voltar ao padrão
    #   original (o de antes dessa funcionalidade existir).
    CHAVE_ANALISE = 'analise'

    chave = models.CharField('Aba / tela', max_length=40, unique=True)
    configuracao = models.JSONField('Ordem e filtros salvos', default=dict)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Padrão salvo de tela'
        verbose_name_plural = 'Padrões salvos de tela'

    def __str__(self):
        return f'Padrão salvo — {self.chave}'

    @classmethod
    def chaves_validas(cls):
        # * [EXPLICAÇÃO] → as 5 abas do fluxo (mesmos nomes de
        #   Devolucao.STATUS_CHOICES) + a tela Análise. Qualquer outra chave
        #   é recusada pela view — assim ninguém grava lixo por engano.
        return [valor for valor, _ in Devolucao.STATUS_CHOICES] + [cls.CHAVE_ANALISE]
