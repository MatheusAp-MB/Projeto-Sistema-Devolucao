# devolucoes/exportacao_xlsx.py

# Função Objetivo: gerar um arquivo .xlsx (Excel) simples — 1 planilha, 1 linha
# de títulos e as linhas de dados — SEM nenhuma biblioteca de fora. Existe
# pra "Exportar para Excel" da tela Análise (pedido de Matheus, 05/10/2026).
#
# * [EXPLICAÇÃO] → por que escrever o .xlsx na mão: o projeto não tem
#   openpyxl nas dependências (pyproject.toml) e todo pacote novo precisa
#   entrar também no empacotamento do .exe (PyInstaller). Um .xlsx é só um
#   ZIP com alguns arquivos XML dentro, e o Python já traz `zipfile`; pra
#   uma planilha simples (títulos + dados + formato de data e de dinheiro)
#   são poucas dezenas de linhas. Se um dia a exportação precisar de
#   fórmulas, gráficos ou várias planilhas, aí vale trocar por openpyxl.
#
# [ATENÇÃO] → todo texto vai como "texto de verdade" (inlineStr), nunca
# como fórmula: um cliente chamado "=1+1" aparece escrito assim na célula,
# o Excel não calcula nada a partir dele.

import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

TIPO_TEXTO = 'texto'
TIPO_DATA = 'data'
TIPO_DINHEIRO = 'dinheiro'

# Estilos (posição na lista cellXfs do styles.xml abaixo)
_ESTILO_PADRAO = 0
_ESTILO_TITULO = 1
_ESTILO_DATA = 2
_ESTILO_DINHEIRO = 3

# Caracteres de controle que o XML não aceita (um deles sozinho deixa o
# arquivo "corrompido" pro Excel). \t, \n e \r são permitidos e ficam.
_CONTROLES_PROIBIDOS = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]')

_INICIO_EXCEL = date(1899, 12, 30)


def _letra_da_coluna(indice):
    # 0 -> A, 25 -> Z, 26 -> AA ...
    letras = ''
    n = indice + 1
    while n:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _texto_xml(valor):
    return escape(_CONTROLES_PROIBIDOS.sub('', str(valor)))


def _celula_texto(referencia, valor, estilo):
    texto = _texto_xml(valor)
    return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (referencia, estilo, texto)


def _celula(referencia, valor, tipo):
    """Uma célula já em XML. Valor vazio (None ou '') vira célula nenhuma."""
    if valor is None or valor == '':
        return ''
    if tipo == TIPO_DATA:
        if isinstance(valor, datetime):
            valor = valor.date()
        if isinstance(valor, date):
            return '<c r="%s" s="%d"><v>%d</v></c>' % (referencia, _ESTILO_DATA, (valor - _INICIO_EXCEL).days)
        return _celula_texto(referencia, valor, _ESTILO_PADRAO)
    if tipo == TIPO_DINHEIRO:
        try:
            numero = Decimal(str(valor))
        except Exception:
            return _celula_texto(referencia, valor, _ESTILO_PADRAO)
        return '<c r="%s" s="%d"><v>%s</v></c>' % (referencia, _ESTILO_DINHEIRO, format(numero, 'f'))
    return _celula_texto(referencia, valor, _ESTILO_PADRAO)


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>'
)

_RELS_RAIZ = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    '</Relationships>'
)

_RELS_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>'
)

# Estilos: 0 normal · 1 título (negrito, letra branca, fundo azul-escuro,
# centralizado) · 2 data dd/mm/aaaa · 3 dinheiro R$ 1.234,56 (o Excel
# troca o separador conforme o idioma do Windows de quem abre).
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="2">'
    '<numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>'
    '<numFmt numFmtId="165" formatCode="&quot;R$&quot; #,##0.00"/>'
    '</numFmts>'
    '<fonts count="2">'
    '<font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
    '</fonts>'
    '<fills count="3">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FF1F3A5F"/><bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="4">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center"/></xf>'
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '</cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>'
)


def _nome_da_planilha(nome):
    # O Excel recusa nome de aba com : \ / ? * [ ] e com mais de 31 letras.
    limpo = re.sub(r'[:\\/?*\[\]]', ' ', str(nome or 'Planilha')).strip()
    return (limpo or 'Planilha')[:31]


def gerar_xlsx(nome_planilha, colunas, linhas):
    """Devolve os bytes de um .xlsx.

    colunas: lista de dicionários {'titulo': str, 'tipo': 'texto'|'data'|
             'dinheiro', 'largura': número (em "letras", como o Excel)}.
    linhas:  lista de listas, cada uma com 1 valor por coluna (texto,
             date/datetime, Decimal/número ou None pra célula vazia).
    A 1ª linha (títulos) fica congelada e com filtro em todas as colunas."""
    quantidade_colunas = len(colunas)
    partes = []

    partes.append(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    )
    ultima_coluna = _letra_da_coluna(max(quantidade_colunas, 1) - 1)
    ultima_linha = len(linhas) + 1
    partes.append('<dimension ref="A1:%s%d"/>' % (ultima_coluna, ultima_linha))
    partes.append(
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft"/>'
        '</sheetView></sheetViews>'
    )
    partes.append('<sheetFormatPr defaultRowHeight="15"/>')
    if colunas:
        partes.append('<cols>')
        for i, coluna in enumerate(colunas, start=1):
            partes.append('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (i, i, coluna.get('largura', 16)))
        partes.append('</cols>')

    partes.append('<sheetData>')
    partes.append('<row r="1" ht="30" customHeight="1">')
    for i, coluna in enumerate(colunas):
        partes.append(_celula_texto('%s1' % _letra_da_coluna(i), coluna['titulo'], _ESTILO_TITULO))
    partes.append('</row>')

    for numero, linha in enumerate(linhas, start=2):
        partes.append('<row r="%d">' % numero)
        for i, coluna in enumerate(colunas):
            valor = linha[i] if i < len(linha) else None
            partes.append(_celula('%s%d' % (_letra_da_coluna(i), numero), valor, coluna.get('tipo', TIPO_TEXTO)))
        partes.append('</row>')
    partes.append('</sheetData>')

    if quantidade_colunas:
        partes.append('<autoFilter ref="A1:%s%d"/>' % (ultima_coluna, ultima_linha))
    partes.append('<pageMargins left="0.5" right="0.5" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>')
    partes.append('<pageSetup orientation="landscape"/>')
    partes.append('</worksheet>')

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>' % escape(_nome_da_planilha(nome_planilha), {'"': '&quot;'})
    )

    saida = io.BytesIO()
    with zipfile.ZipFile(saida, 'w', zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr('[Content_Types].xml', _CONTENT_TYPES)
        pacote.writestr('_rels/.rels', _RELS_RAIZ)
        pacote.writestr('xl/workbook.xml', workbook)
        pacote.writestr('xl/_rels/workbook.xml.rels', _RELS_WORKBOOK)
        pacote.writestr('xl/styles.xml', _STYLES)
        pacote.writestr('xl/worksheets/sheet1.xml', ''.join(partes))
    return saida.getvalue()
