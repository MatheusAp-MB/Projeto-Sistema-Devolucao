# integracao_mercado_livre/views.py

# Função Objetivo: view do botão de teste da API do Mercado Livre —
# chama GET /users/me pra provar que a integração funciona dentro do
# .exe. Resolve a conta (MB/SV) sozinha a partir da empresa ativa da
# sessão (sem Facade — mesmo padrão hoje usado no Sistema Interno V2:
# quem chama passa "MB"/"SV" explícito pro cliente de transporte).

import json

from django.conf import settings
from django.shortcuts import render

from core.empresa import obter_empresa_ativa, EMPRESA_MAGAZINE, EMPRESA_SAMVALE
from api_mercado_livre.core.estrutura_api.cliente_api import (
    chamar_api, ErroAPI, ErroAutenticacaoAPI,
)
from api_mercado_livre.core.auth.gerenciador_token import FalhaAutenticacao

CONTA_POR_EMPRESA = {
    EMPRESA_MAGAZINE: 'MB',
    EMPRESA_SAMVALE: 'SV',
}

PASTA_LOGS_ML = settings.DADOS_DIR / 'logs' / 'mercado_livre'


def view_teste_conexao_ml(request):
    empresa = obter_empresa_ativa()
    conta = CONTA_POR_EMPRESA.get(empresa)

    contexto = {'empresa': empresa, 'conta': conta}

    if conta is None:
        contexto['erro'] = f'Empresa ativa "{empresa}" não mapeada pra nenhuma conta MB/SV.'
        return render(request, 'integracao_mercado_livre/teste_conexao.html', contexto)

    try:
        resposta = chamar_api('GET', '/users/me', pasta_logs=PASTA_LOGS_ML, conta=conta)
        contexto['resultado_json'] = json.dumps(resposta.json(), ensure_ascii=False, indent=2)
    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        contexto['erro'] = str(erro)

    return render(request, 'integracao_mercado_livre/teste_conexao.html', contexto)