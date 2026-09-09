# launcher.py

# Função Objetivo: ponto de entrada do executável empacotado (PyInstaller)
# — sobe o Django via waitress em background, abre a tela de carregamento
# (loading.html) e expõe o ícone de bandeja (pystray) para controle do
# ciclo de vida do processo (abrir de novo / encerrar).

import os
import socket
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import pystray
from PIL import Image
from waitress import serve

# Precisa ser setado antes do import de core.wsgi, que dispara o
# carregamento do Django (django.setup()) no momento em que é importado.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projeto_sistema_devolucao_mb_sv.settings")

from django.core.management import call_command
from projeto_sistema_devolucao_mb_sv.wsgi import application
from django.conf import settings as django_settings

# HOST_LOCAL é usado só pra 2 coisas desta própria máquina: checar se
# já tem uma instância rodando, e o fallback de bind caso o IPV4_LOCAL
# não exista mais nesta máquina. IP_REDE (do .env) é o mesmo IP usado
# no "runserver ipv4:8000" no escritório — quando existe, URL passa a
# ser ele, pra abrir direto nesse endereço (PC e celular usam o mesmo
# link, sem fallback).
HOST_LOCAL = "127.0.0.1"
PORTA = 8000

IP_REDE = os.getenv("IPV4_LOCAL")
URL = f"http://{IP_REDE}:{PORTA}/" if IP_REDE else f"http://{HOST_LOCAL}:{PORTA}/"


def caminho_recurso(nome_arquivo):
    # sys._MEIPASS existe só quando rodando como .exe empacotado (PyInstaller)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome_arquivo)


def porta_ja_em_uso():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST_LOCAL, PORTA))
        return False
    except OSError:
        return True
    finally:
        sock.close()


def rodar_servidor():
    # Escuta em 2 endereços específicos (não em "tudo"): localhost, pra
    # continuar abrindo sozinho nesta máquina, e IP_REDE (do .env), pro
    # celular acessar. Se IPV4_LOCAL não estiver no .env (ex.: teste
    # local seu, sem essa variável), escuta só em localhost mesmo.
    enderecos = f"{HOST_LOCAL}:{PORTA}"
    if IP_REDE:
        enderecos += f" {IP_REDE}:{PORTA}"

    try:
        serve(application, listen=enderecos)
    except OSError:
        # Rede de segurança: se o IP do .env não existir mais nesta
        # máquina (mudou de rede, .env desatualizado), não deixa o
        # sistema travar sem abrir nem localmente — cai pra localhost.
        serve(application, host=HOST_LOCAL, port=PORTA)


def abrir_tela_de_carregamento():
    caminho = caminho_recurso("launcher_recursos/loading.html")
    # Raio-x completo pra fechar o diagnóstico de vez: mostra se o .exe
    # está mesmo "congelado" (sys.frozen), qual caminho ele calculou
    # pro .env (mesma conta do settings.py) e se esse .env realmente
    # existe ali — tudo que precisamos saber pra achar onde a leitura
    # está realmente falhando.
    pasta_env = django_settings.PASTA_ENV
    diagnostico = {
        "url": URL,
        "ip_bruto": repr(IP_REDE),
        "frozen": str(getattr(sys, "frozen", False)),
        "exe": sys.executable,
        "pasta_env": str(pasta_env),
        "env_existe": str((pasta_env / ".env").is_file()),
    }
    query = urllib.parse.urlencode(diagnostico)
    uri = Path(caminho).as_uri()
    webbrowser.open(f"{uri}?{query}")


def abrir_navegador(icone=None, item=None):
    # Reaproveita a mesma tela/lógica de conexão do início — evita
    # abrir direto numa URL que pode não estar mais respondendo.
    abrir_tela_de_carregamento()


def criar_imagem_icone():
    caminho = caminho_recurso("launcher_recursos/icone_app.ico")
    return Image.open(caminho).convert("RGBA").resize((64, 64), Image.LANCZOS)


def encerrar(icone, item):
    icone.stop()
    os._exit(0)


def iniciar_icone_bandeja():
    menu = pystray.Menu(
        pystray.MenuItem("Abrir no navegador", abrir_navegador),
        pystray.MenuItem("Encerrar", encerrar),
    )
    pystray.Icon(
        "sistema_devolucoes", criar_imagem_icone(),
        "Sistema de Relatório de Devoluções", menu,
    ).run()


if __name__ == "__main__":
    if porta_ja_em_uso():
        abrir_navegador()
        sys.exit(0)

    for alias in ("magazine", "samvale"):
        call_command("migrate", database=alias, verbosity=0)

    threading.Thread(target=rodar_servidor, daemon=True).start()
    abrir_tela_de_carregamento()
    iniciar_icone_bandeja()