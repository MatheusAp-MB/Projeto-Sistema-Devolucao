# core/middleware.py

# Função Objetivo: decide qual empresa está ativa nesta requisição,
# antes de qualquer view/model rodar. Sem a distinção de rota /api/ do
# Sistema Interno V2 — este projeto ainda não tem rota de API própria.

from core.empresa import definir_empresa_ativa, EMPRESA_PADRAO, EMPRESAS_VALIDAS


class EmpresaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        empresa = request.session.get('empresa_ativa', EMPRESA_PADRAO)
        if empresa not in EMPRESAS_VALIDAS:
            empresa = EMPRESA_PADRAO
        definir_empresa_ativa(empresa)
        return self.get_response(request)