# devolucoes/urls.py

from django.urls import path

from . import views

urlpatterns = [
    path('nova-devolucao/', views.nova_devolucao, name='nova_devolucao'),
    path('nova-devolucao/buscar-produto/', views.buscar_produtos_devolucao, name='buscar_produtos_devolucao'),
    path('devolucoes/pendentes/', views.devolucoes_pendentes, name='devolucoes_pendentes'),
    path('devolucoes/<int:devolucao_id>/editar/', views.editar_devolucao, name='editar_devolucao'),
    path('devolucoes/<int:devolucao_id>/excluir/', views.excluir_devolucao, name='excluir_devolucao'),
    path('devolucoes/<int:devolucao_id>/conferir/', views.conferir_devolucao, name='conferir_devolucao'),
    path('conferencia-peca/foto/<int:foto_id>/excluir/', views.excluir_foto_conferencia, name='excluir_foto_conferencia'),
    path('devolucoes/<int:devolucao_id>/relatorio/', views.imprimir_relatorio_devolucao, name='imprimir_relatorio_devolucao'),
    path('produtos/', views.produtos, name='produtos'),
    path('produtos/<int:produto_id>/', views.visualizar_produto, name='visualizar_produto'),
    path('produtos/<int:produto_id>/excluir/', views.excluir_produto, name='excluir_produto'),
    path('catalogo/marca/cadastrar/', views.cadastrar_marca, name='cadastrar_marca'),
    path('catalogo/grupo-fornecedor/cadastrar/', views.cadastrar_grupo_fornecedor, name='cadastrar_grupo_fornecedor'),
    path('catalogo/produto/cadastrar/', views.cadastrar_produto, name='cadastrar_produto'),
    path('catalogo/produto/<int:produto_id>/editar/', views.editar_produto, name='editar_produto'),
    path('catalogo/produto/<int:produto_id>/pecas/vincular/', views.vincular_pecas_produto, name='vincular_pecas_produto'),
    # [ATENÇÃO] → buscar_pecas não é mais usada por nenhum fluxo do produto,
    # mas _modal_vinculo.html (compartilhado, ainda ativo no lado da peça)
    # referencia essa URL incondicionalmente — ver docstring da view.
    path('catalogo/produto/<int:produto_id>/peca/buscar/', views.buscar_pecas, name='buscar_pecas'),
    path('catalogo/peca/cadastrar/', views.cadastrar_peca_avulsa, name='cadastrar_peca_avulsa'),
    path('catalogo/peca/<int:peca_id>/editar/', views.editar_peca, name='editar_peca'),
    path('catalogo/compatibilidade/<int:compatibilidade_id>/desvincular/', views.desvincular_peca, name='desvincular_peca'),
    path('catalogo/peca/<int:peca_id>/excluir/', views.excluir_peca, name='excluir_peca'),

    path('pecas/', views.gaveta_pecas, name='gaveta_pecas'),
    path('pecas/cadastrar/', views.cadastrar_peca_gaveta, name='cadastrar_peca_gaveta'),
    path('pecas/<int:peca_id>/editar/', views.editar_peca_gaveta, name='editar_peca_gaveta'),
    path('pecas/vincular/', views.vincular_peca_gaveta, name='vincular_peca_gaveta'),
    path('pecas/<int:peca_id>/produtos/buscar/', views.buscar_produtos, name='buscar_produtos'),

    path('marcas-grupos/', views.marcas_grupos, name='marcas_grupos'),
    path('marcas-grupos/marca/cadastrar/', views.cadastrar_marca_avulsa, name='cadastrar_marca_avulsa'),
    path('marcas-grupos/marca/<int:marca_id>/editar/', views.editar_marca, name='editar_marca'),
    path('marcas-grupos/marca/<int:marca_id>/excluir/', views.excluir_marca, name='excluir_marca'),
    path('marcas-grupos/grupo/cadastrar/', views.cadastrar_grupo_fornecedor_avulso, name='cadastrar_grupo_fornecedor_avulso'),
    path('marcas-grupos/grupo/<int:grupo_id>/editar/', views.editar_grupo_fornecedor, name='editar_grupo_fornecedor'),
    path('marcas-grupos/grupo/<int:grupo_id>/excluir/', views.excluir_grupo_fornecedor, name='excluir_grupo_fornecedor'),
]