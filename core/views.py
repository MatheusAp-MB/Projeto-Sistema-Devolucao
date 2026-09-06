# core/views.py

# Função Objetivo: views globais do app core — hoje só a homepage.
# Path temporário em /inicio/ até a Fase 6 (reorganização de URLs)
# mover a raiz do projeto pra cá.

from django.shortcuts import render


def view_home(request):
    return render(request, 'pagina_home/estrutura_home.html')