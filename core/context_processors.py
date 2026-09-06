# core/context_processors.py

# Função Objetivo: expõe a empresa ativa (definida pelo EmpresaMiddleware)
# pra qualquer template, sem cada view precisar repetir isso no
# contexto — usado pelo seletor de empresa no menu principal.

from core.empresa import (
    EMPRESA_MAGAZINE,
    EMPRESA_SAMVALE,
    LOGO_POR_EMPRESA,
    NOME_EXIBICAO_POR_EMPRESA,
    obter_empresa_ativa,
)

CLASSE_CSS_POR_EMPRESA = {
    EMPRESA_MAGAZINE: 'badge-empresa-magazine',
    EMPRESA_SAMVALE: 'badge-empresa-samvale',
}

def empresa_ativa(request):
    empresa = obter_empresa_ativa()

    return {
        'empresa_ativa': empresa,
        'empresa_ativa_nome': NOME_EXIBICAO_POR_EMPRESA.get(empresa, ''),
        'empresa_classe_css': CLASSE_CSS_POR_EMPRESA.get(empresa, ''),
        'empresa_logo': LOGO_POR_EMPRESA.get(empresa, LOGO_POR_EMPRESA[EMPRESA_MAGAZINE]),
    }