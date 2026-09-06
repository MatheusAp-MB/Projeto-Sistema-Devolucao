# devolucoes/management/commands/migrate.py

# Função Objetivo: sobrescreve o comando "migrate" nativo do Django pra
# tornar --database obrigatório. O projeto usa 2 bancos reais (magazine e
# samvale, ver settings.DATABASES) e o "migrate" original, sem --database,
# aplica as migrations SOMENTE no alias "default" — deixando o outro banco
# silenciosamente desatualizado (foi exatamente o que aconteceu em
# 06/09/2026: samvale ficou sem migrar e passou despercebido). Essa
# sobrescrita transforma esse erro de silencioso em impossível: sem
# --database, o comando recusa rodar.
#
# O launcher.py já informa o banco explicitamente nas 2 chamadas que faz
# (call_command("migrate", database=alias, ...)), então essa mudança não
# afeta o fluxo automático do .exe.

from django.core.management.commands.migrate import Command as ComandoMigrateOriginal


class Command(ComandoMigrateOriginal):
    def add_arguments(self, parser):
        super().add_arguments(parser)

        # O argumento --database já existe (herdado do comando original),
        # só precisamos torná-lo obrigatório. argparse permite required=True
        # mesmo em argumentos que começam com "--" — o parser recusa rodar
        # sozinho se a flag não vier, com uma mensagem de erro padrão, antes
        # de qualquer código nosso executar. (parser._actions é um detalhe
        # interno do argparse, mas estável há muito tempo — é o único jeito
        # de "pegar de volta" um argumento já adicionado pelo comando pai.)
        for acao in parser._actions:
            if acao.dest == 'database':
                acao.required = True
                acao.help = (
                    'Obrigatório neste projeto — qual banco migrar: '
                    '"magazine" ou "samvale" (ver settings.DATABASES).'
                )
                break