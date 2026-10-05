import re
from urllib.parse import urlparse

from django.db import models

from .devolucao import Devolucao

# * [EXPLICAÇÃO] → o "N.º" de uma consulta no Mercado Livre é um número de 9 dígitos (ex.: 485766153).
#   Aceita de 6 a 12 dígitos de propósito: folga pra o ML crescer a numeração, mas ainda longe do
#   número de pedido (16 dígitos, "2000..."), que assim é recusado se for colado aqui por engano.
_NUMERO_SOZINHO = re.compile(r'\D*(\d{6,12})\D*')
# Caminhos de tela do ML que carregam o número da consulta: /cases/<N> e /minhas-consultas/detalhe/<N>.
_CAMINHO_CONSULTA = re.compile(r'/(?:cases|minhas-consultas/detalhe)/(\d{6,12})(?:/|$)')
_DOMINIOS_ML = ('mercadolivre.com.br', 'mercadolivre.com', 'mercadolibre.com')

URL_CONSULTA_ML = 'https://www.mercadolivre.com.br/cases/{numero}'


def extrair_numero_consulta(texto):
    """Devolve só o número da consulta (str) a partir do que a pessoa digitou/colou, ou None se não
    der pra ter certeza. Aceita:
      - o número puro ("485766153") ou com texto em volta ("N.º 485766153", "Consulta número: 485766153");
      - o endereço da consulta no site do ML, em qualquer um dos formatos que ele usa
        (…/cases/485766153, …/minhas-consultas/detalhe/485766153?chat=true).
    Endereço de outro site é recusado (None) — o link final é sempre montado por nós, nunca copiado."""
    texto = (texto or '').strip()
    if not texto:
        return None

    if '://' in texto or texto.lower().startswith('www.'):
        try:
            partes = urlparse(texto if '://' in texto else 'https://' + texto)
        except ValueError:
            return None
        host = (partes.hostname or '').lower()
        if not any(host == dominio or host.endswith('.' + dominio) for dominio in _DOMINIOS_ML):
            return None
        achado = _CAMINHO_CONSULTA.search(partes.path)
        return achado.group(1) if achado else None

    achado = _NUMERO_SOZINHO.fullmatch(texto)
    return achado.group(1) if achado else None


class ConsultaML(models.Model):
    # * [EXPLICAÇÃO] → "consulta" é o nome que o Mercado Livre dá a um atendimento aberto pelo vendedor na
    #   Central de vendedores (Minhas consultas). Uma devolução pode ter 0, 1 ou várias (a Ana às vezes
    #   abre mais de uma) — por isso uma linha por consulta, e não um campo só na Devolucao. Guardamos só o
    #   número: o link é montado em `link` (decisão de Matheus, 05/10/2026). Consultas encerradas ficam
    #   disponíveis no ML por 30 dias, então a anotação é o registro duradouro de como terminou.
    STATUS_ABERTA = 'aberta'
    STATUS_ENCERRADA = 'encerrada'
    STATUS_CHOICES = [
        (STATUS_ABERTA, 'Aberta'),
        (STATUS_ENCERRADA, 'Encerrada'),
    ]

    devolucao = models.ForeignKey(Devolucao, on_delete=models.CASCADE, related_name='consultas_ml')
    numero = models.CharField('N.º da consulta no ML', max_length=12)
    # * [EXPLICAÇÃO] → o ML não entrega o andamento da consulta por API (só aparece na Central de vendedores),
    #   então quem diz se ela está aberta ou encerrada é a Ana, à mão (decisão de Matheus, 05/10/2026).
    status = models.CharField('Situação', max_length=10, choices=STATUS_CHOICES, default=STATUS_ABERTA)
    anotacao = models.CharField('Anotação', max_length=300, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criada_em', 'id']
        constraints = [
            models.UniqueConstraint(fields=['devolucao', 'numero'], name='consulta_ml_unica_por_devolucao'),
        ]
        verbose_name = 'Consulta no Mercado Livre'
        verbose_name_plural = 'Consultas no Mercado Livre'

    def __str__(self):
        return f'Consulta {self.numero} — {self.devolucao}'

    @property
    def link(self):
        return URL_CONSULTA_ML.format(numero=self.numero)
