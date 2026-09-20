# devolucoes/views.py

# Função Objetivo: views da tela de Nova Devolução (Fase 0 + busca/
# seleção de produto — salva a base da devolução no banco; a
# conferência de peças em si é um Objetivo separado, feita depois pelo
# celular) — views do catálogo de produtos e peças — criar/excluir
# produto e 3 telas próprias e separadas pra ele (Visualizar, só
# leitura; Editar, só os dados do produto; Vincular peças, tela
# dedicada que reaproveita a visão agrupada da Gaveta de Peças pra
# selecionar em massa quais peças ficam vinculadas e com que
# quantidade) — cadastrar/editar/excluir/desvincular peça — cadastro
# isolado de Marca/Grupo Fornecedor via AJAX (chamado de dentro da tela
# de produto) — e a tela própria de gerenciar Marcas e Grupos
# Fornecedores (criar/editar/excluir cada um, direto na lista).

import json
import re
import subprocess
import threading
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from core.empresa import obter_alias_banco_ativo, obter_empresa_ativa
from integracao_mercado_livre.views import CONTA_POR_EMPRESA

from .models import (
    ClaimMercadoLivre, Compatibilidade, ConferenciaPeca, Devolucao,
    FotoConferenciaPeca, FotoObservacaoGeral, FotoReclamacaoCliente,
    GrupoFornecedor, Marca, MediacaoAvulsa, ModeloAnotacao, Peca, Produto,
    StatusVarreduraMediacoes,
)
from .reorganizacao_fotos import reorganizar_fotos_devolucao
from .varredura_mediacoes import (
    atualizar_e_formatar_mensagens, buscar_nome_cliente_e_produto,
    categoria_slug, contagem_por_categoria, executar_atualizacao_acompanhados,
    executar_varredura_completa,
)


def imprimir_relatorio_devolucao(request, devolucao_id):
    """Tela de impressão do relatório de 1 devolução (Objetivo 5/Finalizar).

    [ATENÇÃO] → Isso NÃO gera PDF no servidor. É uma página HTML normal,
    com estilos de impressão (@media print) — a pessoa aperta Ctrl+P (ou
    o botão "Imprimir" da própria página) e usa a tela de impressão do
    navegador (imprime na física ou "Salvar como PDF"). Trocamos de
    abordagem depois de bater de frente com as limitações de bibliotecas
    de PDF em Python (xhtml2pdf ignora background/border em elemento
    inline dentro de tabela; WeasyPrint precisa de Pango/GObject nativo,
    que não empacota bem no PyInstaller no Windows; Playwright exige
    baixar um Chromium inteiro). Usando render() (não render_to_string)
    o context processor de empresa_ativa_nome roda sozinho, sem precisar
    passar request= manualmente.

    Só faz sentido de verdade depois de conferida — por isso o botão que
    chama essa view (devolucoes_pendentes.html) só aparece quando
    destino_produto já está preenchido, mas pode ser aberta a qualquer
    momento."""
    devolucao = get_object_or_404(
        Devolucao.objects.select_related('produto__marca'), pk=devolucao_id,
    )
    pecas_conferidas = (
        devolucao.pecas_conferidas
        .select_related('peca__marca')
        .order_by('peca__nome_generico')
    )
    return render(request, 'devolucoes/relatorio_devolucao_impressao.html', {
        'devolucao': devolucao,
        'pecas_conferidas': pecas_conferidas,
    })


def _sanitizar_texto_zpl(texto):
    """Remove caracteres que têm significado especial em ZPL: ^ inicia um
    comando (ex: ^FO, ^FD) e ~ inicia um comando de controle (ex: ~PS) — se
    algum dado real (nome do cliente, nome do produto, código de barras
    digitado manualmente) tiver um desses caracteres por acaso, ele
    quebraria a leitura da etiqueta na impressora/Labelary sem avisar.
    Troca por hífen em vez de apagar, pra não colar duas palavras."""
    return (texto or '').replace('^', '-').replace('~', '-')


def _preparar_codigo_barras_produto(codigo_barras):
    """Decide como desenhar o código de barras do produto na etiqueta
    térmica, a partir de Produto.codigo_barras — campo de texto livre, sem
    validação de formato hoje, então não é garantido que seja sempre um
    EAN-13/12 numérico "limpo".

    Retorna (tipo, valor):
    - ('ean', <12 dígitos>) quando dá pra desenhar como EAN-13 de verdade
      (comando ^BE, que é o padrão visual de código de barras de varejo).
      ^BE espera exatamente 12 dígitos de entrada — o 13º (dígito
      verificador) é calculado sozinho pela impressora/Labelary. Se o
      código cadastrado já tiver 13 dígitos, usamos só os 12 primeiros
      (mesma correção que o próprio Labelary já faz sozinho quando recebe
      13 dígitos — testado durante o desenho do layout com Matheus).
    - ('code128', <texto sanitizado>) quando o valor não é um EAN numérico
      "limpo" (tem letra, tamanho diferente de 12/13...) — cai pro
      Code128 (^BC), que aceita qualquer texto/alfanumérico, o mesmo tipo
      de código já usado pro número do pedido.
    - (None, None) quando não há codigo_barras cadastrado nesse produto —
      a etiqueta sai sem nenhum código de barras nesse campo.
    """
    if not codigo_barras:
        return None, None
    apenas_digitos = re.sub(r'\D', '', codigo_barras)
    if len(apenas_digitos) == 13:
        return 'ean', apenas_digitos[:12]
    if len(apenas_digitos) == 12:
        return 'ean', apenas_digitos
    return 'code128', _sanitizar_texto_zpl(codigo_barras)


def _montar_zpl_etiqueta_termica_devolucao(devolucao):
    """Monta o texto ZPL da etiqueta térmica 10x15cm (mini-relatório) de 1
    devolução — layout desenhado e aprovado por Matheus testando no
    Labelary (https://labelary.com/viewer.html) em 17-18/09/2026 (ver nota
    "Relato Completo do Fluxo Real..." no vault, seção "Layout final da
    etiqueta térmica (ZPL)").

    [ATENÇÃO] → Isso NÃO imprime nada sozinho e NÃO gera PDF no servidor.
    Gera só o TEXTO ZPL — igual ao que já vem pronto do ERP/Mercado Livre
    em outras situações — pra colar no Labelary, conferir visualmente e
    baixar o PDF de lá, que é o que de fato vai pra impressora Zebra
    (mesmo fluxo manual já usado hoje pra qualquer etiqueta térmica
    instável).

    Densidade assumida: 8 dpmm / 203 dpi (impressora Zebra do Matheus,
    testado e confirmado no Labelary) — label 10x15cm = 800x1200 dots.

    [NOVO, 19/09/2026] → quando a mediação está genuinamente aberta (tem
    data de abertura e ainda não tem data de encerramento — mesma regra da
    versão HTML/CSS e da aba "Mediações Abertas"), insere um bloco de
    aviso "EM MEDIACAO" logo abaixo do cabeçalho e empurra todo o resto do
    layout 70 dots pra baixo (variável 'deslocamento') — a versão original
    tinha ~137 dots de folga antes do limite de 1200 (15cm), então isso
    cabe com margem de sobra, sem precisar redesenhar o resto do zero.
    IMPORTANTE: como isso não é validado automaticamente (só no Labelary,
    manualmente, como sempre foi esse fluxo backup), reconferir lá antes
    de confiar numa devolução com mediação aberta."""
    produto = devolucao.produto

    numero_pedido = _sanitizar_texto_zpl(devolucao.numero_pedido)
    numero_nota_fiscal = _sanitizar_texto_zpl(devolucao.numero_nota_fiscal)
    nome_cliente = _sanitizar_texto_zpl(devolucao.nome_cliente)
    plataforma = _sanitizar_texto_zpl(
        f'{devolucao.nome_plataforma} - {devolucao.get_tipo_venda_display()}'
    )
    nome_produto = _sanitizar_texto_zpl(produto.nome)
    sku = _sanitizar_texto_zpl(produto.sku) if produto.sku else '-'
    gerado_em = timezone.localtime().strftime('%d/%m/%Y %H:%M')

    tipo_codigo_produto, valor_codigo_produto = _preparar_codigo_barras_produto(
        produto.codigo_barras
    )

    em_mediacao = bool(
        devolucao.data_abertura_mediacao and not devolucao.data_finalizacao_mediacao
    )
    deslocamento = 70 if em_mediacao else 0

    if em_mediacao:
        data_abertura_str = devolucao.data_abertura_mediacao.strftime('%d/%m/%Y')
        bloco_mediacao = (
            '^FO40,115^GB720,75,3^FS\n'
            '^CF0,28\n'
            f'^FO40,140^FB720,1,0,C,0^FDEM MEDIACAO - ABERTA EM {data_abertura_str}\\&^FS\n'
        )
    else:
        bloco_mediacao = ''

    if tipo_codigo_produto == 'ean':
        bloco_codigo_produto = (
            '^CF0,20\n'
            f'^FO40,{875 + deslocamento}^FDEAN^FS\n'
            f'^FO40,{900 + deslocamento}^BY3\n'
            '^BEN,70,Y,N\n'
            f'^FD{valor_codigo_produto}^FS'
        )
    elif tipo_codigo_produto == 'code128':
        bloco_codigo_produto = (
            '^CF0,20\n'
            f'^FO40,{875 + deslocamento}^FDCODIGO DE BARRAS^FS\n'
            f'^FO40,{900 + deslocamento}^BY2\n'
            '^BCN,70,N,N,N,A\n'
            f'^FD{valor_codigo_produto}^FS'
        )
    else:
        bloco_codigo_produto = (
            '^CF0,20\n'
            f'^FO40,{875 + deslocamento}^FDEAN^FS\n'
            '^CF0,26\n'
            f'^FO40,{900 + deslocamento}^FD(produto sem codigo de barras cadastrado)^FS'
        )

    return f'''^XA
^CI28

^FX ===== Cabecalho =====
^CF0,32
^FO40,40^FB720,2,0,C,0^FDDEVOLUCAO - IDENTIFICACAO PROVISORIA\\&^FS
^FO40,105^GB720,3,3^FS

{bloco_mediacao}
^FX ===== Bloco: Pedido & Cliente =====
^CF0,20
^FO40,{135 + deslocamento}^FDPEDIDO^FS
^CF0,36
^FO40,{160 + deslocamento}^FD{numero_pedido}^FS

^FX --- codigo de barras do pedido, ao lado do numero ---
^FO430,{130 + deslocamento}^BY2
^BCN,70,N,N,N,A
^FD{numero_pedido}^FS

^CF0,20
^FO40,{225 + deslocamento}^FDNF^FS
^CF0,36
^FO40,{250 + deslocamento}^FD{numero_nota_fiscal}^FS

^CF0,20
^FO40,{310 + deslocamento}^FDCLIENTE^FS
^CF0,30
^FO40,{335 + deslocamento}^FB720,2,0,L,0^FD{nome_cliente}\\&^FS

^FO40,{395 + deslocamento}^GB720,3,3^FS

^FX ===== Bloco: Plataforma =====
^CF0,20
^FO40,{420 + deslocamento}^FDPLATAFORMA^FS
^CF0,32
^FO40,{445 + deslocamento}^FD{plataforma}^FS

^FO40,{500 + deslocamento}^GB720,3,3^FS

^FX ===== Bloco: Datas =====
^CF0,20
^FO40,{525 + deslocamento}^FDDATAS^FS
^CF0,26
^FO40,{552 + deslocamento}^FDVenda: {devolucao.data_venda.strftime('%d/%m/%Y')}^FS
^FO40,{594 + deslocamento}^FDRecebido pelo cliente: {devolucao.data_recebimento_cliente.strftime('%d/%m/%Y')}^FS
^FO40,{636 + deslocamento}^FDReclamacao aberta: {devolucao.data_reclamacao_cliente.strftime('%d/%m/%Y')}^FS
^FO40,{678 + deslocamento}^FDRecebido por nos: {devolucao.data_recebimento_por_nos.strftime('%d/%m/%Y')}^FS

^FO40,{735 + deslocamento}^GB720,3,3^FS

^FX ===== Bloco: Produto (com codigo de barras dentro do bloco) =====
^CF0,20
^FO40,{760 + deslocamento}^FDPRODUTO^FS
^CF0,26
^FO40,{785 + deslocamento}^FB720,2,0,L,0^FD{nome_produto}\\&^FS

{bloco_codigo_produto}

^CF0,20
^FO430,{875 + deslocamento}^FDSKU^FS
^CF0,32
^FO430,{900 + deslocamento}^FD{sku}^FS

^FO40,{1020 + deslocamento}^GB720,3,3^FS

^FX ===== Rodape =====
^CF0,18
^FO40,{1045 + deslocamento}^FDGerado em {gerado_em}^FS

^XZ
'''


FORMATO_JSBARCODE_PRODUTO = {'ean': 'EAN13', 'code128': 'CODE128'}


def imprimir_etiqueta_termica_devolucao(request, devolucao_id):
    """Tela PRINCIPAL de impressão da etiqueta térmica (mini-relatório
    10x15cm) de 1 devolução — Fase 8 do fluxo (ver vault). É essa que o
    botão "Etiqueta térmica" em devolucoes_pendentes.html abre.

    [ATENÇÃO] → Igual a imprimir_relatorio_devolucao: isso NÃO gera PDF
    no servidor. É uma página HTML normal com @page 10x15cm (@media
    print) — a pessoa aperta Ctrl+P (ou o botão "Imprimir" da própria
    página) e imprime direto na Zebra, que aparece como impressora comum
    no Windows. Os códigos de barras (pedido + produto/EAN) são
    desenhados no próprio navegador via JsBarcode (carregado por CDN no
    template — https://github.com/lindell/JsBarcode, MIT, zero
    dependências), sem gerar imagem no servidor e sem precisar de
    nenhuma lib Python nova (não mexe no empacotamento em .exe).

    Se a impressão direta der problema, a própria página tem um link
    "Backup: código ZPL" que leva pra gerar_etiqueta_termica_devolucao —
    o fluxo manual (copiar → colar no Labelary → baixar PDF → imprimir),
    que continua existindo e testado, agora só como plano B.

    Mesma disponibilidade do botão "Imprimir relatório": só aparece em
    devolucoes_pendentes.html quando destino_produto já está preenchido,
    mas pode ser aberta a qualquer momento."""
    devolucao = get_object_or_404(
        Devolucao.objects.select_related('produto'), pk=devolucao_id,
    )
    tipo_codigo_produto, valor_codigo_produto = _preparar_codigo_barras_produto(
        devolucao.produto.codigo_barras
    )
    return render(request, 'devolucoes/etiqueta_termica_devolucao_impressao.html', {
        'devolucao': devolucao,
        'formato_codigo_produto': FORMATO_JSBARCODE_PRODUTO.get(tipo_codigo_produto),
        'valor_codigo_produto': valor_codigo_produto,
    })


def gerar_etiqueta_termica_devolucao(request, devolucao_id):
    """Tela BACKUP que gera o texto ZPL da etiqueta térmica (mini-
    relatório) de 1 devolução — Fase 8 do fluxo (ver vault). A tela
    principal do dia a dia é imprimir_etiqueta_termica_devolucao (imprime
    direto, sem esse passo manual) — essa aqui só entra em cena quando a
    impressão direta falhar/ficar instável.

    [ATENÇÃO] → Não imprime nem gera PDF sozinha (ver docstring de
    _montar_zpl_etiqueta_termica_devolucao). A página só mostra o código
    ZPL pronto num bloco de texto com botão "Copiar" — quem usa cola esse
    código no Labelary (https://labelary.com/viewer.html), confere
    visualmente, baixa o PDF de lá e imprime na Zebra normalmente, igual
    já é feito hoje pra qualquer etiqueta térmica instável.

    Não é mais linkada direto do botão em devolucoes_pendentes.html — só
    é alcançada a partir do link "Backup: código ZPL" dentro da tela
    principal."""
    devolucao = get_object_or_404(
        Devolucao.objects.select_related('produto'), pk=devolucao_id,
    )
    zpl = _montar_zpl_etiqueta_termica_devolucao(devolucao)
    return render(request, 'devolucoes/etiqueta_termica_devolucao.html', {
        'devolucao': devolucao,
        'zpl': zpl,
    })


def _parse_data_opcional(valor):
    """Converte o valor de um <input type=date> pro DateField — string
    vazia vira None (campo realmente em branco, ex: mediação que nem
    abriu ainda), senão passa a string ISO adiante pro Django parsear
    na hora de salvar."""
    valor = (valor or '').strip()
    return valor or None


def _parse_reembolsado(valor):
    """Converte o <select> de reembolso (3 estados) pro BooleanField
    null=True do model: '' = ainda não sei/mediação em aberto, 'sim'/
    'nao' = já resolvido."""
    if valor == 'sim':
        return True
    if valor == 'nao':
        return False
    return None


def _parse_decimal_opcional(valor):
    """Converte um <input type=number step=0.01> (preco_produto,
    valor_reembolsado) pro DecimalField null=True do model — string
    vazia vira None, igual às datas de mediação em _parse_data_opcional.
    O HTML5 sempre manda com '.' como separador decimal, não importa o
    idioma do navegador (spec do WHATWG), então não precisa tratar
    vírgula aqui. Um valor que não dá pra converter (alguém mexeu no
    HTML na mão, por exemplo) também vira None em vez de quebrar a
    página."""
    valor = (valor or '').strip()
    if not valor:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


def _contexto_nova_devolucao(valores=None, produto_selecionado=None, devolucao=None, busca_produto_sugerida=''):
    """Monta o contexto da tela de Nova Devolução (Fase 0 + busca/
    seleção de produto) — usada tanto pro GET simples quanto pra
    re-exibir o formulário com o que a pessoa digitou quando a
    validação falha. 'devolucao' só vem preenchido quando é
    editar_devolucao reaproveitando este mesmo template — é o que o
    template usa pra virar "Editar devolução" (título, texto do botão)
    em vez de "Nova devolução". 'busca_produto_sugerida' só vem preenchido
    quando chega da ponte Consultar Pedido → Nova Devolução (SKU do
    vendedor no ML) — o template joga esse valor no campo de busca de
    produto e a JS dispara a busca sozinha ao carregar a página."""
    if valores is None:
        valores = {
            'nome_plataforma': '', 'tipo_venda': '',
            'numero_pedido': '', 'numero_nota_fiscal': '', 'nome_cliente': '',
            'preco_produto': '',
            'data_venda': '',
            'data_recebimento_cliente': '', 'data_reclamacao_cliente': '', 'data_recebimento_por_nos': '',
            'data_abertura_mediacao': '', 'data_finalizacao_mediacao': '',
            'reembolsado': '', 'valor_reembolsado': '', 'anotacao_mediacao': '',
            'motivo_reclamacao': '',
        }

    return {
        'valores': valores,
        'produto_selecionado': produto_selecionado,
        'devolucao': devolucao,
        'fotos_reclamacao_cliente': devolucao.fotos_reclamacao_cliente.all() if devolucao else [],
        'busca_produto_sugerida': busca_produto_sugerida,
        'plataforma_choices': Devolucao.PLATAFORMA_CHOICES,
        'tipo_venda_choices': Devolucao.TIPO_VENDA_CHOICES,
        'pagina_ativa': 'nova_devolucao',
    }


def _valores_da_devolucao(devolucao):
    """Serializa uma Devolucao já salva pro dict 'valores' que o
    template de Nova Devolução espera — usado só por editar_devolucao
    (GET), pra pré-preencher o formulário com o que já está salvo.

    preco_produto/valor_reembolsado são formatados aqui como string
    com '.' (f'{valor:.2f}'), NUNCA jogando o Decimal cru pro dict —
    se fosse o Decimal cru, o Django localizaria ele sozinho pro
    template (vírgula, "366,00") e o <input type=number> ignora
    silenciosamente um value com vírgula (o HTML5 exige '.'), fazendo
    o campo parecer vazio ao reabrir o formulário."""
    return {
        'nome_plataforma': devolucao.nome_plataforma,
        'tipo_venda': devolucao.tipo_venda,
        'numero_pedido': devolucao.numero_pedido,
        'numero_nota_fiscal': devolucao.numero_nota_fiscal,
        'nome_cliente': devolucao.nome_cliente,
        'preco_produto': f'{devolucao.preco_produto:.2f}' if devolucao.preco_produto is not None else '',
        'data_venda': devolucao.data_venda.isoformat(),
        'data_recebimento_cliente': devolucao.data_recebimento_cliente.isoformat(),
        'data_reclamacao_cliente': devolucao.data_reclamacao_cliente.isoformat(),
        'data_recebimento_por_nos': devolucao.data_recebimento_por_nos.isoformat(),
        'data_abertura_mediacao': devolucao.data_abertura_mediacao.isoformat() if devolucao.data_abertura_mediacao else '',
        'data_finalizacao_mediacao': devolucao.data_finalizacao_mediacao.isoformat() if devolucao.data_finalizacao_mediacao else '',
        'reembolsado': 'sim' if devolucao.reembolsado is True else 'nao' if devolucao.reembolsado is False else '',
        'valor_reembolsado': f'{devolucao.valor_reembolsado:.2f}' if devolucao.valor_reembolsado is not None else '',
        'anotacao_mediacao': devolucao.anotacao_mediacao,
        'motivo_reclamacao': devolucao.motivo_reclamacao,
    }


def nova_devolucao(request):
    """Tela de abertura da devolução — preenchida no PC. Reúne os dados
    da Fase 0 (plataforma, pedido, cliente, datas, mediação, reclamação
    do cliente) mais a busca/seleção do produto (Fases 1-2, via
    buscar_produtos_devolucao). Ao salvar, cria a Devolucao no banco já
    com o produto definido — mas ainda sem destino_produto nem peças
    conferidas, porque essa 2ª parte é feita depois, pelo celular (ver
    devolucoes_pendentes).

    O GET também aceita chegar com ?numero_pedido=... e companhia, vindo
    do botão "Criar devolução" da tela Consultar Pedido (ponte decidida
    no vault em 17/09 23:24) — nesse caso já chega com plataforma, pedido,
    cliente e datas pré-preenchidos, e NF/reembolsado/motivo da reclamação
    continuam em branco pra confirmação manual (decisão de Matheus,
    18/09/2026: só auto-preenche o que vem direto e confiável da API do
    ML). O produto não é selecionado sozinho, mas a busca já chega com o
    SKU do vendedor no ML (?produto_busca=...) e a JS dispara a mesma
    busca de sempre ao carregar a página — se bater exato com um código
    de barras, seleciona igual o leitor de código de barras faria; senão,
    já deixa a lista de candidatos pronta pra 1 clique (decisão de
    Matheus, 18/09/2026, reaproveitando o mesmo mecanismo do "Colar linha
    do ERP"). Se já existir uma devolução pra esse numero_pedido,
    redireciona pra editar_devolucao em vez de abrir o formulário vazio
    de novo — não cria duplicata.

    A partir de 19/09/2026 (pedido de Ana, via Matheus) o preço do
    produto (preco_produto) também vem preenchido por essa ponte — campo
    unit_price do 1º item de order_items na API do ML, que já é o preço
    unitário COM desconto aplicado (confirmado contra a documentação
    oficial e testado empiricamente com um pedido real — ver
    scripts_exploracao_ML/testar_preco_unitario_pedido.py). O
    valor_reembolsado fica de fora dessa ponte de propósito: não existe
    campo confiável pra isso na API do ML, então continua 100% manual.
    Os 2 campos (preco_produto, valor_reembolsado) são opcionais — dá
    pra salvar a devolução sem preencher nenhum dos 2."""
    if request.method == 'POST':
        valores = {
            'nome_plataforma': request.POST.get('nome_plataforma', '').strip(),
            'tipo_venda': request.POST.get('tipo_venda', '').strip(),
            'numero_pedido': request.POST.get('numero_pedido', '').strip(),
            'numero_nota_fiscal': request.POST.get('numero_nota_fiscal', '').strip(),
            'nome_cliente': request.POST.get('nome_cliente', '').strip(),
            'preco_produto': request.POST.get('preco_produto', '').strip(),
            'data_venda': request.POST.get('data_venda', '').strip(),
            'data_recebimento_cliente': request.POST.get('data_recebimento_cliente', '').strip(),
            'data_reclamacao_cliente': request.POST.get('data_reclamacao_cliente', '').strip(),
            'data_recebimento_por_nos': request.POST.get('data_recebimento_por_nos', '').strip(),
            'data_abertura_mediacao': request.POST.get('data_abertura_mediacao', '').strip(),
            'data_finalizacao_mediacao': request.POST.get('data_finalizacao_mediacao', '').strip(),
            'reembolsado': request.POST.get('reembolsado', '').strip(),
            'valor_reembolsado': request.POST.get('valor_reembolsado', '').strip(),
            'anotacao_mediacao': request.POST.get('anotacao_mediacao', '').strip(),
            'motivo_reclamacao': request.POST.get('motivo_reclamacao', '').strip(),
        }
        produto_id = request.POST.get('produto_id', '').strip()
        produto = Produto.objects.select_related('marca').filter(pk=produto_id).first() if produto_id else None

        rerenderizar = lambda: render(
            request, 'devolucoes/nova_devolucao.html',
            _contexto_nova_devolucao(valores, produto),
        )

        obrigatorios = [
            ('nome_plataforma', 'Plataforma'), ('tipo_venda', 'Tipo de venda'),
            ('numero_pedido', 'Número do pedido'), ('numero_nota_fiscal', 'Número da nota fiscal'),
            ('nome_cliente', 'Nome do cliente'),
            ('data_venda', 'Data da venda'),
            ('data_recebimento_cliente', 'Data de recebimento pelo cliente'),
            ('data_reclamacao_cliente', 'Data da reclamação'),
            ('data_recebimento_por_nos', 'Data de recebimento por nós'),
            ('motivo_reclamacao', 'Motivo da reclamação'),
        ]
        faltando = [rotulo for campo, rotulo in obrigatorios if not valores[campo]]
        if faltando:
            messages.error(request, f'Preencha: {", ".join(faltando)}.')
            return rerenderizar()

        if not produto:
            messages.error(request, 'Selecione um produto pela busca antes de salvar.')
            return rerenderizar()

        if valores['nome_plataforma'] not in dict(Devolucao.PLATAFORMA_CHOICES):
            messages.error(request, 'Plataforma inválida — selecione uma da lista.')
            return rerenderizar()

        if valores['tipo_venda'] not in dict(Devolucao.TIPO_VENDA_CHOICES):
            messages.error(request, 'Tipo de venda inválido.')
            return rerenderizar()

        if Devolucao.objects.filter(numero_pedido=valores['numero_pedido']).exists():
            messages.error(request, f'Já existe uma devolução registrada pro pedido {valores["numero_pedido"]}.')
            return rerenderizar()

        devolucao = Devolucao.objects.create(
            produto=produto,
            nome_plataforma=valores['nome_plataforma'],
            tipo_venda=valores['tipo_venda'],
            numero_pedido=valores['numero_pedido'],
            numero_nota_fiscal=valores['numero_nota_fiscal'],
            nome_cliente=valores['nome_cliente'],
            preco_produto=_parse_decimal_opcional(valores['preco_produto']),
            data_venda=valores['data_venda'],
            data_recebimento_cliente=valores['data_recebimento_cliente'],
            data_reclamacao_cliente=valores['data_reclamacao_cliente'],
            data_recebimento_por_nos=valores['data_recebimento_por_nos'],
            data_abertura_mediacao=_parse_data_opcional(valores['data_abertura_mediacao']),
            data_finalizacao_mediacao=_parse_data_opcional(valores['data_finalizacao_mediacao']),
            reembolsado=_parse_reembolsado(valores['reembolsado']),
            valor_reembolsado=_parse_decimal_opcional(valores['valor_reembolsado']),
            anotacao_mediacao=valores['anotacao_mediacao'],
            motivo_reclamacao=valores['motivo_reclamacao'],
        )

        # * [EXPLICAÇÃO] → fotos que o CLIENTE mandou pra plataforma junto
        #   da reclamação (opcional) — devolucao já existe nesse ponto
        #   (acabou de ser criada acima), então já tem pk garantido pra
        #   associar as fotos.
        for foto in request.FILES.getlist('fotos_cliente'):
            FotoReclamacaoCliente.objects.create(devolucao=devolucao, imagem=foto)

        messages.success(
            request,
            f'Devolução do pedido {devolucao.numero_pedido} criada — pendente de conferência das peças.',
        )
        return redirect('devolucoes_pendentes')

    numero_pedido_ml = request.GET.get('numero_pedido', '').strip()
    if numero_pedido_ml:
        devolucao_existente = Devolucao.objects.filter(numero_pedido=numero_pedido_ml).first()
        if devolucao_existente:
            messages.info(request, f'Já existe uma devolução registrada pro pedido {numero_pedido_ml} — abrindo ela.')
            return redirect('editar_devolucao', devolucao_id=devolucao_existente.id)

        valores = {
            'nome_plataforma': Devolucao.PLATAFORMA_MERCADO_LIVRE,
            'tipo_venda': request.GET.get('tipo_venda', '').strip(),
            'numero_pedido': numero_pedido_ml,
            'numero_nota_fiscal': '',
            'nome_cliente': request.GET.get('nome_cliente', '').strip(),
            'preco_produto': request.GET.get('preco_produto', '').strip(),
            'data_venda': request.GET.get('data_venda', '').strip(),
            'data_recebimento_cliente': request.GET.get('data_recebimento_cliente', '').strip(),
            'data_reclamacao_cliente': request.GET.get('data_reclamacao_cliente', '').strip(),
            'data_recebimento_por_nos': request.GET.get('data_recebimento_por_nos', '').strip(),
            'data_abertura_mediacao': request.GET.get('data_abertura_mediacao', '').strip(),
            'data_finalizacao_mediacao': request.GET.get('data_finalizacao_mediacao', '').strip(),
            'reembolsado': '',
            'valor_reembolsado': '',
            'anotacao_mediacao': '',
            'motivo_reclamacao': '',
        }
        produto_busca_sugerido = request.GET.get('produto_busca', '').strip()
        return render(
            request, 'devolucoes/nova_devolucao.html',
            _contexto_nova_devolucao(valores, busca_produto_sugerida=produto_busca_sugerido),
        )

    return render(request, 'devolucoes/nova_devolucao.html', _contexto_nova_devolucao())


def editar_devolucao(request, devolucao_id):
    """Edição dos dados da Fase 0 de uma devolução já salva (plataforma,
    pedido, cliente, datas, mediação, reclamação do cliente, produto) —
    reaproveita o mesmo template e a mesma validação de nova_devolucao,
    só que atualiza a instância existente em vez de criar uma nova. Não
    mexe na conferência de peças — isso é conferir_devolucao.

    preco_produto/valor_reembolsado seguem a mesma regra de
    nova_devolucao — opcionais, sem puxar nada sozinho aqui (a ponte com
    a API do ML só existe na criação, vinda da tela Consultar Pedido)."""
    devolucao = get_object_or_404(Devolucao, pk=devolucao_id)

    if request.method == 'POST':
        valores = {
            'nome_plataforma': request.POST.get('nome_plataforma', '').strip(),
            'tipo_venda': request.POST.get('tipo_venda', '').strip(),
            'numero_pedido': request.POST.get('numero_pedido', '').strip(),
            'numero_nota_fiscal': request.POST.get('numero_nota_fiscal', '').strip(),
            'nome_cliente': request.POST.get('nome_cliente', '').strip(),
            'preco_produto': request.POST.get('preco_produto', '').strip(),
            'data_venda': request.POST.get('data_venda', '').strip(),
            'data_recebimento_cliente': request.POST.get('data_recebimento_cliente', '').strip(),
            'data_reclamacao_cliente': request.POST.get('data_reclamacao_cliente', '').strip(),
            'data_recebimento_por_nos': request.POST.get('data_recebimento_por_nos', '').strip(),
            'data_abertura_mediacao': request.POST.get('data_abertura_mediacao', '').strip(),
            'data_finalizacao_mediacao': request.POST.get('data_finalizacao_mediacao', '').strip(),
            'reembolsado': request.POST.get('reembolsado', '').strip(),
            'valor_reembolsado': request.POST.get('valor_reembolsado', '').strip(),
            'anotacao_mediacao': request.POST.get('anotacao_mediacao', '').strip(),
            'motivo_reclamacao': request.POST.get('motivo_reclamacao', '').strip(),
        }
        produto_id = request.POST.get('produto_id', '').strip()
        produto = Produto.objects.select_related('marca').filter(pk=produto_id).first() if produto_id else None

        rerenderizar = lambda: render(
            request, 'devolucoes/nova_devolucao.html',
            _contexto_nova_devolucao(valores, produto, devolucao),
        )

        obrigatorios = [
            ('nome_plataforma', 'Plataforma'), ('tipo_venda', 'Tipo de venda'),
            ('numero_pedido', 'Número do pedido'), ('numero_nota_fiscal', 'Número da nota fiscal'),
            ('nome_cliente', 'Nome do cliente'),
            ('data_venda', 'Data da venda'),
            ('data_recebimento_cliente', 'Data de recebimento pelo cliente'),
            ('data_reclamacao_cliente', 'Data da reclamação'),
            ('data_recebimento_por_nos', 'Data de recebimento por nós'),
            ('motivo_reclamacao', 'Motivo da reclamação'),
        ]
        faltando = [rotulo for campo, rotulo in obrigatorios if not valores[campo]]
        if faltando:
            messages.error(request, f'Preencha: {", ".join(faltando)}.')
            return rerenderizar()

        if not produto:
            messages.error(request, 'Selecione um produto pela busca antes de salvar.')
            return rerenderizar()

        if valores['nome_plataforma'] not in dict(Devolucao.PLATAFORMA_CHOICES):
            messages.error(request, 'Plataforma inválida — selecione uma da lista.')
            return rerenderizar()

        if valores['tipo_venda'] not in dict(Devolucao.TIPO_VENDA_CHOICES):
            messages.error(request, 'Tipo de venda inválido.')
            return rerenderizar()

        if Devolucao.objects.exclude(pk=devolucao.pk).filter(numero_pedido=valores['numero_pedido']).exists():
            messages.error(request, f'Já existe uma devolução registrada pro pedido {valores["numero_pedido"]}.')
            return rerenderizar()

        devolucao.produto = produto
        devolucao.nome_plataforma = valores['nome_plataforma']
        devolucao.tipo_venda = valores['tipo_venda']
        devolucao.numero_pedido = valores['numero_pedido']
        devolucao.numero_nota_fiscal = valores['numero_nota_fiscal']
        devolucao.nome_cliente = valores['nome_cliente']
        devolucao.preco_produto = _parse_decimal_opcional(valores['preco_produto'])
        devolucao.data_venda = valores['data_venda']
        devolucao.data_recebimento_cliente = valores['data_recebimento_cliente']
        devolucao.data_reclamacao_cliente = valores['data_reclamacao_cliente']
        devolucao.data_recebimento_por_nos = valores['data_recebimento_por_nos']
        devolucao.data_abertura_mediacao = _parse_data_opcional(valores['data_abertura_mediacao'])
        devolucao.data_finalizacao_mediacao = _parse_data_opcional(valores['data_finalizacao_mediacao'])
        devolucao.reembolsado = _parse_reembolsado(valores['reembolsado'])
        devolucao.valor_reembolsado = _parse_decimal_opcional(valores['valor_reembolsado'])
        devolucao.anotacao_mediacao = valores['anotacao_mediacao']
        devolucao.motivo_reclamacao = valores['motivo_reclamacao']
        devolucao.save()

        # * [EXPLICAÇÃO] → fotos novas que o cliente mandou, anexadas
        #   durante a edição — SOMA às que já existem, nunca substitui;
        #   excluir uma foto existente é uma ação isolada (botão X de
        #   cada foto, ver excluir_foto_reclamacao_cliente).
        for foto in request.FILES.getlist('fotos_cliente'):
            FotoReclamacaoCliente.objects.create(devolucao=devolucao, imagem=foto)

        messages.success(request, f'Devolução do pedido {devolucao.numero_pedido} atualizada.')
        return redirect('devolucoes_pendentes')

    valores = _valores_da_devolucao(devolucao)
    return render(
        request, 'devolucoes/nova_devolucao.html',
        _contexto_nova_devolucao(valores, devolucao.produto, devolucao),
    )


def excluir_devolucao(request, devolucao_id):
    """Exclui a devolução inteira (e em cascata: peças conferidas e fotos
    dela, se já tiver alguma) — usada tanto pra corrigir um cadastro
    feito por engano quanto por uma devolução de teste."""
    devolucao = get_object_or_404(Devolucao, pk=devolucao_id)

    if request.method == 'POST':
        numero_pedido = devolucao.numero_pedido
        devolucao.delete()
        messages.success(request, f'Devolução do pedido {numero_pedido} excluída.')

    return redirect('devolucoes_pendentes')


def _produto_para_busca(produto):
    return {
        'id': produto.id,
        'nome': produto.nome,
        'codigo_barras': produto.codigo_barras,
        'sku': produto.sku or '',
        'marca_nome': produto.marca.nome,
        'foto_url': produto.foto.url if produto.foto else None,
    }


def buscar_produtos_devolucao(request):
    """Busca de produto pra abrir uma nova devolução — aceita tanto
    digitação livre e robusta (várias palavras, em qualquer ordem,
    batendo em nome/SKU/cód. fabricante/marca — ex: 'pulv 9121
    brudden') quanto a leitura direta de um leitor de código de barras
    no mesmo campo: se o termo digitado bate exatamente com um código
    de barras, esse produto volta sozinho e marcado como match_exato,
    pra tela já selecionar ele sem precisar clicar."""
    termo = request.GET.get('q', '').strip()

    if not termo:
        return JsonResponse({'resultados': [], 'match_exato': False})

    match_exato = Produto.objects.select_related('marca').filter(codigo_barras=termo).first()
    if match_exato:
        return JsonResponse({'resultados': [_produto_para_busca(match_exato)], 'match_exato': True})

    produtos = Produto.objects.select_related('marca')
    for token in termo.split():
        produtos = produtos.filter(
            Q(nome__icontains=token)
            | Q(sku__icontains=token)
            | Q(codigo_fabricante__icontains=token)
            | Q(codigo_barras__icontains=token)
            | Q(marca__nome__icontains=token)
        )

    resultados = [_produto_para_busca(produto) for produto in produtos.distinct()[:8]]
    return JsonResponse({'resultados': resultados, 'match_exato': False})


def devolucoes_pendentes(request):
    """Listagem de TODAS as devoluções, organizada em 5 abas que seguem
    o fluxo real do produto (decisão de Matheus, 18/09/2026):
    Aguardando Conferência → Conferidos → Mediações Abertas →
    Mediações Encerradas → Impressos. 'Impressos' é sempre o destino
    final, tanto de quem nunca precisou de mediação (Conferido →
    Impresso direto) quanto de quem precisou (→ Mediação Aberta →
    Mediação Encerrada → Impresso) — não existe caminho de volta, o
    relatório só é marcado como impresso quando o processo já foi
    realmente finalizado. A aba de cada devolução é calculada por
    Devolucao.status_fluxo (ver o model pra regra completa), nunca
    guardada num campo à parte — mesma filosofia de destino_produto/
    ConferenciaPeca.situacao já usada no resto do sistema. A busca e o
    filtro de reembolso (dentro de Mediações Encerradas/Impressos) são
    100% client-side (script_devolucoes_pendentes.js) — o Django já
    manda as 5 listas prontas de uma vez, sem endpoint novo pra buscar."""
    lista = (
        Devolucao.objects.select_related('produto__marca')
        .order_by('-criado_em')
    )

    grupos = {status_valor: [] for status_valor, _ in Devolucao.STATUS_CHOICES}
    for devolucao in lista:
        grupos[devolucao.status_fluxo].append(devolucao)

    contexto = {
        'aguardando_conferencia': grupos[Devolucao.STATUS_AGUARDANDO_CONFERENCIA],
        'conferidos': grupos[Devolucao.STATUS_CONFERIDO],
        'mediacoes_abertas': grupos[Devolucao.STATUS_MEDIACAO_ABERTA],
        'mediacoes_encerradas': grupos[Devolucao.STATUS_MEDIACAO_ENCERRADA],
        'impressos': grupos[Devolucao.STATUS_IMPRESSO],
        'total_devolucoes': len(lista),
        'pagina_ativa': 'devolucoes_pendentes',
    }
    return render(request, 'devolucoes/devolucoes_pendentes.html', contexto)


def marcar_devolucao_impressa(request, devolucao_id):
    """Confirma manualmente que o relatório de 1 devolução já saiu
    impresso de verdade — de propósito NÃO é marcado sozinho quando a
    Ana abre imprimir_relatorio_devolucao, porque às vezes a impressão
    sai errada (papel torto, impressora travou) e ela precisa repetir
    sem que o sistema já tivesse dado como concluído (decisão de
    Matheus, 18/09/2026). Sempre POST, sem tela própria — mesmo padrão
    de excluir_devolucao."""
    devolucao = get_object_or_404(Devolucao, pk=devolucao_id)

    if request.method == 'POST':
        devolucao.relatorio_impresso_em = timezone.now()
        devolucao.save(update_fields=['relatorio_impresso_em'])
        messages.success(request, f'Devolução do pedido {devolucao.numero_pedido} marcada como impressa.')

    return redirect('devolucoes_pendentes')


def _serializar_mediacao(obj, tipo):
    """Normaliza uma Devolucao (em mediação) ou uma MediacaoAvulsa num
    dict com os mesmos campos, pra tela de Mediações ML poder montar 1
    lista só, ordenada junto, sem `if` de tipo espalhado pelo template.
    Só usado pra LISTAGEM — o detalhe de cada mediação usa o objeto real
    direto (ver mediacoes_ml), porque lá o acesso campo a campo já é
    natural."""
    return {
        'tipo': tipo,
        'id': obj.id,
        'claim_id': obj.claim_id,
        'numero_pedido': obj.numero_pedido,
        'nome_cliente': obj.nome_cliente,
        'nome_produto': obj.produto.nome if tipo == 'devolucao' else obj.nome_produto,
        'reembolsado_filtro': obj.reembolsado_filtro,
        'data_abertura_mediacao': obj.data_abertura_mediacao,
        'data_finalizacao_mediacao': obj.data_finalizacao_mediacao,
    }


def mediacoes_ml(request, devolucao_id=None, avulsa_id=None):
    """Painel de acompanhamento de mediações do Mercado Livre (dor da
    Ana: hoje ela acompanha cada mediação aberta numa aba fixada do
    Chrome, 1 por 1). Junta 2 fontes na mesma lista: Devolucao em
    Mediação Aberta/Encerrada (Devolucao.status_fluxo) e MediacaoAvulsa
    (mediação sem devolução registrada aqui — ver o model). Mockup
    aprovado por Matheus, 20/09/2026.

    [ATENÇÃO] → esta é a 2ª etapa da implementação (sidebar + lista real
    + dashboard + detalhe com os dados que já existem hoje). A conversa
    de verdade com o Mercado Livre (busca de mensagens, botões de
    atualizar) e o modal de adicionar mediação manual ainda NÃO estão
    implementados — entram nas próximas etapas.

    Sem sistema de login ainda (só a Ana usa essa tela, direto do PC
    dela — confirmado por Matheus, 20/09/2026), então
    mediacao_visualizada_em é 1 timestamp só por mediação, compartilhado,
    não por usuário.

    [ATENÇÃO] → "Encerradas" aqui exclui quem já foi impresso
    (relatorio_impresso_em preenchido) — uma vez impresso já está
    arquivado de verdade, não faz sentido ocupar espaço nesta tela.
    Decisão tomada nesta implementação, não confirmada com Matheus ainda."""
    devolucoes_abertas = Devolucao.objects.select_related('produto').filter(
        nome_plataforma=Devolucao.PLATAFORMA_MERCADO_LIVRE,
        data_abertura_mediacao__isnull=False,
        data_finalizacao_mediacao__isnull=True,
        relatorio_impresso_em__isnull=True,
    )
    devolucoes_encerradas = Devolucao.objects.select_related('produto').filter(
        nome_plataforma=Devolucao.PLATAFORMA_MERCADO_LIVRE,
        data_finalizacao_mediacao__isnull=False,
        relatorio_impresso_em__isnull=True,
    )
    avulsas_abertas = MediacaoAvulsa.objects.filter(data_finalizacao_mediacao__isnull=True)
    avulsas_encerradas = MediacaoAvulsa.objects.filter(data_finalizacao_mediacao__isnull=False)

    mediacoes_abertas = sorted(
        [_serializar_mediacao(d, 'devolucao') for d in devolucoes_abertas]
        + [_serializar_mediacao(a, 'avulsa') for a in avulsas_abertas],
        key=lambda m: m['data_abertura_mediacao'] or date.min,
        reverse=True,
    )
    mediacoes_encerradas = sorted(
        [_serializar_mediacao(d, 'devolucao') for d in devolucoes_encerradas]
        + [_serializar_mediacao(a, 'avulsa') for a in avulsas_encerradas],
        key=lambda m: m['data_finalizacao_mediacao'] or date.min,
        reverse=True,
    )

    # * [EXPLICACAO] -> categoria (Reclamacao/+Mediacao/+Devolucao/+
    #   Mediacao+Devolucao) de cada item de "Em Acompanhamento" -- so
    #   resolve pra quem ja tem claim_id (casado por uma varredura alguma
    #   vez); quem ainda nao foi casado fica sem badge de categoria
    #   (mostra o badge "Aberta" de sempre) em vez de arriscar uma
    #   classificacao errada -- e continua sempre visivel nos 4 chips
    #   (so item com categoria resolvida e escondido pelo filtro).
    cache_por_claim_id = {
        c.claim_id: c
        for c in ClaimMercadoLivre.objects.filter(
            claim_id__in=[m['claim_id'] for m in mediacoes_abertas if m['claim_id']]
        )
    }
    for item in mediacoes_abertas:
        cache = cache_por_claim_id.get(item['claim_id'])
        item['categoria_slug'] = categoria_slug(cache.dados_brutos.get('stage'), cache.tem_devolucao_fisica) if cache else None

    # * [EXPLICACAO] -> "Encontrados pelo Sistema" -- resultado bruto da
    #   ultima varredura, so o que ainda NAO esta em acompanhamento (quem
    #   ja esta, aparece do lado de "Em Acompanhamento" acima). Nunca
    #   aparece em "Encerradas" -- a varredura so busca status "opened".
    #   Decisao de Matheus, 20/09/2026.
    encontrados = [
        {
            'claim_id': c.claim_id,
            'numero_pedido': c.numero_pedido,
            'categoria_slug': categoria_slug(c.dados_brutos.get('stage'), c.tem_devolucao_fisica),
        }
        for c in ClaimMercadoLivre.objects.filter(esta_acompanhando=False)
    ]

    contagem_encontrados = contagem_por_categoria(encontrados)
    contagem_acompanhamento = contagem_por_categoria(mediacoes_abertas)

    mediacao_selecionada = None
    tipo_selecionado = None
    if devolucao_id:
        # * [EXPLICAÇÃO] → filtro de plataforma também aqui (não só na
        #   lista) — sem isso, dava pra abrir o detalhe de uma devolução
        #   de outra plataforma digitando a URL na mão (20/09/2026).
        mediacao_selecionada = get_object_or_404(
            Devolucao.objects.select_related('produto'),
            pk=devolucao_id, nome_plataforma=Devolucao.PLATAFORMA_MERCADO_LIVRE,
        )
        tipo_selecionado = 'devolucao'
    elif avulsa_id:
        mediacao_selecionada = get_object_or_404(MediacaoAvulsa, pk=avulsa_id)
        tipo_selecionado = 'avulsa'

    mensagens_chat = None
    mensagens_falhou = False
    if mediacao_selecionada:
        # * [EXPLICAÇÃO] → marca como "visualizada agora" só de abrir a
        #   tela — é o gatilho do indicador de mensagem nova (entra na
        #   próxima etapa, quando a mensagem real existir pra comparar).
        mediacao_selecionada.mediacao_visualizada_em = timezone.now()
        mediacao_selecionada.save(update_fields=['mediacao_visualizada_em'])

        # * [EXPLICAÇÃO] → busca síncrona de mensagens toda vez que Ana
        #   abre o chat de um item -- validado em
        #   cronometrar_refresh_individual.py (~0,63s médio, isolado),
        #   decisão de Matheus 20/09/2026: não precisa do mecanismo de
        #   segundo plano usado pelas 2 varreduras, só pro refresh de 1
        #   chat. Sem claim_id ainda (nenhuma varredura casou esse
        #   pedido) não tem como buscar -- fica None mesmo.
        if mediacao_selecionada.claim_id:
            cache_da_conversa = ClaimMercadoLivre.objects.filter(pk=mediacao_selecionada.claim_id).first()
            conta = CONTA_POR_EMPRESA.get(obter_empresa_ativa())
            if cache_da_conversa and conta:
                mensagens_chat, sucesso = atualizar_e_formatar_mensagens(conta, cache_da_conversa, mediacao_selecionada.nome_cliente)
                mensagens_falhou = not sucesso
                if sucesso:
                    mediacao_selecionada.mediacao_atualizada_em = timezone.now()
                    mediacao_selecionada.save(update_fields=['mediacao_atualizada_em'])

    # * [EXPLICAÇÃO] → qual aba abre selecionada — sem isso, clicar numa
    #   mediação Encerrada recarregava a página e voltava pra "Abertas"
    #   por padrão, com o item selecionado escondido na aba errada (bug
    #   real, 20/09/2026).
    aba_ativa = 'encerradas' if mediacao_selecionada and mediacao_selecionada.status_fluxo == 'mediacao_encerrada' else 'abertas'

    contexto = {
        'mediacoes_abertas': mediacoes_abertas,
        'mediacoes_encerradas': mediacoes_encerradas,
        'encontrados': encontrados,
        'contagem_encontrados': contagem_encontrados,
        'contagem_acompanhamento': contagem_acompanhamento,
        'mediacao_selecionada': mediacao_selecionada,
        'tipo_selecionado': tipo_selecionado,
        'aba_ativa': aba_ativa,
        'mensagens_chat': mensagens_chat,
        'mensagens_falhou': mensagens_falhou,
        'pagina_ativa': 'mediacoes_ml',
    }
    return render(request, 'devolucoes/mediacoes_ml.html', contexto)


def adicionar_mediacao_avulsa(request):
    """Cria uma MediacaoAvulsa a partir só do número do pedido — usado
    quando a Ana quer acompanhar uma mediação que ainda não tem
    Devolucao registrada aqui (ver o model). Sempre POST, sem tela
    própria — mesmo padrão de marcar_devolucao_impressa. Confere
    duplicidade nos 2 lugares onde uma mediação pode já existir
    (Devolucao e MediacaoAvulsa) antes de criar, pra não duplicar a
    mesma mediação na lista."""
    if request.method == 'POST':
        numero_pedido = request.POST.get('numero_pedido', '').strip()
        if not numero_pedido:
            messages.error(request, 'Informe o número do pedido.')
        elif Devolucao.objects.filter(numero_pedido=numero_pedido).exists():
            messages.error(request, f'O pedido {numero_pedido} já está registrado como devolução — não precisa adicionar manualmente.')
        elif MediacaoAvulsa.objects.filter(numero_pedido=numero_pedido).exists():
            messages.error(request, f'O pedido {numero_pedido} já está na lista de mediações.')
        else:
            avulsa = MediacaoAvulsa.objects.create(numero_pedido=numero_pedido)
            return redirect('mediacoes_ml_avulsa', avulsa_id=avulsa.id)

    return redirect('mediacoes_ml')


def excluir_mediacao_avulsa(request, avulsa_id):
    """Remove uma mediação avulsa da lista — esse modelo existe só pra
    alimentar esta tela, então excluir o registro aqui não afeta nada
    mais no sistema (diferente de excluir_devolucao, que apaga uma
    devolução de verdade, com peças/fotos etc). Sempre POST, sem tela
    própria — mesmo padrão de excluir_devolucao/adicionar_mediacao_avulsa."""
    avulsa = get_object_or_404(MediacaoAvulsa, pk=avulsa_id)

    if request.method == 'POST':
        numero_pedido = avulsa.numero_pedido
        avulsa.delete()
        messages.success(request, f'Mediação avulsa do pedido {numero_pedido} removida da lista.')

    return redirect('mediacoes_ml')


def iniciar_varredura_mediacoes(request):
    """Dispara em segundo plano a varredura completa (6 meses, empresa
    ativa da sessão) de reclamações abertas na API do Mercado Livre --
    trava contra clique duplo via UPDATE...WHERE atômico (não
    select_for_update()), 1 só por vez entre os 2 botões de varredura.
    Sempre POST, sempre AJAX (a tela faz polling em
    status_varredura_mediacoes enquanto isso roda). Decisão de Matheus,
    20/09/2026 -- ver vault 'Redesenho do Painel de Mediações'."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    linhas = StatusVarreduraMediacoes.objects.filter(pk=1, rodando=False).update(
        rodando=True, tipo_execucao=StatusVarreduraMediacoes.TIPO_COMPLETA,
        fase_atual='Iniciando...', processados=0, total=0, itens_nao_confirmados=0,
        iniciado_em=timezone.now(), finalizado_em=None, erro='',
    )
    if not linhas:
        return JsonResponse({'erro': 'Já existe uma varredura em andamento.'}, status=409)

    empresa = obter_empresa_ativa()
    threading.Thread(target=executar_varredura_completa, args=(empresa,), daemon=True).start()
    return JsonResponse({'ok': True})


def iniciar_atualizacao_acompanhados(request):
    """Mesmo mecanismo de iniciar_varredura_mediacoes, mas só atualiza
    devolução física + mensagens dos itens já marcados
    esta_acompanhando=True (não busca reclamações novas) -- tipicamente
    ~6 itens, no extremo ~25 (dado por Matheus, 20/09/2026)."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    linhas = StatusVarreduraMediacoes.objects.filter(pk=1, rodando=False).update(
        rodando=True, tipo_execucao=StatusVarreduraMediacoes.TIPO_ACOMPANHADOS,
        fase_atual='Iniciando...', processados=0, total=0, itens_nao_confirmados=0,
        iniciado_em=timezone.now(), finalizado_em=None, erro='',
    )
    if not linhas:
        return JsonResponse({'erro': 'Já existe uma varredura em andamento.'}, status=409)

    empresa = obter_empresa_ativa()
    threading.Thread(target=executar_atualizacao_acompanhados, args=(empresa,), daemon=True).start()
    return JsonResponse({'ok': True})


def status_varredura_mediacoes(request):
    """Estado atual (ou da última execução) da varredura de mediações --
    alimenta tanto o polling durante a execução quanto a checagem no
    carregamento da página (pra mostrar o aviso na hora se Ana sair e
    voltar, ou der F5, com uma varredura em andamento). Nunca devolve o
    texto técnico cru de `erro` -- só se existe ou não; a tela sempre
    mostra a mesma mensagem fixa e amigável (decisão de Matheus,
    20/09/2026: ela é usuária comum, nada técnico pra ela)."""
    status = StatusVarreduraMediacoes.objects.filter(pk=1).first()
    if status is None:
        return JsonResponse({'rodando': False, 'tipo_execucao': None, 'fase_atual': None, 'processados': 0, 'total': 0, 'tem_erro': False})

    return JsonResponse({
        'rodando': status.rodando,
        'tipo_execucao': status.tipo_execucao,
        'fase_atual': status.fase_atual,
        'processados': status.processados,
        'total': status.total,
        'itens_nao_confirmados': status.itens_nao_confirmados,
        'tem_erro': bool(status.erro),
    })


def acompanhar_claim(request, claim_id):
    """Caminho manual do mecanismo 'está acompanhando' -- Ana clica
    'Acompanhar' num item de 'Encontrados pelo Sistema'. Cria uma
    MediacaoAvulsa (mesmo padrão de adicionar_mediacao_avulsa) só quando
    o pedido ainda não tem Devolucao nem MediacaoAvulsa cadastrada; se já
    tiver (ex: o casamento automático da varredura chegou primeiro, ou
    ela deixou de acompanhar antes e mudou de ideia), só liga a flag da
    cache de novo, sem duplicar nada. Decisão de Matheus, 20/09/2026."""
    cache = get_object_or_404(ClaimMercadoLivre, pk=claim_id)

    if request.method == 'POST' and not cache.esta_acompanhando:
        ja_existe = (
            Devolucao.objects.filter(numero_pedido=cache.numero_pedido).exists()
            or MediacaoAvulsa.objects.filter(numero_pedido=cache.numero_pedido).exists()
        )
        if not ja_existe:
            conta = CONTA_POR_EMPRESA.get(obter_empresa_ativa())
            nome_cliente, nome_produto = buscar_nome_cliente_e_produto(conta, cache.numero_pedido) if conta else ('', '')
            MediacaoAvulsa.objects.create(
                numero_pedido=cache.numero_pedido,
                claim_id=cache.claim_id,
                nome_cliente=nome_cliente,
                nome_produto=nome_produto,
            )
        cache.esta_acompanhando = True
        cache.save(update_fields=['esta_acompanhando'])
        messages.success(request, f'Pedido {cache.numero_pedido} agora está em acompanhamento.')

    return redirect('mediacoes_ml')


def deixar_de_acompanhar_claim(request, claim_id):
    """Desliga a flag 'está acompanhando' -- sempre não destrutivo (não
    apaga Devolucao/MediacaoAvulsa nem a linha de cache), mesmo mecanismo
    pros 2 tipos de mediação. O 'Excluir mediação avulsa' que já existe
    (excluir_mediacao_avulsa, apaga de vez) continua disponível como ação
    separada, mais forte. Decisão de Matheus, 20/09/2026."""
    cache = get_object_or_404(ClaimMercadoLivre, pk=claim_id)

    if request.method == 'POST':
        cache.esta_acompanhando = False
        cache.save(update_fields=['esta_acompanhando'])
        messages.success(request, f'Pedido {cache.numero_pedido} não está mais em acompanhamento.')

    return redirect('mediacoes_ml')


def _pecas_para_conferencia(devolucao):
    """Monta a lista de peças pra tela de conferência — parte das peças
    ATUALMENTE compatíveis com o produto (Compatibilidade) e sobrepõe
    com o que já foi conferido antes (ConferenciaPeca), se for edição de
    uma conferência já existente. A união com o que já foi conferido é
    de propósito: garante que, ao editar, uma peça que não é mais
    compatível com o produto (cadastro mudou depois) mas já tinha sido
    registrada nessa devolução continue aparecendo — sem sumir dado já
    gravado. quantidade_esperada de uma peça já conferida vem congelada
    dela mesma (ConferenciaPeca), não da Compatibilidade atual — mesma
    ideia documentada no model. 'ja_registrada' é o que o template usa
    pra decidir se pré-marca o toggle Veio/Não veio — uma peça nova
    (nunca conferida) começa sem nenhum dos 2 marcado, pra não sugerir
    uma resposta que ninguém deu ainda. 'fotos' são as fotos de
    evidência já salvas (FotoConferenciaPeca) — uma peça nova não tem
    nenhuma ainda, porque só dá pra anexar foto numa ConferenciaPeca que
    já existe."""
    conferencias_existentes = {
        c.peca_id: c for c in
        devolucao.pecas_conferidas.select_related('peca__marca').prefetch_related('fotos').all()
    }
    compatibilidades = devolucao.produto.compatibilidades.select_related('peca__marca')

    pecas_por_id = {}
    for compat in compatibilidades:
        pecas_por_id[compat.peca_id] = {
            'peca': compat.peca,
            'quantidade_esperada': compat.quantidade_esperada,
            'quantidade_recebida': 0,
            'anotacao': '',
            'ja_registrada': False,
            'fotos': [],
        }
    for peca_id, conferencia in conferencias_existentes.items():
        pecas_por_id[peca_id] = {
            'peca': conferencia.peca,
            'quantidade_esperada': conferencia.quantidade_esperada,
            'quantidade_recebida': conferencia.quantidade_recebida,
            'anotacao': conferencia.anotacao,
            'ja_registrada': True,
            'fotos': list(conferencia.fotos.all()),
    }

    return sorted(pecas_por_id.values(), key=lambda p: p['peca'].nome_generico)


def conferir_devolucao(request, devolucao_id):
    """Tela de conferência de peças — preenchida no celular (Fase 3).
    Reúne as peças a conferir (_pecas_para_conferencia) e deixa marcar
    quantidade recebida + anotação por peça, além do destino final do
    produto e uma observação geral. Serve tanto pra conferir pela 1ª vez
    (destino_produto ainda vazio) quanto pra corrigir uma conferência já
    feita — mesma tela, os dados vêm pré-preenchidos e salvar sobrescreve
    o que já existia (ver 'ja_conferida' no contexto)."""
    devolucao = get_object_or_404(Devolucao.objects.select_related('produto__marca'), pk=devolucao_id)
    ja_conferida = devolucao.destino_produto != ''

    if request.method == 'POST':
        destino_produto = request.POST.get('destino_produto', '').strip()
        observacao_geral = request.POST.get('observacao_geral', '').strip()

        contexto_erro = lambda: render(request, 'devolucoes/conferir_devolucao.html', {
            'devolucao': devolucao,
            'ja_conferida': ja_conferida,
            'pecas': _pecas_para_conferencia(devolucao),
            'destino_choices': Devolucao.DESTINO_CHOICES,
            'fotos_observacao_geral': devolucao.fotos_observacao_geral.all(),
            'modelos_anotacao': list(ModeloAnotacao.objects.values_list('texto', flat=True)),
            'pagina_ativa': 'devolucoes_pendentes',
        })

        if destino_produto not in dict(Devolucao.DESTINO_CHOICES):
            messages.error(request, 'Selecione o destino do produto.')
            return contexto_erro()

        compatibilidades = {c.peca_id: c.quantidade_esperada for c in devolucao.produto.compatibilidades.all()}
        conferencias_existentes = {c.peca_id: c for c in devolucao.pecas_conferidas.all()}
        # peça pode vir tanto de uma Compatibilidade atual quanto de uma
        # ConferenciaPeca já existente (peça que não é mais compatível
        # mas já tinha sido registrada antes) — mesma união feita em
        # _pecas_para_conferencia.
        ids_peca = set(compatibilidades.keys()) | set(conferencias_existentes.keys())

        with transaction.atomic():
            for peca_id in ids_peca:
                conferencia_existente = conferencias_existentes.get(peca_id)
                quantidade_esperada = (
                    conferencia_existente.quantidade_esperada if conferencia_existente
                    else compatibilidades[peca_id]
                )

                try:
                    quantidade_recebida = int(request.POST.get(f'quantidade_recebida_{peca_id}', '0'))
                except ValueError:
                    quantidade_recebida = 0
                quantidade_recebida = max(0, min(quantidade_recebida, quantidade_esperada))

                anotacao = request.POST.get(f'anotacao_{peca_id}', '').strip()

                if conferencia_existente:
                    conferencia_existente.quantidade_recebida = quantidade_recebida
                    conferencia_existente.anotacao = anotacao
                    conferencia_existente.save(update_fields=['quantidade_recebida', 'anotacao'])
                    conferencia = conferencia_existente
                else:
                    conferencia = ConferenciaPeca.objects.create(
                        devolucao=devolucao, peca_id=peca_id,
                        quantidade_esperada=quantidade_esperada,
                        quantidade_recebida=quantidade_recebida,
                        anotacao=anotacao,
                    )

                # * [EXPLICAÇÃO] → funciona tanto na 1ª conferência quanto
                #   numa edição — 'conferencia' aponta pro registro certo
                #   nos 2 casos (recém criado ou já existente), então dá
                #   pra anexar foto logo na 1ª vez, sem precisar salvar a
                #   conferência antes pra só depois anexar foto.
                for foto in request.FILES.getlist(f'fotos_{peca_id}'):
                    FotoConferenciaPeca.objects.create(conferencia=conferencia, imagem=foto)

            # * [EXPLICAÇÃO] → fotos do estado GERAL do produto (não são de
            #   nenhuma peça específica) — complementa observacao_geral,
            #   que antes só aceitava texto. devolucao já existe sempre
            #   nessa tela (criada na Fase 0), então não tem o mesmo
            #   problema de ordem que as fotos por peça têm.
            for foto in request.FILES.getlist('fotos_geral'):
                FotoObservacaoGeral.objects.create(devolucao=devolucao, imagem=foto)

            devolucao.destino_produto = destino_produto
            devolucao.observacao_geral = observacao_geral
            devolucao.save(update_fields=['destino_produto', 'observacao_geral'])

        messages.success(request, f'Conferência do pedido {devolucao.numero_pedido} salva.')
        return redirect('devolucoes_pendentes')

    contexto = {
        'devolucao': devolucao,
        'ja_conferida': ja_conferida,
        'pecas': _pecas_para_conferencia(devolucao),
        'destino_choices': Devolucao.DESTINO_CHOICES,
        'fotos_observacao_geral': devolucao.fotos_observacao_geral.all(),
        'modelos_anotacao': list(ModeloAnotacao.objects.values_list('texto', flat=True)),
        'pagina_ativa': 'devolucoes_pendentes',
    }
    return render(request, 'devolucoes/conferir_devolucao.html', contexto)


def excluir_foto_conferencia(request, foto_id):
    """Exclui 1 foto de evidência tirada durante a conferência de uma
    peça (Objetivo 4) — ação isolada, disparada de dentro da própria
    tela de conferência (cada foto já salva tem seu próprio botão/form
    de excluir). Sempre volta pra tela de conferência da devolução dona
    da foto, tenha dado certo ou não (GET nessa URL só redireciona sem
    fazer nada — a exclusão em si é POST-only)."""
    foto = get_object_or_404(
        FotoConferenciaPeca.objects.select_related('conferencia__devolucao'), pk=foto_id,
    )
    devolucao_id = foto.conferencia.devolucao_id

    if request.method == 'POST':
        foto.delete()
        messages.success(request, 'Foto excluída.')

    return redirect('conferir_devolucao', devolucao_id)


def excluir_foto_observacao_geral(request, foto_id):
    """Exclui 1 foto do estado GERAL do produto (não é de peça nenhuma) —
    mesmo padrão de excluir_foto_conferencia logo acima, só que pra
    FotoObservacaoGeral: ação isolada, POST-only, sempre volta pra tela
    de conferência da devolução dona da foto."""
    foto = get_object_or_404(
        FotoObservacaoGeral.objects.select_related('devolucao'), pk=foto_id,
    )
    devolucao_id = foto.devolucao_id

    if request.method == 'POST':
        foto.delete()
        messages.success(request, 'Foto excluída.')

    return redirect('conferir_devolucao', devolucao_id)


def excluir_foto_reclamacao_cliente(request, foto_id):
    """Exclui 1 foto que o CLIENTE mandou junto da reclamação — mesmo
    padrão das duas exclusões de foto logo acima, só que pra
    FotoReclamacaoCliente: ação isolada, POST-only. Diferente das outras
    2, volta pra tela de Editar Devolução (não pra Conferência) — é lá
    que essas fotos aparecem, dentro do bloco "Reclamação do cliente"."""
    foto = get_object_or_404(
        FotoReclamacaoCliente.objects.select_related('devolucao'), pk=foto_id,
    )
    devolucao_id = foto.devolucao_id

    if request.method == 'POST':
        foto.delete()
        messages.success(request, 'Foto excluída.')

    return redirect('editar_devolucao', devolucao_id)


def visualizar_devolucao(request, devolucao_id):
    """Tela de consulta — só leitura, pensada pra quem só precisa checar o
    que foi feito na conferência ou pegar as fotos de evidência pra
    mediação com a plataforma (dor da Ana), sem precisar entrar na tela
    de edição (conferir_devolucao) nem reabrir o relatório A4.

    Mostra as fotos de FotoConferenciaPeca (evidência da conferência)
    agrupadas por peça, as fotos de FotoObservacaoGeral (estado geral do
    produto, sem ser de peça nenhuma — ex: produto recebido já montado)
    e as fotos de FotoReclamacaoCliente (as que o CLIENTE mandou junto
    da reclamação, anexadas em Nova/Editar Devolução) — nunca a foto de
    catálogo da Peca. [ATENÇÃO] → decisão de Matheus, 19/09/2026: fotos
    do cliente raramente vão ser usadas pra mediação, mas é melhor ter
    aqui e não precisar do que precisar e não ter — por isso aparecem
    aqui também, revertendo uma decisão anterior de deixar de fora.

    [ATENÇÃO] → reorganização de 19/09/2026 (mockup aprovado às 22:11):
    o template agora separa 2 blocos com o MESMO dado de pecas_conferidas
    mas propósitos diferentes — "Evidência pra mediação" junta fotos de
    TODAS as peças com problema num grid só, sem separar por peça
    (mediação do Mercado Livre funciona como chat: anexa tudo de uma vez,
    não precisa vincular foto a peça), e "Resumo geral da conferência"
    mostra cada peça com seu próprio card (aí sim agrupado por peça,
    reaproveitando o mesmo visual do Relatório A4). pecas_com_problema é
    o pré-filtro (ver eh_evidencia_de_problema em ConferenciaPeca) que
    alimenta só o 1º bloco.
    """
    devolucao = get_object_or_404(
        Devolucao.objects.select_related('produto'), pk=devolucao_id,
    )
    pecas_conferidas = (
        devolucao.pecas_conferidas
        .select_related('peca')
        .prefetch_related('fotos')
    )
    # * [EXPLICAÇÃO] → pré-filtra as peças com problema (não veio,
    #   incompleta, ou completa mas com anotação) pra alimentar o bloco
    #   "Evidência pra mediação" — evita repetir esse filtro 2x dentro do
    #   template (fotos + lista de anotações) e deixa fácil detectar o
    #   caso "sem evidência nenhuma" (mockup aprovado por Matheus,
    #   19/09/2026 22:11). Iterar a queryset aqui já popula o cache
    #   dela — o for do template reaproveita, sem consulta 2x.
    pecas_com_problema = [c for c in pecas_conferidas if c.eh_evidencia_de_problema]
    return render(request, 'devolucoes/visualizar_devolucao.html', {
        'devolucao': devolucao,
        'pecas_conferidas': pecas_conferidas,
        'pecas_com_problema': pecas_com_problema,
        'fotos_observacao_geral': devolucao.fotos_observacao_geral.all(),
        'fotos_reclamacao_cliente': devolucao.fotos_reclamacao_cliente.all(),
    })


def abrir_pasta_conferencia(request, devolucao_id):
    """Abre a pasta das fotos de conferência dessa devolução direto no
    Explorer do Windows — só funciona porque o servidor Django roda no
    mesmo computador de quem clica (é um app local, nunca um servidor
    remoto/compartilhado — ver settings.DADOS_DIR), então disparar o
    Explorer aqui abre na tela de quem clicou, nunca em outra máquina.

    [ATENÇÃO] → específico de Windows de propósito (comando "explorer"),
    já que é a única plataforma onde esse sistema roda de verdade (ver
    gerar_exe.py).
    """
    devolucao = get_object_or_404(Devolucao, pk=devolucao_id)
    pedido_slug = slugify(devolucao.numero_pedido) or str(devolucao.pk)

    raiz_media = Path(settings.MEDIA_ROOT).resolve()
    pasta = (raiz_media / f'Devoluções/Pedido_{pedido_slug}/Fotos da conferencia').resolve()

    if raiz_media != pasta and raiz_media not in pasta.parents:
        messages.error(request, 'Caminho de pasta inválido.')
        return redirect('visualizar_devolucao', devolucao_id)

    if not pasta.exists():
        messages.warning(request, 'Essa devolução ainda não tem fotos de conferência salvas nessa pasta.')
        return redirect('visualizar_devolucao', devolucao_id)

    subprocess.Popen(['explorer', str(pasta)])
    return redirect('visualizar_devolucao', devolucao_id)


def produtos(request):
    """Lista todos os produtos agrupados por Marca/Grupo Fornecedor —
    marca sem grupo vira uma seção própria; marca com grupo fica dentro
    da seção do grupo dela. A busca em si (Nome/SKU/EAN/Cód. Fabricante/
    Marca) é só client-side, feita pelo script_produtos.js."""
    lista_produtos = (
        Produto.objects.select_related('marca__grupo_fornecedor')
        .order_by('marca__nome', 'nome')
    )

    grupos_por_id = {}
    marcas_sem_grupo_por_id = {}

    for produto in lista_produtos:
        marca = produto.marca
        grupo = marca.grupo_fornecedor

        if grupo:
            grupo_entry = grupos_por_id.setdefault(grupo.id, {'grupo': grupo, 'marcas_por_id': {}})
            marca_entry = grupo_entry['marcas_por_id'].setdefault(marca.id, {'marca': marca, 'produtos': []})
        else:
            marca_entry = marcas_sem_grupo_por_id.setdefault(marca.id, {'marca': marca, 'produtos': []})

        marca_entry['produtos'].append(produto)

    grupos = sorted(
        (
            {
                'grupo': g['grupo'],
                'marcas': sorted(g['marcas_por_id'].values(), key=lambda m: m['marca'].nome.lower()),
            }
            for g in grupos_por_id.values()
        ),
        key=lambda g: g['grupo'].nome.lower(),
    )
    marcas_sem_grupo = sorted(marcas_sem_grupo_por_id.values(), key=lambda m: m['marca'].nome.lower())

    contexto = {
        'marcas_sem_grupo': marcas_sem_grupo,
        'grupos': grupos,
        'tem_produtos': bool(grupos_por_id or marcas_sem_grupo_por_id),
        'pagina_ativa': 'produtos',
    }
    return render(request, 'devolucoes/produtos.html', contexto)


def _contexto_form_produto(produto=None, valores=None):
    """Monta o contexto da tela de cadastro/edição de produto — usada
    tanto pra 'Novo produto' (GET simples) quanto pra 'Editar produto'
    (GET com produto já preenchido), e também pra re-exibir o formulário
    com o que a pessoa digitou quando a validação falha. Só os campos do
    produto em si — peça vinculada não aparece mais aqui, isso ficou pra
    visualizar_produto (visualização) e vincular_pecas_produto (a tela
    dedicada de vincular/desvincular)."""
    if valores is None:
        if produto:
            valores = {
                'nome': produto.nome,
                'codigo_barras': produto.codigo_barras,
                'sku': produto.sku or '',
                'codigo_fabricante': produto.codigo_fabricante or '',
                'marca_id': produto.marca_id,
                'marca_nome': produto.marca.nome if produto.marca else '',
            }
        else:
            valores = {
                'nome': '', 'codigo_barras': '', 'sku': '',
                'codigo_fabricante': '', 'marca_id': '', 'marca_nome': '',
            }

    return {
        'produto': produto,
        'valores': valores,
        'marcas_json': _marcas_json(),
        'grupos': GrupoFornecedor.objects.all(),
        'pagina_ativa': 'produtos',
    }

def _criar_marca(nome, grupo_id):
    """Cria (ou reaproveita, se já existir) uma Marca. Usada tanto pelo
    endpoint AJAX da tela de produto quanto pelo formulário comum da
    tela de Marcas e Grupos Fornecedores."""
    nome = nome.strip()
    if not nome:
        return None, 'Nome da marca é obrigatório.'

    grupo = GrupoFornecedor.objects.filter(pk=grupo_id).first() if grupo_id else None
    marca, _ = Marca.objects.get_or_create(nome=nome, defaults={'grupo_fornecedor': grupo})
    return marca, None


def _criar_grupo_fornecedor(nome):
    """Cria (ou reaproveita) um Grupo Fornecedor — mesma ideia de
    _criar_marca, usada nos 2 lugares que cadastram grupo."""
    nome = nome.strip()
    if not nome:
        return None, 'Nome do grupo é obrigatório.'

    grupo, _ = GrupoFornecedor.objects.get_or_create(nome=nome)
    return grupo, None


def _marcas_json():
    """JSON com todas as Marcas cadastradas, pro widget de seletor de
    marca (reaproveitado em Produto e Peça — ver script_marca_widget.js).
    Vai pro template como atributo data-marcas de um elemento HTML; o
    widget nunca lê marca de variável JS global, só do próprio DOM."""
    marcas = Marca.objects.select_related('grupo_fornecedor')
    return json.dumps([
        {
            'id': marca.id,
            'nome': marca.nome,
            'grupo': marca.grupo_fornecedor.nome if marca.grupo_fornecedor else None,
        }
        for marca in marcas
    ])

def _agrupar_pecas_por_marca_grupo(pecas):
    """Agrupa uma lista/queryset de Peca por Grupo Fornecedor/Marca — marca
    sem grupo vira uma seção própria; marca com grupo fica dentro da seção
    do grupo dela. Extraído de dentro de gaveta_pecas() pra também ser
    reaproveitado por vincular_pecas_produto() — as 2 telas mostram a
    mesma visão agrupada do catálogo de peças (a 2ª com um subconjunto
    marcado como já vinculado ao produto em questão). Retorna
    (grupos, marcas_sem_grupo, tem_pecas)."""
    grupos_por_id = {}
    marcas_sem_grupo_por_id = {}

    for peca in pecas:
        marca = peca.marca
        grupo = marca.grupo_fornecedor

        if grupo:
            grupo_entry = grupos_por_id.setdefault(grupo.id, {'grupo': grupo, 'marcas_por_id': {}})
            marca_entry = grupo_entry['marcas_por_id'].setdefault(marca.id, {'marca': marca, 'pecas': []})
        else:
            marca_entry = marcas_sem_grupo_por_id.setdefault(marca.id, {'marca': marca, 'pecas': []})

        marca_entry['pecas'].append(peca)

    grupos = sorted(
        (
            {
                'grupo': g['grupo'],
                'marcas': sorted(g['marcas_por_id'].values(), key=lambda m: m['marca'].nome.lower()),
            }
            for g in grupos_por_id.values()
        ),
        key=lambda g: g['grupo'].nome.lower(),
    )
    marcas_sem_grupo = sorted(marcas_sem_grupo_por_id.values(), key=lambda m: m['marca'].nome.lower())

    return grupos, marcas_sem_grupo, bool(grupos_por_id or marcas_sem_grupo_por_id)


def cadastrar_grupo_fornecedor(request):
    """Endpoint AJAX (JSON) — chamado de dentro da tela de produto."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    grupo, erro = _criar_grupo_fornecedor(request.POST.get('nome', ''))
    if erro:
        return JsonResponse({'erro': erro}, status=400)

    return JsonResponse({'id': grupo.id, 'nome': grupo.nome})


def cadastrar_marca(request):
    """Endpoint AJAX (JSON) — chamado de dentro da tela de produto."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    marca, erro = _criar_marca(request.POST.get('nome', ''), request.POST.get('grupo_fornecedor_id', '').strip())
    if erro:
        return JsonResponse({'erro': erro}, status=400)

    return JsonResponse({
        'id': marca.id,
        'nome': marca.nome,
        'grupo': {'id': marca.grupo_fornecedor.id, 'nome': marca.grupo_fornecedor.nome} if marca.grupo_fornecedor else None,
    })


def cadastrar_produto(request):
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        codigo_barras = request.POST.get('codigo_barras', '').strip()
        sku = request.POST.get('sku', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        marca_id = request.POST.get('marca_id', '').strip()
        foto = request.FILES.get('foto')

        valores_digitados = {
            'nome': nome, 'codigo_barras': codigo_barras,
            'sku': sku, 'codigo_fabricante': codigo_fabricante,
            'marca_id': marca_id,
            'marca_nome': Marca.objects.filter(pk=marca_id).values_list('nome', flat=True).first() or '' if marca_id else '',
        }
        rerenderizar = lambda: render(request, 'devolucoes/produto_form.html', _contexto_form_produto(valores=valores_digitados))

        if not (nome and codigo_barras and marca_id):
            messages.error(request, 'Nome, Marca e EAN são obrigatórios.')
            return rerenderizar()

        marca = Marca.objects.filter(pk=marca_id).first()
        if not marca:
            messages.error(request, 'Marca inválida — selecione uma marca da lista.')
            return rerenderizar()

        if Produto.objects.filter(codigo_barras=codigo_barras).exists():
            messages.error(request, f'Já existe um produto cadastrado com o código de barras {codigo_barras}.')
            return rerenderizar()

        if sku and Produto.objects.filter(sku=sku).exists():
            messages.error(request, f'Já existe um produto cadastrado com o SKU {sku}.')
            return rerenderizar()

        if codigo_fabricante and Produto.objects.filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe um produto cadastrado com o código do fabricante {codigo_fabricante}.')
            return rerenderizar()

        produto = Produto.objects.create(
            codigo_barras=codigo_barras, nome=nome, marca=marca,
            sku=sku or None, codigo_fabricante=codigo_fabricante or None, foto=foto,
        )
        messages.success(request, f'Produto "{nome}" cadastrado.')
        return redirect('visualizar_produto', produto_id=produto.id)

    return render(request, 'devolucoes/produto_form.html', _contexto_form_produto())


def visualizar_produto(request, produto_id):
    """Tela de visualização do produto — só leitura. É o "hub" do fluxo:
    mostra os dados do produto e a lista de peças vinculadas, e de lá
    partem as 3 ações irmãs (Editar produto / Vincular peças / Excluir
    produto). Vincular e desvincular peça não acontece mais aqui —
    virou responsabilidade exclusiva de vincular_pecas_produto."""
    produto = get_object_or_404(Produto, pk=produto_id)
    compatibilidades = produto.compatibilidades.select_related('peca__marca').order_by('peca__nome_generico')

    contexto = {
        'produto': produto,
        'compatibilidades': compatibilidades,
        'pagina_ativa': 'produtos',
    }
    return render(request, 'devolucoes/produto_visualizar.html', contexto)


def editar_produto(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        codigo_barras = request.POST.get('codigo_barras', '').strip()
        sku = request.POST.get('sku', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        marca_id = request.POST.get('marca_id', '').strip()
        foto = request.FILES.get('foto')

        valores_digitados = {
            'nome': nome, 'codigo_barras': codigo_barras,
            'sku': sku, 'codigo_fabricante': codigo_fabricante,
            'marca_id': marca_id,
            'marca_nome': Marca.objects.filter(pk=marca_id).values_list('nome', flat=True).first() or '' if marca_id else '',
        }
        rerenderizar = lambda: render(request, 'devolucoes/produto_form.html', _contexto_form_produto(produto, valores_digitados))

        if not (nome and codigo_barras and marca_id):
            messages.error(request, 'Nome, Marca e EAN são obrigatórios.')
            return rerenderizar()

        marca = Marca.objects.filter(pk=marca_id).first()
        if not marca:
            messages.error(request, 'Marca inválida — selecione uma marca da lista.')
            return rerenderizar()

        if Produto.objects.exclude(pk=produto.pk).filter(codigo_barras=codigo_barras).exists():
            messages.error(request, f'Já existe outro produto com o código de barras {codigo_barras}.')
            return rerenderizar()

        if sku and Produto.objects.exclude(pk=produto.pk).filter(sku=sku).exists():
            messages.error(request, f'Já existe outro produto com o SKU {sku}.')
            return rerenderizar()

        if codigo_fabricante and Produto.objects.exclude(pk=produto.pk).filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe outro produto com o código do fabricante {codigo_fabricante}.')
            return rerenderizar()

        produto.marca = marca
        produto.nome = nome
        produto.codigo_barras = codigo_barras
        produto.sku = sku or None
        produto.codigo_fabricante = codigo_fabricante or None
        if foto:
            produto.foto = foto
        produto.save()
        messages.success(request, 'Dados do produto atualizados.')
        return redirect('visualizar_produto', produto_id=produto.id)

    return render(request, 'devolucoes/produto_form.html', _contexto_form_produto(produto))


def excluir_produto(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        nome = produto.nome
        produto.delete()
        messages.success(request, f'Produto "{nome}" excluído.')

    return redirect('produtos')


def buscar_pecas(request, produto_id):
    """[ATENÇÃO] → Não é mais chamada por nenhum fluxo da tela de produto
    (o antigo Modal de Vínculo do lado do produto saiu de cena no
    Objetivo 0). Mantida só porque _modal_vinculo.html — componente
    compartilhado, ainda ativo no lado da peça (Gaveta de Peças,
    abrirComPeca) — referencia essa URL incondicionalmente; removê-la
    quebraria o render da Gaveta. Decisão de manter, não de limpar,
    nesta rodada."""
    termo = request.GET.get('q', '').strip()

    resultados = []
    if len(termo) >= 2:
        pecas = (
            Peca.objects.filter(nome_generico__icontains=termo)
            .exclude(compatibilidades__produto_id=produto_id)
            .prefetch_related('compatibilidades__produto')[:8]
        )

        for peca in pecas:
            resultados.append({
                'id': peca.id,
                'nome': peca.nome_generico,
                'foto_url': peca.imagem.url if peca.imagem else None,
                'usada_em': [c.produto.nome for c in peca.compatibilidades.all()],
            })

    return JsonResponse({'resultados': resultados})


def _ler_quantidade_do_post(request, peca_id):
    """Lê o campo quantidade_<id> do POST de vincular_pecas_produto — cada
    peça da grade tem o seu próprio campo de quantidade, então não dá pra
    usar request.POST.get('quantidade_esperada') fixo como nas telas de
    peça única. Cai pra 1 se vier vazio/inválido (input number no HTML já
    evita isso na prática, isso aqui é só a rede de segurança do
    servidor)."""
    try:
        valor = int(request.POST.get(f'quantidade_{peca_id}', '1'))
    except (TypeError, ValueError):
        valor = 1
    return max(1, valor)


def vincular_pecas_produto(request, produto_id):
    """Tela dedicada de vincular/desvincular peças de um produto —
    substitui o antigo Modal de Vínculo do lado do produto (Objetivo 0).
    Reaproveita a mesma visão agrupada por Grupo Fornecedor/Marca da
    Gaveta de Peças (_agrupar_pecas_por_marca_grupo), mas aqui cada peça
    vem marcada com ja_vinculada/quantidade_vinculada — o card já nasce
    marcado (checkbox) se a peça já é compatível com este produto.

    É um formulário clássico só, sem AJAX: marcar uma peça nova = vincular,
    desmarcar uma já vinculada = desvincular, mudar o número da quantidade
    = atualiza. Um "Salvar vínculos" só aplica a diferença toda de uma vez,
    dentro de uma transação — funciona inteiro mesmo com JS desligado (a
    busca/filtro da tela é que são só enfeite client-side)."""
    produto = get_object_or_404(Produto, pk=produto_id)

    if request.method == 'POST':
        ids_selecionados = {
            int(valor) for valor in request.POST.getlist('peca_id') if valor.isdigit()
        }
        vinculos_atuais = {c.peca_id: c for c in produto.compatibilidades.all()}
        ids_atuais = set(vinculos_atuais.keys())

        ids_para_desvincular = ids_atuais - ids_selecionados
        ids_para_vincular = ids_selecionados - ids_atuais
        ids_para_atualizar = ids_selecionados & ids_atuais

        with transaction.atomic():
            if ids_para_desvincular:
                Compatibilidade.objects.filter(produto=produto, peca_id__in=ids_para_desvincular).delete()

            for peca_id in ids_para_vincular:
                Compatibilidade.objects.create(
                    produto=produto, peca_id=peca_id,
                    quantidade_esperada=_ler_quantidade_do_post(request, peca_id),
                )

            for peca_id in ids_para_atualizar:
                nova_quantidade = _ler_quantidade_do_post(request, peca_id)
                compatibilidade = vinculos_atuais[peca_id]
                if compatibilidade.quantidade_esperada != nova_quantidade:
                    compatibilidade.quantidade_esperada = nova_quantidade
                    compatibilidade.save(update_fields=['quantidade_esperada'])

        messages.success(request, 'Vínculos de peças atualizados.')
        return redirect('visualizar_produto', produto_id=produto.id)

    vinculos = {c.peca_id: c.quantidade_esperada for c in produto.compatibilidades.all()}
    pecas = Peca.objects.select_related('marca__grupo_fornecedor').order_by('nome_generico')
    for peca in pecas:
        peca.ja_vinculada = peca.id in vinculos
        peca.quantidade_vinculada = vinculos.get(peca.id, 1)

    pecas_grupos, pecas_marcas_sem_grupo, tem_pecas = _agrupar_pecas_por_marca_grupo(pecas)

    contexto = {
        'produto': produto,
        'pecas_grupos': pecas_grupos,
        'pecas_marcas_sem_grupo': pecas_marcas_sem_grupo,
        'tem_pecas': tem_pecas,
        'qtd_vinculada_inicial': len(vinculos),
        'marcas': Marca.objects.all(),
        'pagina_ativa': 'produtos',
    }
    return render(request, 'devolucoes/produto_vincular_pecas.html', contexto)


def cadastrar_peca_avulsa(request):
    if request.method == 'POST':
        nome_generico = request.POST.get('nome', '').strip()
        nome_tecnico = request.POST.get('nome_tecnico', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        marca_id = request.POST.get('marca_id', '').strip()
        imagem = request.FILES.get('imagem')

        if not nome_generico:
            messages.error(request, 'Nome da peça é obrigatório.')
            return redirect('gaveta_pecas')

        if not imagem:
            messages.error(request, 'Foto da peça é obrigatória.')
            return redirect('gaveta_pecas')

        if not marca_id:
            messages.error(request, 'Marca é obrigatória — selecione uma marca da lista.')
            return redirect('gaveta_pecas')

        marca = Marca.objects.filter(pk=marca_id).first()
        if not marca:
            messages.error(request, 'Marca inválida — selecione uma marca da lista.')
            return redirect('gaveta_pecas')

        if codigo_fabricante and Peca.objects.filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe uma peça cadastrada com o código do fabricante {codigo_fabricante}.')
            return redirect('gaveta_pecas')

        Peca.objects.create(
            nome_generico=nome_generico,
            nome_tecnico=nome_tecnico or '',
            codigo_fabricante=codigo_fabricante or None,
            marca=marca,
            imagem=imagem,
        )
        messages.success(request, f'Peça "{nome_generico}" cadastrada — ainda sem produto vinculado. Vincule ela depois pela busca dentro de um produto.')

    return redirect('gaveta_pecas')


def desvincular_peca(request, compatibilidade_id):
    """Desfaz o vínculo peça-produto — usado pelo card expandido da Gaveta
    de Peças (POST via AJAX, com resposta em JSON, pra atualizar o card na
    hora). Do lado do produto, desvincular virou responsabilidade
    exclusiva de vincular_pecas_produto (desmarcar o checkbox da peça) —
    esta view não é mais chamada de lá, então o fallback sem JS volta pra
    Gaveta de Peças, de onde o form realmente vem."""
    compatibilidade = get_object_or_404(Compatibilidade, pk=compatibilidade_id)
    produto_id = compatibilidade.produto_id

    if request.method == 'POST':
        eh_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        nome_peca = compatibilidade.peca.nome_generico
        peca_id = compatibilidade.peca_id
        compatibilidade.delete()

        if eh_ajax:
            return JsonResponse({
                'peca_id': peca_id,
                'produto_id': produto_id,
                'qtd_produtos_vinculados': Peca.objects.get(pk=peca_id).compatibilidades.count(),
            })

        messages.success(request, f'"{nome_peca}" desvinculada deste produto.')

    return redirect('gaveta_pecas')


def excluir_peca(request, peca_id):
    """Exclui a peça — reaproveitado tanto pelo card na tela de produto
    (POST clássico, com redirect) quanto pelo card na Gaveta de Peças
    (POST via AJAX, com resposta em JSON, pra sumir da grade sem
    recarregar a página). O fallback não-AJAX volta pra Gaveta de Peças
    — a peça já não pertence mais a uma tela de produto específica."""
    peca = get_object_or_404(Peca, pk=peca_id)

    if request.method == 'POST':
        eh_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        nome = peca.nome_generico
        peca.delete()

        if eh_ajax:
            return JsonResponse({'id': peca_id, 'nome': nome})

        messages.success(request, f'Peça "{nome}" excluída do sistema.')

    return redirect('gaveta_pecas')


def _contexto_form_peca(peca=None, valores=None):
    """Monta o contexto da tela de edição de peça — só 'Editar peça'
    existe por enquanto (cadastro acontece dentro do produto ou na
    tela/painel de peça avulsa, não aqui)."""
    if valores is None:
        valores = {
            'nome': peca.nome_generico,
            'nome_tecnico': peca.nome_tecnico,
            'codigo_fabricante': peca.codigo_fabricante,
            'marca_id': peca.marca_id or '',
            'marca_nome': peca.marca.nome if peca.marca else '',
        }

    return {
        'peca': peca,
        'valores': valores,
        'qtd_produtos_vinculados': peca.compatibilidades.count(),
        'marcas_json': _marcas_json(),
        'grupos': GrupoFornecedor.objects.all(),
        'pagina_ativa': 'gaveta_pecas',
    }

def editar_peca(request, peca_id):
    peca = get_object_or_404(Peca, pk=peca_id)

    if request.method == 'POST':
        nome_generico = request.POST.get('nome', '').strip()
        nome_tecnico = request.POST.get('nome_tecnico', '').strip()
        codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
        marca_id = request.POST.get('marca_id', '').strip()
        imagem = request.FILES.get('imagem')

        valores_digitados = {
            'nome': nome_generico, 'nome_tecnico': nome_tecnico, 'codigo_fabricante': codigo_fabricante,
            'marca_id': marca_id,
            'marca_nome': Marca.objects.filter(pk=marca_id).values_list('nome', flat=True).first() or '' if marca_id else '',
        }
        rerenderizar = lambda: render(request, 'devolucoes/peca_form.html', _contexto_form_peca(peca, valores_digitados))

        if not nome_generico:
            messages.error(request, 'Nome da peça é obrigatório.')
            return rerenderizar()

        if not marca_id:
            messages.error(request, 'Marca é obrigatória — selecione uma marca da lista.')
            return rerenderizar()

        marca = Marca.objects.filter(pk=marca_id).first()
        if not marca:
            messages.error(request, 'Marca inválida — selecione uma marca da lista.')
            return rerenderizar()

        if codigo_fabricante and Peca.objects.exclude(pk=peca.pk).filter(codigo_fabricante=codigo_fabricante).exists():
            messages.error(request, f'Já existe outra peça com o código do fabricante {codigo_fabricante}.')
            return rerenderizar()

        peca.marca = marca
        peca.nome_generico = nome_generico
        peca.nome_tecnico = nome_tecnico
        peca.codigo_fabricante = codigo_fabricante or None
        if imagem:
            peca.imagem = imagem
        peca.save()
        messages.success(request, 'Dados da peça atualizados.')
        return redirect('gaveta_pecas')

    return render(request, 'devolucoes/peca_form.html', _contexto_form_peca(peca))


def gaveta_pecas(request):
    """Tela própria de Peça — objeto autossuficiente, com CRUD completo
    independente de vínculo. A busca/filtro (nome, marca, status) é
    client-side, feita por script_gaveta_pecas.js — mesmo padrão já
    usado em produtos() e marcas_grupos().

    Os cards vêm agrupados por Grupo Fornecedor/Marca — mesma lógica de
    agrupamento de produtos() (marca sem grupo vira seção própria; marca
    com grupo fica dentro da seção do grupo dela), só que aqui cada marca
    virou um carrossel horizontal em vez de uma fileira só. Os nomes das
    chaves de contexto são "pecas_..." pra não colidir com 'grupos' (a
    lista simples de GrupoFornecedor que já ia pro <select> de "novo
    grupo" dentro do Modal de Peça — ver _modal_peca.html)."""
    pecas = (
        Peca.objects.select_related('marca__grupo_fornecedor')
        .prefetch_related('compatibilidades__produto')
        .annotate(qtd_produtos_vinculados=Count('compatibilidades', distinct=True))
        .order_by('nome_generico')
    )

    pecas_grupos, pecas_marcas_sem_grupo, tem_pecas = _agrupar_pecas_por_marca_grupo(pecas)

    contexto = {
        'pecas_grupos': pecas_grupos,
        'pecas_marcas_sem_grupo': pecas_marcas_sem_grupo,
        'tem_pecas': tem_pecas,
        'marcas': Marca.objects.all(),
        'marcas_json': _marcas_json(),
        'grupos': GrupoFornecedor.objects.all(),
        'pagina_ativa': 'gaveta_pecas',
    }
    return render(request, 'devolucoes/gaveta_pecas.html', contexto)


def cadastrar_peca_gaveta(request):
    """Endpoint AJAX (JSON) — cadastro de peça pelo Modal de Peça na
    Gaveta. Toda peça nasce avulsa aqui; vincular a um produto é uma
    ação separada e posterior (Objetivo 2)."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    nome_generico = request.POST.get('nome', '').strip()
    nome_tecnico = request.POST.get('nome_tecnico', '').strip()
    codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
    marca_id = request.POST.get('marca_id', '').strip()
    imagem = request.FILES.get('imagem')

    if not nome_generico:
        return JsonResponse({'erro': 'Nome da peça é obrigatório.', 'campo': 'nome'}, status=400)

    if not imagem:
        return JsonResponse({'erro': 'Foto da peça é obrigatória.', 'campo': 'imagem'}, status=400)

    if not marca_id:
        return JsonResponse({'erro': 'Marca é obrigatória — selecione uma marca da lista.', 'campo': 'marca'}, status=400)

    marca = Marca.objects.filter(pk=marca_id).first()
    if not marca:
        return JsonResponse({'erro': 'Marca inválida — selecione uma marca da lista.', 'campo': 'marca'}, status=400)

    if codigo_fabricante and Peca.objects.filter(codigo_fabricante=codigo_fabricante).exists():
        return JsonResponse({
            'erro': f'Já existe uma peça cadastrada com o código do fabricante {codigo_fabricante}.',
            'campo': 'codigo_fabricante',
        }, status=400)

    peca = Peca.objects.create(
        nome_generico=nome_generico,
        nome_tecnico=nome_tecnico or '',
        codigo_fabricante=codigo_fabricante or None,
        marca=marca,
        imagem=imagem,
    )

    return JsonResponse({
        'id': peca.id,
        'nome': peca.nome_generico,
        'nome_tecnico': peca.nome_tecnico,
        'codigo_fabricante': peca.codigo_fabricante or '',
        'marca_id': peca.marca_id,
        'marca_nome': peca.marca.nome,
        'marca_grupo': peca.marca.grupo_fornecedor.nome if peca.marca.grupo_fornecedor else None,
        'imagem_url': peca.imagem.url if peca.imagem else None,
        'qtd_produtos_vinculados': 0,
    })


def editar_peca_gaveta(request, peca_id):
    """Endpoint AJAX (JSON) — edição de peça pelo Modal de Peça na
    Gaveta. Mesma validação de editar_peca (tela própria antiga), só
    que devolve JSON em vez de re-renderizar a página inteira."""
    peca = get_object_or_404(Peca, pk=peca_id)

    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    nome_generico = request.POST.get('nome', '').strip()
    nome_tecnico = request.POST.get('nome_tecnico', '').strip()
    codigo_fabricante = request.POST.get('codigo_fabricante', '').strip()
    marca_id = request.POST.get('marca_id', '').strip()
    imagem = request.FILES.get('imagem')

    if not nome_generico:
        return JsonResponse({'erro': 'Nome da peça é obrigatório.', 'campo': 'nome'}, status=400)

    if not marca_id:
        return JsonResponse({'erro': 'Marca é obrigatória — selecione uma marca da lista.', 'campo': 'marca'}, status=400)

    marca = Marca.objects.filter(pk=marca_id).first()
    if not marca:
        return JsonResponse({'erro': 'Marca inválida — selecione uma marca da lista.', 'campo': 'marca'}, status=400)

    if codigo_fabricante and Peca.objects.exclude(pk=peca.pk).filter(codigo_fabricante=codigo_fabricante).exists():
        return JsonResponse({
            'erro': f'Já existe outra peça com o código do fabricante {codigo_fabricante}.',
            'campo': 'codigo_fabricante',
        }, status=400)

    peca.marca = marca
    peca.nome_generico = nome_generico
    peca.nome_tecnico = nome_tecnico
    peca.codigo_fabricante = codigo_fabricante or None
    if imagem:
        peca.imagem = imagem
    peca.save()

    return JsonResponse({
        'id': peca.id,
        'nome': peca.nome_generico,
        'nome_tecnico': peca.nome_tecnico,
        'codigo_fabricante': peca.codigo_fabricante or '',
        'marca_id': peca.marca_id,
        'marca_nome': peca.marca.nome,
        'marca_grupo': peca.marca.grupo_fornecedor.nome if peca.marca.grupo_fornecedor else None,
        'imagem_url': peca.imagem.url if peca.imagem else None,
        'qtd_produtos_vinculados': peca.compatibilidades.count(),
    })


def vincular_peca_gaveta(request):
    """Endpoint AJAX (JSON) — cria (ou atualiza) o vínculo entre uma
    peça e um produto. Chamado tanto do Modal de Vínculo aberto a
    partir da Gaveta de Peças (peça travada) quanto do aberto a partir
    da página de Produto (produto travado) — é o mesmo componente dos
    dois lados.

    Se o vínculo já existir, não cria duplicado — devolve a quantidade
    atual pro modal mostrar o aviso de duplicidade. Só atualiza de
    fato quando o pedido chega com confirmar_atualizacao=1 (segunda
    chamada, depois que a pessoa confirma no modal)."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    peca_id = request.POST.get('peca_id', '').strip()
    produto_id = request.POST.get('produto_id', '').strip()
    confirmar_atualizacao = request.POST.get('confirmar_atualizacao') == '1'

    try:
        quantidade_esperada = int(request.POST.get('quantidade_esperada') or '0')
    except ValueError:
        quantidade_esperada = 0

    if not peca_id or not produto_id:
        return JsonResponse({'erro': 'Selecione a peça e o produto.'}, status=400)

    peca = Peca.objects.filter(pk=peca_id).first()
    if not peca:
        return JsonResponse({'erro': 'Peça inválida.'}, status=400)

    produto = Produto.objects.filter(pk=produto_id).first()
    if not produto:
        return JsonResponse({'erro': 'Produto inválido.'}, status=400)

    if quantidade_esperada < 1:
        return JsonResponse({'erro': 'Quantidade esperada precisa ser 1 ou mais.', 'campo': 'quantidade_esperada'}, status=400)

    existente = Compatibilidade.objects.filter(peca=peca, produto=produto).first()

    if existente and not confirmar_atualizacao:
        return JsonResponse({
            'duplicidade': True,
            'quantidade_atual': existente.quantidade_esperada,
        })

    if existente:
        existente.quantidade_esperada = quantidade_esperada
        existente.save()
        compatibilidade = existente
        criada = False
    else:
        compatibilidade = Compatibilidade.objects.create(
            peca=peca, produto=produto, quantidade_esperada=quantidade_esperada,
        )
        criada = True

    return JsonResponse({
        'id': compatibilidade.id,
        'peca_id': peca.id,
        'peca_nome': peca.nome_generico,
        'produto_id': produto.id,
        'produto_nome': produto.nome,
        'quantidade_esperada': compatibilidade.quantidade_esperada,
        'criada': criada,
    })


def buscar_produtos(request, peca_id):
    """Busca de produtos pra vincular a esta peça — simétrico ao
    buscar_pecas (busca de peças pra vincular a um produto). Exclui
    produtos já vinculados a esta peça, pelo mesmo motivo: quem já
    está vinculado já aparece na lista, a busca é só pra achar algo
    novo pra adicionar."""
    termo = request.GET.get('q', '').strip()

    resultados = []
    if len(termo) >= 2:
        produtos = (
            Produto.objects.filter(nome__icontains=termo)
            .exclude(compatibilidades__peca_id=peca_id)
            .select_related('marca')[:8]
        )

        for produto in produtos:
            resultados.append({
                'id': produto.id,
                'nome': produto.nome,
                'foto_url': produto.foto.url if produto.foto else None,
                'marca_nome': produto.marca.nome,
            })

    return JsonResponse({'resultados': resultados})


def marcas_grupos(request):
    contexto = {
        'marcas': Marca.objects.select_related('grupo_fornecedor'),
        'grupos': GrupoFornecedor.objects.all(),
        'pagina_ativa': 'marcas_grupos',
    }
    return render(request, 'devolucoes/marcas_grupos.html', contexto)


def cadastrar_marca_avulsa(request):
    if request.method == 'POST':
        marca, erro = _criar_marca(request.POST.get('nome', ''), request.POST.get('grupo_fornecedor_id', '').strip())
        if erro:
            messages.error(request, erro)
        else:
            messages.success(request, f'Marca "{marca.nome}" cadastrada.')

    return redirect('marcas_grupos')


def editar_marca(request, marca_id):
    marca = get_object_or_404(Marca, pk=marca_id)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        grupo_id = request.POST.get('grupo_fornecedor_id', '').strip()

        if nome:
            if Marca.objects.exclude(pk=marca.pk).filter(nome=nome).exists():
                messages.error(request, f'Já existe outra marca chamada "{nome}".')
                return redirect('marcas_grupos')

            marca.nome = nome
            marca.grupo_fornecedor = GrupoFornecedor.objects.filter(pk=grupo_id).first() if grupo_id else None
            marca.save()
            messages.success(request, f'Marca "{nome}" atualizada.')

    return redirect('marcas_grupos')


def excluir_marca(request, marca_id):
    marca = get_object_or_404(Marca, pk=marca_id)

    if request.method == 'POST':
        if marca.produtos.exists() or marca.pecas.exists():
            messages.error(request, f'A marca "{marca.nome}" tem produtos ou peças vinculados e não pode ser excluída.')
            return redirect('marcas_grupos')

        marca.delete()
        messages.success(request, f'Marca "{marca.nome}" excluída.')

    return redirect('marcas_grupos')


def cadastrar_grupo_fornecedor_avulso(request):
    if request.method == 'POST':
        grupo, erro = _criar_grupo_fornecedor(request.POST.get('nome', ''))
        if erro:
            messages.error(request, erro)
        else:
            messages.success(request, f'Grupo "{grupo.nome}" cadastrado.')

    return redirect('marcas_grupos')


def editar_grupo_fornecedor(request, grupo_id):
    grupo = get_object_or_404(GrupoFornecedor, pk=grupo_id)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()

        if nome:
            if GrupoFornecedor.objects.exclude(pk=grupo.pk).filter(nome=nome).exists():
                messages.error(request, f'Já existe outro grupo chamado "{nome}".')
                return redirect('marcas_grupos')

            grupo.nome = nome
            grupo.save()
            messages.success(request, f'Grupo "{nome}" atualizado.')

    return redirect('marcas_grupos')


def excluir_grupo_fornecedor(request, grupo_id):
    grupo = get_object_or_404(GrupoFornecedor, pk=grupo_id)

    if request.method == 'POST':
        nome = grupo.nome
        grupo.delete()
        messages.success(request, f'Grupo "{nome}" excluído.')

    return redirect('marcas_grupos')


def modelos_anotacao(request):
    contexto = {
        'modelos': ModeloAnotacao.objects.all(),
        'pagina_ativa': 'modelos_anotacao',
    }
    return render(request, 'devolucoes/modelos_anotacao.html', contexto)


def cadastrar_modelo_anotacao(request):
    if request.method == 'POST':
        texto = request.POST.get('texto', '').strip()

        if not texto:
            messages.error(request, 'Texto do modelo é obrigatório.')
        elif ModeloAnotacao.objects.filter(texto=texto).exists():
            messages.error(request, f'Já existe um modelo "{texto}".')
        else:
            ModeloAnotacao.objects.create(texto=texto)
            messages.success(request, f'Modelo "{texto}" cadastrado.')

    return redirect('modelos_anotacao')


def editar_modelo_anotacao(request, modelo_id):
    modelo = get_object_or_404(ModeloAnotacao, pk=modelo_id)

    if request.method == 'POST':
        texto = request.POST.get('texto', '').strip()

        if texto:
            if ModeloAnotacao.objects.exclude(pk=modelo.pk).filter(texto=texto).exists():
                messages.error(request, f'Já existe outro modelo "{texto}".')
                return redirect('modelos_anotacao')

            modelo.texto = texto
            modelo.save()
            messages.success(request, f'Modelo "{texto}" atualizado.')

    return redirect('modelos_anotacao')


def excluir_modelo_anotacao(request, modelo_id):
    modelo = get_object_or_404(ModeloAnotacao, pk=modelo_id)

    if request.method == 'POST':
        texto = modelo.texto
        modelo.delete()
        messages.success(request, f'Modelo "{texto}" excluído.')

    return redirect('modelos_anotacao')


def manutencao_reorganizar_fotos(request):
    """Tela de manutenção pontual — reorganiza no disco as fotos de
    conferência e de reclamação do cliente que já existiam antes da
    mudança de upload_to. De propósito sem link em nenhum menu: só
    acessível digitando o endereço direto (ver urls.py).

    Roda sempre em cima da empresa ativa (a mesma escolhida no badge
    "trocar empresa" no topo da tela) — pra cobrir a outra empresa,
    troca no badge e abre essa página de novo.

    GET = simula (nada é alterado). POST = aplica de verdade.
    """
    alias = obter_alias_banco_ativo()
    aplicar = request.method == 'POST'

    resultado = reorganizar_fotos_devolucao(alias, aplicar=aplicar)

    return render(request, 'devolucoes/manutencao_reorganizar_fotos.html', {
        'resultado': resultado,
        'aplicou': aplicar,
    })