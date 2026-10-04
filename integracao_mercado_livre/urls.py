# integracao_mercado_livre/urls.py

from django.urls import path

from . import views

urlpatterns = [
    path('mercado-livre/teste-conexao/', views.view_teste_conexao_ml, name='teste_conexao_ml'),
    path('mercado-livre/consultar-pedido/', views.view_consultar_pedido, name='consultar_pedido_ml'),
    path('mercado-livre/claim/<str:claim_id>/anexo/<str:filename>/', views.proxy_anexo_claim, name='proxy_anexo_claim'),
]