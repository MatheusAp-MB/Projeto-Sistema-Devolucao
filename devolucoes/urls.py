# devolucoes/urls.py

from django.urls import path

from . import views

urlpatterns = [
    path('nova-devolucao/', views.nova_devolucao, name='nova_devolucao'),
    path('produtos/', views.produtos, name='produtos'),
    path('catalogo/', views.catalogo, name='catalogo'),
    path('catalogo/produto/cadastrar/', views.cadastrar_produto, name='cadastrar_produto'),
    path('catalogo/produto/<int:produto_id>/editar/', views.editar_produto, name='editar_produto'),
    path('catalogo/produto/<int:produto_id>/peca/adicionar/', views.adicionar_peca, name='adicionar_peca'),
    path('catalogo/peca/<int:peca_id>/remover/', views.remover_peca, name='remover_peca'),
]