"""
Função Objetivo:
Atalho de terminal pra quem já tem o ambiente de desenvolvimento
completo (Python + dependências + manage.py) — ex: eu testando local
antes de liberar a tela de manutenção "Reorganizar fotos" (dentro do
próprio sistema, sem precisar de terminal nenhum).

A lógica de verdade mora em devolucoes/reorganizacao_fotos.py — esse
comando só chama ela e imprime o resultado formatado no terminal.
"""

from django.core.management.base import BaseCommand

from devolucoes.reorganizacao_fotos import reorganizar_fotos_devolucao


class Command(BaseCommand):
    help = 'Reorganiza as fotos de conferência e de reclamação do cliente já existentes em pastas por pedido/peça.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--database', required=True, choices=['magazine', 'samvale'],
            help='Banco a processar.',
        )
        parser.add_argument(
            '--aplicar', action='store_true', default=False,
            help='Move os arquivos de verdade. Sem essa flag, só simula (nada é alterado).',
        )

    def handle(self, *args, **options):
        alias = options['database']
        aplicar = options['aplicar']

        if not aplicar:
            self.stdout.write(self.style.WARNING('Modo simulação — nada será movido. Use --aplicar pra executar de verdade.\n'))

        resultado = reorganizar_fotos_devolucao(alias, aplicar=aplicar)

        for m in resultado['movimentos']:
            if m['situacao'] == 'pulada':
                continue
            if m['situacao'] == 'erro':
                self.stdout.write(self.style.ERROR(f"  [erro] {m['de']} — {m['motivo']}"))
            else:
                self.stdout.write(f"  {m['de']}  ->  {m['para']}")

        self.stdout.write(self.style.SUCCESS(
            f"\nConcluído ({resultado['alias']}): {resultado['movidas']} movida(s), "
            f"{resultado['puladas']} já estava(m) no lugar certo, {len(resultado['erros'])} erro(s)."
        ))

        if not aplicar:
            self.stdout.write('\nIsso foi só simulação — rode de novo com --aplicar pra mover de verdade.')