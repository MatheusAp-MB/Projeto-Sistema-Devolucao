# integracao_mercado_livre/urls.py

from django.urls import path

from . import views

urlpatterns = [
    path('mercado-livre/teste-conexao/', views.view_teste_conexao_ml, name='teste_conexao_ml'),
]