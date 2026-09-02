# devolucoes/views.py

from django.shortcuts import render


def nova_devolucao(request):
    return render(request, 'devolucoes/nova_devolucao.html')