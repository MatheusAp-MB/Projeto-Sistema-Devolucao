# core/urls.py

# Função Objetivo: URLs do app core. Por enquanto só a homepage —
# path temporário em /inicio/ até a Fase 6 (reorganização de URLs)
# mover isso pra raiz de verdade do projeto.

from django.urls import path

from . import views

urlpatterns = [
    path('', views.view_home, name='home'),
]