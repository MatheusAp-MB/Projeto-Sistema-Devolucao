# core/empresa.py

# Função Objetivo: guarda qual empresa (Magazine/Samvale) está ativa
# nesta requisição, em thread-local — mesmo padrão do Sistema Interno V2.

import threading

_armazenamento_local = threading.local()

EMPRESA_MAGAZINE = 'MAGAZINE'
EMPRESA_SAMVALE = 'SAMVALE'

EMPRESA_PADRAO = EMPRESA_MAGAZINE

EMPRESAS_VALIDAS = [EMPRESA_MAGAZINE, EMPRESA_SAMVALE]

ALIAS_BANCO_POR_EMPRESA = {
    EMPRESA_MAGAZINE: 'magazine',
    EMPRESA_SAMVALE: 'samvale',
}

NOME_EXIBICAO_POR_EMPRESA = {
    EMPRESA_MAGAZINE: 'MAGAZINE BRASILEIRO',
    EMPRESA_SAMVALE: 'SAMVALE',
}

# * [EXPLICAÇÃO] → Usado pela sidebar/favicon (core/context_processors.py)
#                  e pela tela de escolher empresa (core/views.py) — se os
#                  arquivos que você tem prontos forem .jpg em vez de
#                  .png, só trocar a extensão nas 2 linhas abaixo.
LOGO_POR_EMPRESA = {
    EMPRESA_MAGAZINE: 'base_compartilhada/img/Logo_MB.png',
    EMPRESA_SAMVALE: 'base_compartilhada/img/Logo_SV.png',
}


def definir_empresa_ativa(empresa):
    _armazenamento_local.empresa = empresa


def obter_empresa_ativa():
    # None = nenhuma requisição web setou isso ainda (comando de
    # terminal, migration, shell) — o Router não deve opinar nesses
    # casos, respeitando o --database= nativo do Django.
    return getattr(_armazenamento_local, 'empresa', None)


def obter_alias_banco_ativo():
    empresa = obter_empresa_ativa()
    if empresa is None:
        return None
    return ALIAS_BANCO_POR_EMPRESA[empresa]