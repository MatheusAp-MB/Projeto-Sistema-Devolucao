# core/views.py

# Função Objetivo: views globais do app core — homepage e a tela de
# escolher/trocar a empresa ativa (Magazine/Samvale).

from django.contrib import messages
from django.shortcuts import redirect, render

from core.empresa import EMPRESAS_VALIDAS, LOGO_POR_EMPRESA, NOME_EXIBICAO_POR_EMPRESA


def view_home(request):
    return render(request, 'pagina_home/estrutura_home.html')


def view_escolher_empresa(request):
    if request.method == 'POST':
        empresa_escolhida = request.POST.get('empresa')

        if empresa_escolhida not in EMPRESAS_VALIDAS:
            messages.error(request, 'Empresa inválida.')
            return redirect('escolher_empresa')

        # * [EXPLICAÇÃO] → Sem logout() aqui — diferente do Sistema Interno
        #                  V2, o Devolução ainda não tem autenticação, então
        #                  não existe sessão de usuário pra invalidar.
        request.session['empresa_ativa'] = empresa_escolhida
        return redirect('home')

    return render(request, 'pagina_empresa/estrutura_escolher_empresa.html', {
        'empresas': [
            {'valor': valor, 'nome_exibicao': nome, 'logo': LOGO_POR_EMPRESA[valor]}
            for valor, nome in NOME_EXIBICAO_POR_EMPRESA.items()
        ],
    })