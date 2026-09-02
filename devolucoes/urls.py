# devolucoes/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.nova_devolucao, name='nova_devolucao'),
]