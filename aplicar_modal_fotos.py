# -*- coding: utf-8 -*-
"""
Cria o modal de fotos unico e reutilizavel (CSS + JS novos, compartilhados
pelo sistema inteiro) e liga ele nas telas que devem exibir fotos clicaveis,
conforme decidido:

  - Visualizar Devolucao (foto do produto, Resumo geral, Motivo da
    reclamacao do cliente, Evidencia para a mediacao)
  - Gaveta de Pecas (card de peca)
  - Produto especifico (/produtos/<id>/) — foto principal e pecas mini
  - Vincular pecas — só a foto do produto no topo (os cards de peça, que
    ficam dentro do checkbox de selecao, ficam de fora)
  - Devolucoes pendentes (foto de cada item da lista)
  - Conferencia de pecas — foto original do produto, foto de referencia
    da peca, fotos ja anexadas na conferencia atual e a previa de fotos
    recem-selecionadas (ainda nao salvas)
  - Nova Devolucao (reaproveita a mesma previa da Conferencia pras fotos
    do cliente)

Ficam de fora (decidido): lista de Produtos, cards de peca da tela de
Vincular pecas, relatorio de impressao, telas de upload de foto.

Como rodar:
    python3 aplicar_modal_fotos.py [caminho_do_repo]

Se "caminho_do_repo" nao for passado, usa o diretorio atual. Rode a partir
da raiz do repo (Projeto-Sistema-Devolucao) ou passe o caminho dela.

Seguro: cada troca so e aplicada se o texto original aparecer no arquivo
exatamente a quantidade de vezes esperada (normalmente 1; em
devolucoes_pendentes.html o mesmo bloco se repete 5x de proposito, uma vez
por aba). Os 2 arquivos novos (CSS e JS do modal) so sao criados se ainda
NAO existirem. Se qualquer checagem falhar, o script NAO grava nada — lista
os problemas e para. So escreve os arquivos se TUDO bater.
"""
import sys
import os

REPO = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
AQUI = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1) Arquivos novos (CSS + JS do modal). So sao criados se ainda nao existirem.
# ---------------------------------------------------------------------------
ARQUIVOS_NOVOS = [
    ("core/static/base_compartilhada/css/layout_modal_fotos.css", "layout_modal_fotos.css"),
    ("core/static/base_compartilhada/js/script_modal_fotos.js", "script_modal_fotos.js"),
]

# ---------------------------------------------------------------------------
# 2) Trocas em arquivos existentes.
# Cada entrada: (caminho relativo, [ (texto_antigo, texto_novo, qtd_esperada), ... ])
# qtd_esperada e opcional (padrao 1) — usado quando o mesmo bloco se repete
# de proposito (ex.: devolucoes_pendentes.html, 5 abas iguais).
# ---------------------------------------------------------------------------
TROCAS = [

    ("core/templates/base_compartilhada/estrutura_base_global.html", [
        (
            "        <link rel=\"stylesheet\" href=\"{% static 'base_compartilhada/css/layout_global.css' %}\">\n"
            "        <link rel=\"stylesheet\" href=\"{% static 'base_compartilhada/css/layout_badges.css' %}\">\n"
            "        {% block head_extra %}{% endblock %}",

            "        <link rel=\"stylesheet\" href=\"{% static 'base_compartilhada/css/layout_global.css' %}\">\n"
            "        <link rel=\"stylesheet\" href=\"{% static 'base_compartilhada/css/layout_badges.css' %}\">\n"
            "        <link rel=\"stylesheet\" href=\"{% static 'base_compartilhada/css/layout_modal_fotos.css' %}\">\n"
            "        {% block head_extra %}{% endblock %}",
        ),
        (
            "        <!-- Bootstrap JS -->\n"
            "        <script src=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js\"></script>\n"
            "        <script src=\"{% static 'base_compartilhada/js/script_global.js' %}\"></script>\n"
            "        {% block scripts %}{% endblock %}\n"
            "    </body>\n"
            "</html>",

            "        <!-- Bootstrap JS -->\n"
            "        <script src=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js\"></script>\n"
            "        <script src=\"{% static 'base_compartilhada/js/script_global.js' %}\"></script>\n"
            "\n"
            "        <!-- Modal de fotos — único pro sistema inteiro, ver layout_modal_fotos.css / script_modal_fotos.js -->\n"
            "        <div id=\"modal-fotos\" class=\"modal-fotos-overlay\" hidden>\n"
            "            <div class=\"modal-fotos-cabecalho\">\n"
            "                <div class=\"modal-fotos-identificacao\">\n"
            "                    <span class=\"modal-fotos-titulo\" id=\"modal-fotos-titulo\"></span>\n"
            "                    <span class=\"modal-fotos-subtitulo\" id=\"modal-fotos-subtitulo\"></span>\n"
            "                </div>\n"
            "                <span class=\"modal-fotos-contador\" id=\"modal-fotos-contador\"></span>\n"
            "                <button type=\"button\" class=\"modal-fotos-fechar\" id=\"modal-fotos-fechar\" aria-label=\"Fechar\">&times;</button>\n"
            "            </div>\n"
            "            <div class=\"modal-fotos-area\">\n"
            "                <button type=\"button\" class=\"modal-fotos-nav\" id=\"modal-fotos-anterior\" aria-label=\"Foto anterior\">&#10094;</button>\n"
            "                <div class=\"modal-fotos-corpo\">\n"
            "                    <img id=\"modal-fotos-imagem\" class=\"modal-fotos-imagem\" src=\"\" alt=\"\">\n"
            "                </div>\n"
            "                <button type=\"button\" class=\"modal-fotos-nav\" id=\"modal-fotos-proxima\" aria-label=\"Próxima foto\">&#10095;</button>\n"
            "            </div>\n"
            "            <p class=\"modal-fotos-legenda\" id=\"modal-fotos-legenda\"></p>\n"
            "        </div>\n"
            "        <script src=\"{% static 'base_compartilhada/js/script_modal_fotos.js' %}\"></script>\n"
            "\n"
            "        {% block scripts %}{% endblock %}\n"
            "    </body>\n"
            "</html>",
        ),
    ]),

    ("devolucoes/templates/devolucoes/visualizar_devolucao.html", [
        (
            "            <div class=\"vd-produto-foto-mini\">\n"
            "                {% if devolucao.produto.foto %}\n"
            "                    <img src=\"{{ devolucao.produto.foto.url }}\" alt=\"{{ devolucao.produto.nome }}\">\n"
            "                {% else %}\n"
            "                    <i class=\"fas fa-box\"></i>\n"
            "                {% endif %}\n"
            "            </div>",

            "            <div class=\"vd-produto-foto-mini{% if devolucao.produto.foto %} card-fotos-item{% endif %}\"\n"
            "                 {% if devolucao.produto.foto %}data-fotos-id=\"vd-produto-{{ devolucao.id }}\" data-titulo=\"{{ devolucao.produto.nome }}\"{% endif %}>\n"
            "                {% if devolucao.produto.foto %}\n"
            "                    <img src=\"{{ devolucao.produto.foto.url }}\" alt=\"{{ devolucao.produto.nome }}\">\n"
            "                {% else %}\n"
            "                    <i class=\"fas fa-box\"></i>\n"
            "                {% endif %}\n"
            "            </div>",
        ),
        (
            "        {% if fotos_reclamacao_cliente %}\n"
            "            <div class=\"vd-grade-fotos\">\n"
            "                {% for foto in fotos_reclamacao_cliente %}\n"
            "                    <a href=\"{{ foto.imagem.url }}\" target=\"_blank\" class=\"vd-foto-item\" title=\"{{ foto.nome_arquivo }}\">\n"
            "                        <div class=\"vd-foto-thumb\">\n"
            "                            <img src=\"{{ foto.imagem.url }}\" alt=\"Foto do cliente\">\n"
            "                        </div>\n"
            "                        <span class=\"vd-foto-nome\">{{ foto.nome_arquivo }}</span>\n"
            "                    </a>\n"
            "                {% endfor %}\n"
            "            </div>\n"
            "        {% endif %}",

            "        {% if fotos_reclamacao_cliente %}\n"
            "            <div class=\"vd-grade-fotos\">\n"
            "                {% for foto in fotos_reclamacao_cliente %}\n"
            "                    <a href=\"{{ foto.imagem.url }}\" target=\"_blank\" class=\"vd-foto-item card-fotos-item\" title=\"{{ foto.nome_arquivo }}\"\n"
            "                       data-fotos-id=\"vd-reclamacao-cliente\" data-titulo=\"Foto do cliente\" data-legenda=\"{{ foto.nome_arquivo }}\">\n"
            "                        <div class=\"vd-foto-thumb\">\n"
            "                            <img src=\"{{ foto.imagem.url }}\" alt=\"Foto do cliente\">\n"
            "                        </div>\n"
            "                        <span class=\"vd-foto-nome\">{{ foto.nome_arquivo }}</span>\n"
            "                    </a>\n"
            "                {% endfor %}\n"
            "            </div>\n"
            "        {% endif %}",
        ),
        (
            "                            <div class=\"vd-resumo-card-topo\">\n"
            "                                {% if conferencia.peca.imagem %}\n"
            "                                    <img class=\"vd-resumo-card-foto\" src=\"{{ conferencia.peca.imagem.url }}\" alt=\"\">\n"
            "                                {% else %}\n"
            "                                    <div class=\"vd-resumo-card-foto-vazia\"></div>\n"
            "                                {% endif %}",

            "                            <div class=\"vd-resumo-card-topo\">\n"
            "                                {% if conferencia.peca.imagem %}\n"
            "                                    <img class=\"vd-resumo-card-foto card-fotos-item\" src=\"{{ conferencia.peca.imagem.url }}\" alt=\"\"\n"
            "                                         data-fotos-id=\"vd-resumo-{{ conferencia.peca.id }}\" data-titulo=\"{{ conferencia.peca.nome_generico }}\">\n"
            "                                {% else %}\n"
            "                                    <div class=\"vd-resumo-card-foto-vazia\"></div>\n"
            "                                {% endif %}",
        ),
        (
            "                    {% for conferencia in pecas_com_problema %}\n"
            "                        {% for foto in conferencia.fotos.all %}\n"
            "                            <a href=\"{{ foto.imagem.url }}\" target=\"_blank\" class=\"vd-foto-item\" title=\"{{ foto.nome_arquivo }}\">\n"
            "                                <div class=\"vd-foto-thumb\">\n"
            "                                    <img src=\"{{ foto.imagem.url }}\" alt=\"Foto de {{ conferencia.peca.nome_generico }}\">\n"
            "                                </div>\n"
            "                                <span class=\"vd-foto-nome\">{{ foto.nome_arquivo }}</span>\n"
            "                            </a>\n"
            "                        {% endfor %}\n"
            "                    {% endfor %}\n"
            "                    {% for foto in fotos_observacao_geral %}\n"
            "                        <a href=\"{{ foto.imagem.url }}\" target=\"_blank\" class=\"vd-foto-item\" title=\"{{ foto.nome_arquivo }}\">\n"
            "                            <div class=\"vd-foto-thumb\">\n"
            "                                <img src=\"{{ foto.imagem.url }}\" alt=\"Foto geral do produto\">\n"
            "                            </div>\n"
            "                            <span class=\"vd-foto-nome\">{{ foto.nome_arquivo }}</span>\n"
            "                        </a>\n"
            "                    {% endfor %}",

            "                    {% for conferencia in pecas_com_problema %}\n"
            "                        {% for foto in conferencia.fotos.all %}\n"
            "                            <a href=\"{{ foto.imagem.url }}\" target=\"_blank\" class=\"vd-foto-item card-fotos-item\" title=\"{{ foto.nome_arquivo }}\"\n"
            "                               data-fotos-id=\"vd-evidencia\" data-titulo=\"{{ conferencia.peca.nome_generico }}\"\n"
            "                               data-legenda=\"{{ conferencia.anotacao|default:'' }}\">\n"
            "                                <div class=\"vd-foto-thumb\">\n"
            "                                    <img src=\"{{ foto.imagem.url }}\" alt=\"Foto de {{ conferencia.peca.nome_generico }}\">\n"
            "                                </div>\n"
            "                                <span class=\"vd-foto-nome\">{{ foto.nome_arquivo }}</span>\n"
            "                            </a>\n"
            "                        {% endfor %}\n"
            "                    {% endfor %}\n"
            "                    {% for foto in fotos_observacao_geral %}\n"
            "                        <a href=\"{{ foto.imagem.url }}\" target=\"_blank\" class=\"vd-foto-item card-fotos-item\" title=\"{{ foto.nome_arquivo }}\"\n"
            "                           data-fotos-id=\"vd-evidencia\" data-titulo=\"Observação geral do produto\"\n"
            "                           data-legenda=\"{{ devolucao.observacao_geral|default:'' }}\">\n"
            "                            <div class=\"vd-foto-thumb\">\n"
            "                                <img src=\"{{ foto.imagem.url }}\" alt=\"Foto geral do produto\">\n"
            "                            </div>\n"
            "                            <span class=\"vd-foto-nome\">{{ foto.nome_arquivo }}</span>\n"
            "                        </a>\n"
            "                    {% endfor %}",
        ),
    ]),

    ("devolucoes/templates/devolucoes/_card_peca.html", [
        (
            "    <div class=\"gaveta-peca-card-foto{% if peca.imagem %} catalogo-peca-foto--clicavel{% endif %}\"\n"
            "         {% if peca.imagem %}data-imagem-url=\"{{ peca.imagem.url }}\" data-imagem-titulo=\"{{ peca.nome_generico }}\"{% endif %}>",

            "    <div class=\"gaveta-peca-card-foto{% if peca.imagem %} catalogo-peca-foto--clicavel card-fotos-item{% endif %}\"\n"
            "         {% if peca.imagem %}data-imagem-url=\"{{ peca.imagem.url }}\" data-imagem-titulo=\"{{ peca.nome_generico }}\"\n"
            "         data-fotos-id=\"gaveta-peca-{{ peca.id }}\" data-titulo=\"{{ peca.nome_generico }}\"{% endif %}>",
        ),
    ]),

    ("devolucoes/templates/devolucoes/produto_visualizar.html", [
        (
            "            <div class=\"produto-view-foto\">\n"
            "                {% if produto.foto %}\n"
            "                    <img src=\"{{ produto.foto.url }}\" alt=\"{{ produto.nome }}\">\n"
            "                {% else %}\n"
            "                    <i class=\"fas fa-box\"></i>\n"
            "                {% endif %}\n"
            "            </div>",

            "            <div class=\"produto-view-foto{% if produto.foto %} card-fotos-item{% endif %}\"\n"
            "                 {% if produto.foto %}data-fotos-id=\"produto-view-principal-{{ produto.id }}\" data-titulo=\"{{ produto.nome }}\"{% endif %}>\n"
            "                {% if produto.foto %}\n"
            "                    <img src=\"{{ produto.foto.url }}\" alt=\"{{ produto.nome }}\">\n"
            "                {% else %}\n"
            "                    <i class=\"fas fa-box\"></i>\n"
            "                {% endif %}\n"
            "            </div>",
        ),
        (
            "                        <div class=\"produto-view-peca-foto-mini\">\n"
            "                            {% if comp.peca.imagem %}\n"
            "                                <img src=\"{{ comp.peca.imagem.url }}\" alt=\"{{ comp.peca.nome_generico }}\">\n"
            "                            {% else %}\n"
            "                                <i class=\"fas fa-puzzle-piece\"></i>\n"
            "                            {% endif %}\n"
            "                        </div>",

            "                        <div class=\"produto-view-peca-foto-mini{% if comp.peca.imagem %} card-fotos-item{% endif %}\"\n"
            "                             {% if comp.peca.imagem %}data-fotos-id=\"produto-view-peca-{{ comp.id }}\" data-titulo=\"{{ comp.peca.nome_generico }}\"{% endif %}>\n"
            "                            {% if comp.peca.imagem %}\n"
            "                                <img src=\"{{ comp.peca.imagem.url }}\" alt=\"{{ comp.peca.nome_generico }}\">\n"
            "                            {% else %}\n"
            "                                <i class=\"fas fa-puzzle-piece\"></i>\n"
            "                            {% endif %}\n"
            "                        </div>",
        ),
    ]),

    ("devolucoes/templates/devolucoes/produto_vincular_pecas.html", [
        (
            "                <div class=\"vp-header-foto\">\n"
            "                    {% if produto.foto %}\n"
            "                        <img src=\"{{ produto.foto.url }}\" alt=\"{{ produto.nome }}\">\n"
            "                    {% else %}\n"
            "                        <i class=\"fas fa-box\"></i>\n"
            "                    {% endif %}\n"
            "                </div>",

            "                <div class=\"vp-header-foto{% if produto.foto %} card-fotos-item{% endif %}\"\n"
            "                     {% if produto.foto %}data-fotos-id=\"vp-header-{{ produto.id }}\" data-titulo=\"{{ produto.nome }}\"{% endif %}>\n"
            "                    {% if produto.foto %}\n"
            "                        <img src=\"{{ produto.foto.url }}\" alt=\"{{ produto.nome }}\">\n"
            "                    {% else %}\n"
            "                        <i class=\"fas fa-box\"></i>\n"
            "                    {% endif %}\n"
            "                </div>",
        ),
    ]),

    ("devolucoes/templates/devolucoes/devolucoes_pendentes.html", [
        (
            "                    <div class=\"dp-item-foto\">\n"
            "                        {% if devolucao.produto.foto %}\n"
            "                            <img src=\"{{ devolucao.produto.foto.url }}\" alt=\"{{ devolucao.produto.nome }}\">\n"
            "                        {% else %}\n"
            "                            <i class=\"fas fa-box\"></i>\n"
            "                        {% endif %}\n"
            "                    </div>",

            "                    <div class=\"dp-item-foto{% if devolucao.produto.foto %} card-fotos-item{% endif %}\"\n"
            "                         {% if devolucao.produto.foto %}data-fotos-id=\"dp-{{ devolucao.id }}\" data-titulo=\"{{ devolucao.produto.nome }}\"{% endif %}>\n"
            "                        {% if devolucao.produto.foto %}\n"
            "                            <img src=\"{{ devolucao.produto.foto.url }}\" alt=\"{{ devolucao.produto.nome }}\">\n"
            "                        {% else %}\n"
            "                            <i class=\"fas fa-box\"></i>\n"
            "                        {% endif %}\n"
            "                    </div>",
            5,
        ),
    ]),

    ("devolucoes/templates/devolucoes/conferir_devolucao.html", [
        (
            "            <div class=\"cf-recap-foto\">\n"
            "                {% if devolucao.produto.foto %}\n"
            "                    <img src=\"{{ devolucao.produto.foto.url }}\" alt=\"{{ devolucao.produto.nome }}\">\n"
            "                {% else %}\n"
            "                    <i class=\"fas fa-box\"></i>\n"
            "                {% endif %}\n"
            "            </div>",

            "            <div class=\"cf-recap-foto{% if devolucao.produto.foto %} card-fotos-item{% endif %}\"\n"
            "                 {% if devolucao.produto.foto %}data-fotos-id=\"cf-recap-{{ devolucao.id }}\" data-titulo=\"{{ devolucao.produto.nome }}\" data-subtitulo=\"Foto original do produto\"{% endif %}>\n"
            "                {% if devolucao.produto.foto %}\n"
            "                    <img src=\"{{ devolucao.produto.foto.url }}\" alt=\"{{ devolucao.produto.nome }}\">\n"
            "                {% else %}\n"
            "                    <i class=\"fas fa-box\"></i>\n"
            "                {% endif %}\n"
            "            </div>",
        ),
        (
            "                        <div class=\"cf-peca-foto\">\n"
            "                            {% if item.peca.imagem %}\n"
            "                                <img src=\"{{ item.peca.imagem.url }}\" alt=\"{{ item.peca.nome_generico }}\">\n"
            "                            {% else %}\n"
            "                                <i class=\"fas fa-puzzle-piece\"></i>\n"
            "                            {% endif %}\n"
            "                        </div>",

            "                        <div class=\"cf-peca-foto{% if item.peca.imagem %} card-fotos-item{% endif %}\"\n"
            "                             {% if item.peca.imagem %}data-fotos-id=\"cf-peca-ref-{{ item.peca.id }}\" data-titulo=\"{{ item.peca.nome_generico }}\" data-subtitulo=\"Foto de referência\"{% endif %}>\n"
            "                            {% if item.peca.imagem %}\n"
            "                                <img src=\"{{ item.peca.imagem.url }}\" alt=\"{{ item.peca.nome_generico }}\">\n"
            "                            {% else %}\n"
            "                                <i class=\"fas fa-puzzle-piece\"></i>\n"
            "                            {% endif %}\n"
            "                        </div>",
        ),
        (
            "                                    <div class=\"cf-foto-item\">\n"
            "                                        <img src=\"{{ foto.imagem.url }}\" alt=\"Foto da peça {{ item.peca.nome_generico }}\">\n"
            "                                        <button type=\"submit\" class=\"cf-foto-excluir\" title=\"Excluir foto\"\n"
            "                                                formmethod=\"post\" formaction=\"{% url 'excluir_foto_conferencia' foto.id %}\">\n"
            "                                            <i class=\"fas fa-xmark\"></i>\n"
            "                                        </button>\n"
            "                                    </div>",

            "                                    <div class=\"cf-foto-item card-fotos-item\"\n"
            "                                         data-fotos-id=\"cf-fotos-{{ item.peca.id }}\" data-titulo=\"{{ item.peca.nome_generico }}\">\n"
            "                                        <img src=\"{{ foto.imagem.url }}\" alt=\"Foto da peça {{ item.peca.nome_generico }}\">\n"
            "                                        <button type=\"submit\" class=\"cf-foto-excluir\" title=\"Excluir foto\"\n"
            "                                                formmethod=\"post\" formaction=\"{% url 'excluir_foto_conferencia' foto.id %}\">\n"
            "                                            <i class=\"fas fa-xmark\"></i>\n"
            "                                        </button>\n"
            "                                    </div>",
        ),
        (
            "                                <div class=\"cf-foto-item\">\n"
            "                                    <img src=\"{{ foto.imagem.url }}\" alt=\"Foto geral do produto\">\n"
            "                                    <button type=\"submit\" class=\"cf-foto-excluir\" title=\"Excluir foto\"\n"
            "                                            formmethod=\"post\" formaction=\"{% url 'excluir_foto_observacao_geral' foto.id %}\">\n"
            "                                        <i class=\"fas fa-xmark\"></i>\n"
            "                                    </button>\n"
            "                                </div>",

            "                                <div class=\"cf-foto-item card-fotos-item\"\n"
            "                                     data-fotos-id=\"cf-fotos-geral-{{ devolucao.id }}\" data-titulo=\"Observação geral do produto\">\n"
            "                                    <img src=\"{{ foto.imagem.url }}\" alt=\"Foto geral do produto\">\n"
            "                                    <button type=\"submit\" class=\"cf-foto-excluir\" title=\"Excluir foto\"\n"
            "                                            formmethod=\"post\" formaction=\"{% url 'excluir_foto_observacao_geral' foto.id %}\">\n"
            "                                        <i class=\"fas fa-xmark\"></i>\n"
            "                                    </button>\n"
            "                                </div>",
        ),
    ]),

    ("devolucoes/templates/devolucoes/nova_devolucao.html", [
        (
            "                                <div class=\"cf-foto-item\">\n"
            "                                    <img src=\"{{ foto.imagem.url }}\" alt=\"Foto do cliente\">\n"
            "                                    <button type=\"submit\" class=\"cf-foto-excluir\" title=\"Excluir foto\"\n"
            "                                            formmethod=\"post\" formaction=\"{% url 'excluir_foto_reclamacao_cliente' foto.id %}\">\n"
            "                                        <i class=\"fas fa-xmark\"></i>\n"
            "                                    </button>\n"
            "                                </div>",

            "                                <div class=\"cf-foto-item card-fotos-item\"\n"
            "                                     data-fotos-id=\"nd-fotos-cliente\" data-titulo=\"Foto do cliente\">\n"
            "                                    <img src=\"{{ foto.imagem.url }}\" alt=\"Foto do cliente\">\n"
            "                                    <button type=\"submit\" class=\"cf-foto-excluir\" title=\"Excluir foto\"\n"
            "                                            formmethod=\"post\" formaction=\"{% url 'excluir_foto_reclamacao_cliente' foto.id %}\">\n"
            "                                        <i class=\"fas fa-xmark\"></i>\n"
            "                                    </button>\n"
            "                                </div>",
        ),
    ]),

    ("devolucoes/static/devolucoes/js/script_gaveta_pecas.js", [
        (
            "        var foto = document.createElement('div');\n"
            "        foto.className = 'gaveta-peca-card-foto' + (dados.imagemUrl ? ' catalogo-peca-foto--clicavel' : '');\n"
            "        if (dados.imagemUrl) {\n"
            "            foto.setAttribute('data-imagem-url', dados.imagemUrl);\n"
            "            foto.setAttribute('data-imagem-titulo', dados.nome);\n"
            "            var img = document.createElement('img');",

            "        var foto = document.createElement('div');\n"
            "        foto.className = 'gaveta-peca-card-foto' + (dados.imagemUrl ? ' catalogo-peca-foto--clicavel card-fotos-item' : '');\n"
            "        if (dados.imagemUrl) {\n"
            "            foto.setAttribute('data-imagem-url', dados.imagemUrl);\n"
            "            foto.setAttribute('data-imagem-titulo', dados.nome);\n"
            "            foto.setAttribute('data-fotos-id', 'gaveta-peca-' + dados.id);\n"
            "            foto.setAttribute('data-titulo', dados.nome);\n"
            "            var img = document.createElement('img');",
        ),
        (
            "        var fotoEl = card.querySelector('.gaveta-peca-card-foto');\n"
            "        if (fotoEl && dados.imagem_url) {\n"
            "            fotoEl.className = 'gaveta-peca-card-foto catalogo-peca-foto--clicavel';\n"
            "            fotoEl.setAttribute('data-imagem-url', dados.imagem_url);\n"
            "            fotoEl.setAttribute('data-imagem-titulo', dados.nome);\n"
            "            fotoEl.innerHTML = '';",

            "        var fotoEl = card.querySelector('.gaveta-peca-card-foto');\n"
            "        if (fotoEl && dados.imagem_url) {\n"
            "            fotoEl.className = 'gaveta-peca-card-foto catalogo-peca-foto--clicavel card-fotos-item';\n"
            "            fotoEl.setAttribute('data-imagem-url', dados.imagem_url);\n"
            "            fotoEl.setAttribute('data-imagem-titulo', dados.nome);\n"
            "            fotoEl.setAttribute('data-fotos-id', 'gaveta-peca-' + dados.id);\n"
            "            fotoEl.setAttribute('data-titulo', dados.nome);\n"
            "            fotoEl.innerHTML = '';",
        ),
    ]),

    ("devolucoes/static/devolucoes/js/script_conferir_devolucao.js", [
        (
            "        function renderizarPreview() {\n"
            "            preview.innerHTML = '';\n"
            "\n"
            "            arquivosAcumulados.forEach(function (arquivo, indice) {\n"
            "                var item = document.createElement('div');\n"
            "                item.className = 'cf-foto-preview-item';\n"
            "\n"
            "                var img = document.createElement('img');",

            "        function renderizarPreview() {\n"
            "            preview.innerHTML = '';\n"
            "\n"
            "            arquivosAcumulados.forEach(function (arquivo, indice) {\n"
            "                var item = document.createElement('div');\n"
            "                item.className = 'cf-foto-preview-item card-fotos-item';\n"
            "                item.setAttribute('data-fotos-id', 'preview-' + input.name);\n"
            "                item.setAttribute('data-titulo', 'Foto selecionada (ainda não salva)');\n"
            "\n"
            "                var img = document.createElement('img');",
        ),
    ]),
]


def main():
    problemas = []

    # ---- 1) arquivos novos ----
    novos_para_criar = []
    for caminho_rel, nome_fonte in ARQUIVOS_NOVOS:
        caminho_abs = os.path.join(REPO, caminho_rel)
        if os.path.exists(caminho_abs):
            problemas.append(
                "JA EXISTE (esperava criar do zero): %s — apague ou avise antes de rodar de novo."
                % caminho_abs
            )
            continue
        caminho_fonte = os.path.join(AQUI, nome_fonte)
        if not os.path.isfile(caminho_fonte):
            problemas.append("ARQUIVO FONTE NAO ENCONTRADO (bug no script): %s" % caminho_fonte)
            continue
        with open(caminho_fonte, "r", encoding="utf-8") as f:
            conteudo_novo = f.read()
        novos_para_criar.append((caminho_abs, conteudo_novo))

    # ---- 2) trocas em arquivos existentes ----
    conteudos = {}
    for caminho_rel, pares in TROCAS:
        caminho_abs = os.path.join(REPO, caminho_rel)
        if not os.path.isfile(caminho_abs):
            problemas.append("ARQUIVO NAO ENCONTRADO: %s" % caminho_abs)
            continue
        with open(caminho_abs, "r", encoding="utf-8") as f:
            conteudo = f.read()
        for par in pares:
            if len(par) == 3:
                old, new, esperado = par
            else:
                old, new = par
                esperado = 1
            n = conteudo.count(old)
            if n != esperado:
                problemas.append(
                    "%s: esperava %d ocorrencia(s), encontrei %d, pra:\n----\n%s\n----"
                    % (caminho_rel, esperado, n, old)
                )
            else:
                conteudo = conteudo.replace(old, new)
        conteudos[caminho_abs] = conteudo

    if problemas:
        print("NADA FOI ALTERADO. Encontrei %d problema(s):\n" % len(problemas))
        for p in problemas:
            print(p)
            print()
        sys.exit(1)

    # ---- so grava se TUDO bateu ----
    for caminho_abs, conteudo_novo in novos_para_criar:
        os.makedirs(os.path.dirname(caminho_abs), exist_ok=True)
        with open(caminho_abs, "w", encoding="utf-8") as f:
            f.write(conteudo_novo)
        print("CRIADO: %s" % caminho_abs)

    for caminho_abs, conteudo in conteudos.items():
        with open(caminho_abs, "w", encoding="utf-8") as f:
            f.write(conteudo)
        print("OK: %s" % caminho_abs)

    total_trocas = sum(len(pares) for _, pares in TROCAS)
    print("\n%d arquivo(s) novo(s) criado(s), %d troca(s) aplicada(s) em %d arquivo(s) existente(s)."
          % (len(novos_para_criar), total_trocas, len(conteudos)))
    print("Revise com 'git diff' e 'git status' antes de commitar.")


if __name__ == "__main__":
    main()
