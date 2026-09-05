# core/context_processors.py

# Função Objetivo: expõe a empresa ativa (definida pelo EmpresaMiddleware)
# pra qualquer template, sem cada view precisar repetir isso no
# contexto — usado pelo seletor de empresa no menu principal.

from core.empresa import (
    EMPRESA_MAGAZINE,
    EMPRESA_SAMVALE,
    NOME_EXIBICAO_POR_EMPRESA,
    obter_empresa_ativa,
)


def empresa_ativa(request):
    empresa = obter_empresa_ativa()
    outra = EMPRESA_SAMVALE if empresa == EMPRESA_MAGAZINE else EMPRESA_MAGAZINE

    return {
        'empresa_ativa': empresa,
        'empresa_ativa_nome': NOME_EXIBICAO_POR_EMPRESA.get(empresa, ''),
        'empresa_outra': outra,
        'empresa_outra_nome': NOME_EXIBICAO_POR_EMPRESA.get(outra, ''),
    }