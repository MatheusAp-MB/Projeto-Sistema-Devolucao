# devolucoes/management/commands/gerar_exe.py

# Função Objetivo: empacotar o Sistema de Devoluções com PyInstaller (--onedir),
# reunindo num único comando (`python manage.py gerar_exe`) a linha de build que
# hoje precisa ser copiada/colada manualmente — já com todas as flags descobertas
# como necessárias: --add-data pra launcher_recursos/loading.html, templates e
# estáticos do Django, hidden-import do pystray, e os 2 --collect-submodules
# (reportlab.graphics.barcode e django.core.management.commands) encontrados
# em 03/09/2026. Uso exclusivo do dev — nunca roda na máquina da usuária final.

import subprocess

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Empacota o Sistema de Devoluções com PyInstaller (--onedir), com todas as flags já necessárias."

    def handle(self, *args, **options):
        comando = [
            "pyinstaller",

            # Modo de empacotamento: pasta com o .exe dentro (mais rápido de
            # abrir que --onefile, sem atraso de extração) e sem console
            # visível — arquitetura já validada em 01/09/2026. --clean força
            # o PyInstaller a refazer a análise do zero a cada build — sem
            # isso, ele reaproveita cache antigo e ignora flag nova (bug
            # real encontrado em 04/09/2026: log mostrou "checking Analysis"
            # e pulou direto pra PYZ/PKG/EXE/COLLECT em menos de 1 segundo,
            # sem nenhuma análise de verdade acontecer)
            "--onedir",
            "--noconsole",
            "--clean",
            "--name", "SistemaDevolucoes",
            "--icon", "launcher_recursos/icone_app.ico",

            # Arquivos estáticos que o PyInstaller não empacota sozinho —
            # precisam ser apontados manualmente: tela de carregamento HTML,
            # ícone da bandeja (reaproveita o mesmo .ico do --icon acima,
            # mas precisa entrar também aqui — --icon só grava o ícone no
            # próprio .exe, não deixa o arquivo disponível em tempo de
            # execução pro launcher.py abrir), templates e estáticos do
            # Django
            "--add-data", "launcher_recursos/loading.html;launcher_recursos",
            "--add-data", "launcher_recursos/icone_app.ico;launcher_recursos",
            "--add-data", "devolucoes/templates;devolucoes/templates",
            "--add-data", "devolucoes/static;devolucoes/static",

            # Imports dinâmicos que o PyInstaller não detecta analisando o
            # código (por isso precisam ser forçados manualmente): ícone de
            # bandeja (pystray); management commands do Django, necessários
            # desde que o launcher passou a chamar `migrate` sozinho; e os 2
            # módulos próprios do projeto (`core.middleware`,
            # `core.database_router`) que só são referenciados como string
            # em `MIDDLEWARE`/`DATABASE_ROUTERS` do settings.py, nunca com um
            # `import` direto em nenhum arquivo. Trocado de
            # `--collect-submodules=core` (log não mostrou nenhuma tentativa
            # de análise de `core`, 04/09/2026) pra `--hidden-import`
            # explícito nos 2 módulos — é o que a própria documentação do
            # PyInstaller recomenda pra este exato cenário (módulo só
            # referenciado por string).
            # [ATENÇÃO] → o --collect-submodules=reportlab.graphics.barcode
            # que existia aqui (pro xhtml2pdf) foi removido: o relatório de
            # devolução (Objetivo 5) deixou de gerar PDF via xhtml2pdf/
            # reportlab e virou uma tela HTML de impressão (Ctrl+P do
            # navegador) — se nenhum outro fluxo do sistema usar xhtml2pdf/
            # reportlab, dá pra tirar a dependência do pyproject.toml também
            # (`poetry remove xhtml2pdf`).
            "--hidden-import=pystray._win32",
            "--collect-submodules=django.core.management.commands",
            "--hidden-import=core.middleware",
            "--hidden-import=core.database_router",

            # Ponto de entrada do app
            "launcher.py",
        ]

        self.stdout.write(self.style.NOTICE("Gerando build (PyInstaller --onedir)..."))
        resultado = subprocess.run(comando)

        if resultado.returncode != 0:
            raise CommandError(f"PyInstaller terminou com erro (código {resultado.returncode}) — veja o log acima.")

        self.stdout.write(self.style.SUCCESS("Build concluído em dist/SistemaDevolucoes/"))