# devolucoes/urls.py

from django.urls import path

from . import views

urlpatterns = [
    path('nova-devolucao/', views.nova_devolucao, name='nova_devolucao'),
    path('produtos/', views.produtos, name='produtos'),
    path('produtos/<int:produto_id>/excluir/', views.excluir_produto, name='excluir_produto'),
    path('catalogo/', views.catalogo, name='catalogo'),
    path('catalogo/marca/cadastrar/', views.cadastrar_marca, name='cadastrar_marca'),
    path('catalogo/grupo-fornecedor/cadastrar/', views.cadastrar_grupo_fornecedor, name='cadastrar_grupo_fornecedor'),
    path('catalogo/produto/cadastrar/', views.cadastrar_produto, name='cadastrar_produto'),
    path('catalogo/produto/<int:produto_id>/editar/', views.editar_produto, name='editar_produto'),
    path('catalogo/produto/<int:produto_id>/peca/buscar/', views.buscar_pecas, name='buscar_pecas'),
    path('catalogo/produto/<int:produto_id>/peca/vincular/', views.vincular_peca, name='vincular_peca'),
    path('catalogo/produto/<int:produto_id>/peca/cadastrar/', views.cadastrar_peca, name='cadastrar_peca'),
    path('catalogo/compatibilidade/<int:compatibilidade_id>/desvincular/', views.desvincular_peca, name='desvincular_peca'),
    path('catalogo/peca/<int:peca_id>/excluir/', views.excluir_peca, name='excluir_peca'),
]