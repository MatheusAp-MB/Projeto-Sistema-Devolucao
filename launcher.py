# launcher.py

# Função Objetivo: ponto de entrada do executável empacotado (PyInstaller)
# — sobe o Django via waitress em background, abre a tela de carregamento
# (loading.html) e expõe o ícone de bandeja (pystray) para controle do
# ciclo de vida do processo (abrir de novo / encerrar).

import os
import socket
import sys
import threading
import webbrowser

import pystray
from PIL import Image
from waitress import serve

# Precisa ser setado antes do import de core.wsgi, que dispara o
# carregamento do Django (django.setup()) no momento em que é importado.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projeto_sistema_devolucao_mb_sv.settings")

from django.core.management import call_command
from projeto_sistema_devolucao_mb_sv.wsgi import application

# HOST_LOCAL é usado só pra 2 coisas desta própria máquina: checar se
# já tem uma instância rodando, e abrir o navegador local sozinho (o
# atalho da bandeja/loading). O acesso de fora (celular, outro PC) usa
# o IPV4_LOCAL do .env — mesmo IP fixo que já é usado direto no
# "runserver ipv4:8000" no escritório.
HOST_LOCAL = "127.0.0.1"
PORTA = 8000
URL = f"http://{HOST_LOCAL}:{PORTA}/"


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
    # IPV4_LOCAL vem do .env (ex.: 192.168.0.50) — mesmo IP fixo já
    # usado no "runserver ipv4:8000" no escritório. Escuta em 2
    # endereços específicos (não em "tudo"): localhost, pra continuar
    # abrindo sozinho nesta máquina, e o IP da rede, pro celular
    # acessar. Se IPV4_LOCAL não estiver no .env (ex.: teste local seu,
    # sem essa variável), escuta só em localhost mesmo.
    ip_rede = os.getenv("IPV4_LOCAL")
    enderecos = f"{HOST_LOCAL}:{PORTA}"
    if ip_rede:
        enderecos += f" {ip_rede}:{PORTA}"

    try:
        serve(application, listen=enderecos)
    except OSError:
        # Rede de segurança: se o IP do .env não existir mais nesta
        # máquina (mudou de rede, .env desatualizado), não deixa o
        # sistema travar sem abrir nem localmente — cai pra localhost.
        serve(application, host=HOST_LOCAL, port=PORTA)


def abrir_tela_de_carregamento():
    caminho = caminho_recurso("launcher_recursos/loading.html")
    webbrowser.open(f"file:///{caminho}")


def abrir_navegador(icone=None, item=None):
    webbrowser.open(URL)


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