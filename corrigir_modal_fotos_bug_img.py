# -*- coding: utf-8 -*-
"""
Corrige um bug no modal de fotos: em telas onde a classe "card-fotos-item"
fica direto no proprio <img> (hoje so acontece no Resumo geral da
conferência, ex.: "apagar-05"), o modal abria mas a foto vinha quebrada.

Causa: dadosDoElemento() sempre procurava um <img> DENTRO do elemento
clicado (elemento.querySelector('img')) — funciona quando o elemento e uma
<div>/<a> que CONTEM um <img>, mas retorna nada quando o proprio elemento
clicado JA E o <img> (sobra so o fallback data-url, que nunca foi setado
nesses casos, e a imagem do modal fica vazia).

Corrige script_modal_fotos.js pra checar se o elemento clicado já é a
própria <img> antes de procurar uma dentro dele.

Como rodar:
    python3 corrigir_modal_fotos_bug_img.py [caminho_do_repo]

Seguro: so aplica se o trecho antigo bater exatamente 1 vez no arquivo. Se
nao bater, nao grava nada e avisa.
"""
import sys
import os

REPO = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

ARQUIVO = "core/static/base_compartilhada/js/script_modal_fotos.js"

ANTIGO = (
    "    function dadosDoElemento(elemento) {\n"
    "        var img = elemento.querySelector('img');\n"
    "        var url = (img && img.src) || elemento.getAttribute('data-url') || '';"
)

NOVO = (
    "    function dadosDoElemento(elemento) {\n"
    "        // O elemento com \"card-fotos-item\" às vezes É o próprio <img>\n"
    "        // (ex.: Resumo geral da conferência) e às vezes é uma <div>/<a>\n"
    "        // que só CONTÉM um <img> lá dentro (a maioria das telas). Nos\n"
    "        // dois casos precisa achar a imagem certa.\n"
    "        var img = elemento.tagName === 'IMG' ? elemento : elemento.querySelector('img');\n"
    "        var url = (img && img.src) || elemento.getAttribute('data-url') || '';"
)


def main():
    caminho_abs = os.path.join(REPO, ARQUIVO)
    if not os.path.isfile(caminho_abs):
        print("ARQUIVO NAO ENCONTRADO: %s" % caminho_abs)
        sys.exit(1)

    with open(caminho_abs, "r", encoding="utf-8") as f:
        conteudo = f.read()

    n = conteudo.count(ANTIGO)
    if n != 1:
        print("NADA FOI ALTERADO. Esperava 1 ocorrencia do trecho antigo, encontrei %d." % n)
        print("Provavelmente o arquivo ja foi mudado depois que eu gerei esse script.")
        sys.exit(1)

    conteudo = conteudo.replace(ANTIGO, NOVO)
    with open(caminho_abs, "w", encoding="utf-8") as f:
        f.write(conteudo)

    print("OK: %s" % caminho_abs)
    print("Revise com 'git diff' antes de commitar.")


if __name__ == "__main__":
    main()
