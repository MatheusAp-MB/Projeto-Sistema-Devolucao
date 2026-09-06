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
    return staticfiles_serve(request, path, insecure=True)


def servir_midia(request, path):
    return media_serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', include('devolucoes.urls')),
    path('static/<path:path>', servir_estatico),
    path('media/<path:path>', servir_midia),
]