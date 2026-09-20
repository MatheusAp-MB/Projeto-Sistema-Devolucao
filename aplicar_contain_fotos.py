# -*- coding: utf-8 -*-
"""
Troca object-fit: cover -> object-fit: contain nas caixas de foto REAIS de
produto/peca do sistema (conferencia, catalogo, gaveta de pecas, produtos,
devolucoes pendentes, vincular pecas, relatorio A4). Nao mexe em logo de
empresa (layout_empresa.css / layout_global.css) nem no modal de zoom do
catalogo (catalogo-modal-imagem), que ja usa contain.

Duas caixas (.cf-foto-item e .cf-foto-preview-item, na tela de Conferencia)
nao tinham fundo proprio -- ganham "background: var(--cor-fundo-pagina)"
junto, senao a margem que sobra da foto fica esquisita (transparente) em
vez de parecer uma moldura.

Como rodar:
    python3 aplicar_contain_fotos.py [caminho_do_repo]

Se "caminho_do_repo" nao for passado, usa o diretorio atual. Rode a partir
da raiz do repo (Projeto-Sistema-Devolucao) ou passe o caminho dela.

Seguro: cada troca so e aplicada se o texto original aparecer exatamente
1 vez no arquivo. Se qualquer uma das trocas nao bater (arquivo mudou,
caminho errado, etc.), o script NAO grava nada -- lista os problemas e
para. So escreve os arquivos se TODAS as trocas do arquivo baterem.
"""
import sys
import os

REPO = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

# cada entrada: (caminho relativo ao repo, [ (texto_antigo, texto_novo), ... ])
TROCAS = [
    ("devolucoes/templates/devolucoes/relatorio_devolucao_impressao.html", [
        (
            '.produto-foto, .produto-foto-vazia { width: 44px; height: 44px; border-radius: 8px; object-fit: cover; flex-shrink: 0; }',
            '.produto-foto, .produto-foto-vazia { width: 44px; height: 44px; border-radius: 8px; object-fit: contain; flex-shrink: 0; }',
        ),
        (
            '.peca-foto, .peca-foto-vazia { width: 32px; height: 32px; border-radius: 6px; object-fit: cover; }',
            '.peca-foto, .peca-foto-vazia { width: 32px; height: 32px; border-radius: 6px; object-fit: contain; }',
        ),
        (
            '.peca-card-foto, .peca-card-foto-vazia { width: 56px; height: 56px; border-radius: 6px; object-fit: cover; flex-shrink: 0; }',
            '.peca-card-foto, .peca-card-foto-vazia { width: 56px; height: 56px; border-radius: 6px; object-fit: contain; flex-shrink: 0; }',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_produtos.css", [
        (
            '.produtos-item-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n}',
            '.produtos-item-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    display: block;\n}',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_devolucoes_pendentes.css", [
        (
            '.dp-item-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n}',
            '.dp-item-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n}',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_catalogo.css", [
        (
            '.catalogo-peca-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n}',
            '.catalogo-peca-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    display: block;\n}',
        ),
        (
            '.catalogo-preview-imagem {\n    display: block;\n    width: 96px;\n    height: 96px;\n    object-fit: cover;\n}',
            '.catalogo-preview-imagem {\n    display: block;\n    width: 96px;\n    height: 96px;\n    object-fit: contain;\n}',
        ),
        (
            '.catalogo-resultado-peca-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n}',
            '.catalogo-resultado-peca-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n}',
        ),
        (
            '.catalogo-peca-card-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n}',
            '.catalogo-peca-card-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    display: block;\n}',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_produto_form.css", [
        (
            '.produto-form-foto-uploader img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    position: absolute;\n    inset: 0;\n}',
            '.produto-form-foto-uploader img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    position: absolute;\n    inset: 0;\n}',
        ),
        (
            '.gaveta-vinculo-resultado-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n}',
            '.gaveta-vinculo-resultado-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n}',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_gaveta_pecas.css", [
        (
            '.gaveta-peca-card-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n}',
            '.gaveta-peca-card-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    display: block;\n}',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_nova_devolucao.css", [
        (
            '.nd-produto-resultado-foto {\n    width: 36px;\n    height: 36px;\n    border-radius: 6px;\n    object-fit: cover;\n    flex-shrink: 0;\n    background-color: var(--cor-fundo-pagina);\n}',
            '.nd-produto-resultado-foto {\n    width: 36px;\n    height: 36px;\n    border-radius: 6px;\n    object-fit: contain;\n    flex-shrink: 0;\n    background-color: var(--cor-fundo-pagina);\n}',
        ),
        (
            '.nd-produto-card img,\n.nd-produto-sem-foto {\n    width: 56px;\n    height: 56px;\n    border-radius: 8px;\n    object-fit: cover;\n    flex-shrink: 0;\n}',
            '.nd-produto-card img,\n.nd-produto-sem-foto {\n    width: 56px;\n    height: 56px;\n    border-radius: 8px;\n    object-fit: contain;\n    flex-shrink: 0;\n}',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_produto_vincular_pecas.css", [
        (
            '.vp-header-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n}',
            '.vp-header-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    display: block;\n}',
        ),
        (
            '.vp-card-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n}',
            '.vp-card-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    display: block;\n}',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_conferir_devolucao.css", [
        (
            '.cf-recap-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n}',
            '.cf-recap-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n}',
        ),
        (
            '.cf-peca-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n}',
            '.cf-peca-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n}',
        ),
        (
            '.cf-foto-item {\n    position: relative;\n    width: 64px;\n    height: 64px;\n    border-radius: 8px;\n    overflow: hidden;\n    border: 1px solid var(--cor-borda);\n}',
            '.cf-foto-item {\n    position: relative;\n    width: 64px;\n    height: 64px;\n    border-radius: 8px;\n    overflow: hidden;\n    border: 1px solid var(--cor-borda);\n    background: var(--cor-fundo-pagina);\n}',
        ),
        (
            '.cf-foto-item img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n}',
            '.cf-foto-item img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n}',
        ),
        (
            '.cf-foto-preview-item {\n    position: relative;\n    width: 64px;\n    height: 64px;\n    border-radius: 8px;\n    overflow: hidden;\n    border: 1.5px solid var(--cor-primaria-clara);\n}',
            '.cf-foto-preview-item {\n    position: relative;\n    width: 64px;\n    height: 64px;\n    border-radius: 8px;\n    overflow: hidden;\n    border: 1.5px solid var(--cor-primaria-clara);\n    background: var(--cor-fundo-pagina);\n}',
        ),
        (
            '.cf-foto-preview-item img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n}',
            '.cf-foto-preview-item img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n}',
        ),
    ]),

    ("devolucoes/static/devolucoes/css/layout_produto_visualizar.css", [
        (
            '.produto-view-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n}',
            '.produto-view-foto img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    display: block;\n}',
        ),
        (
            '.produto-view-peca-foto-mini img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n}',
            '.produto-view-peca-foto-mini img {\n    width: 100%;\n    height: 100%;\n    object-fit: contain;\n    display: block;\n}',
        ),
    ]),
]


def main():
    problemas = []
    conteudos = {}

    for caminho_rel, pares in TROCAS:
        caminho_abs = os.path.join(REPO, caminho_rel)
        if not os.path.isfile(caminho_abs):
            problemas.append("ARQUIVO NAO ENCONTRADO: %s" % caminho_abs)
            continue
        with open(caminho_abs, "r", encoding="utf-8") as f:
            conteudo = f.read()
        for old, new in pares:
            n = conteudo.count(old)
            if n != 1:
                problemas.append(
                    "%s: esperava 1 ocorrencia, encontrei %d, pra:\n----\n%s\n----"
                    % (caminho_rel, n, old)
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

    for caminho_abs, conteudo in conteudos.items():
        with open(caminho_abs, "w", encoding="utf-8") as f:
            f.write(conteudo)
        print("OK: %s" % caminho_abs)

    total = sum(len(pares) for _, pares in TROCAS)
    print("\n%d trocas aplicadas em %d arquivos." % (total, len(conteudos)))
    print("Revise com 'git diff' antes de commitar.")


if __name__ == "__main__":
    main()