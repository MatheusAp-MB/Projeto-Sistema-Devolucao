# core/urls.py

# Função Objetivo: URLs do app core — homepage e a tela de escolher a
# empresa ativa (Magazine/Samvale).

from django.urls import path

from . import views

urlpatterns = [
    path('', views.view_home, name='home'),
    path('escolher-empresa/', views.view_escolher_empresa, name='escolher_empresa'),
]