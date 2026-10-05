# core/urls.py

# Função Objetivo: URLs raiz do projeto — inclui as rotas do app
# `devolucoes` e serve estático/mídia manualmente, porque o waitress
# serve o WSGI puro (nunca passa pelo runserver), que é o único lugar
# onde o Django serve esses arquivos sozinho durante o desenvolvimento.

from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.urls import include, path
from django.views.static import serve as media_serve


def servir_estatico(request, path):
    # insecure=True: essa view normalmente só funciona com DEBUG=True —
    # aqui não existe "produção" separada de "app empacotado", então
    # força funcionar sempre, independente do DEBUG.
    resposta = staticfiles_serve(request, path, insecure=True)
    # [EXPLICAÇÃO] → 'no-cache' NÃO desliga o cache: manda o navegador PERGUNTAR ao
    # servidor "esse arquivo mudou?" a cada uso (se não mudou, a resposta é um "304"
    # curtinho e ele usa a cópia que já tem). Sem isso o navegador decidia sozinho guardar
    # o CSS/JS por horas e, depois de uma atualização do sistema, mostrava a página nova
    # com o visual velho (visto no celular em 05/10/2026). Vale pro .exe (waitress) e pro
    # runserver iniciado com --nostatic (o runserver normal serve o estático por fora
    # desta função e não passa por aqui).
    resposta['Cache-Control'] = 'no-cache'
    return resposta


def servir_midia(request, path):
    return media_serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', include('devolucoes.urls')),
    path('', include('integracao_mercado_livre.urls')),
    path('static/<path:path>', servir_estatico),
    path('media/<path:path>', servir_midia),
]