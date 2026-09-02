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
from PIL import Image, ImageDraw
from waitress import serve

# Precisa ser setado antes do import de core.wsgi, que dispara o
# carregamento do Django (django.setup()) no momento em que é importado.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from core.wsgi import application

HOST = "127.0.0.1"
PORTA = 8000
URL = f"http://{HOST}:{PORTA}/"


def caminho_recurso(nome_arquivo):
    # sys._MEIPASS existe só quando rodando como .exe empacotado (PyInstaller)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome_arquivo)


def porta_ja_em_uso():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, PORTA))
        return False
    except OSError:
        return True
    finally:
        sock.close()


def rodar_servidor():
    serve(application, host=HOST, port=PORTA)


def abrir_tela_de_carregamento():
    caminho = caminho_recurso("loading.html")
    webbrowser.open(f"file:///{caminho}")


def abrir_navegador(icone=None, item=None):
    webbrowser.open(URL)


def criar_imagem_icone():
    imagem = Image.new("RGB", (64, 64), color=(112, 59, 246))
    desenho = ImageDraw.Draw(imagem)
    desenho.ellipse((16, 16, 48, 48), fill=(255, 255, 255))
    return imagem


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

    threading.Thread(target=rodar_servidor, daemon=True).start()
    abrir_tela_de_carregamento()
    iniciar_icone_bandeja()