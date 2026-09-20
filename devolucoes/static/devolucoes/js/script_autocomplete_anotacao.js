// devolucoes/static/devolucoes/js/script_autocomplete_anotacao.js
//
// [RESUMO] -> Autocomplete pro campo "Anotação" de cada peça, na tela
// de Conferência — só esse campo (a "Observação geral do produto" fica
// de fora, de propósito). A lista de modelos é GLOBAL (cadastrada na
// tela "Modelos de anotação", link a partir de "Peças") e vem embutida
// 1x na página via {{ modelos_anotacao|json_script:"..." }} (ver
// conferir_devolucao.html) — não faz requisição nenhuma.
//
// Digitar sempre é aceito, mesmo que o texto não esteja na lista — o
// autocomplete só ajuda a escolher rápido, nunca trava o campo.
//
// Cada textarea ".js-anotacao-autocomplete" tem, como irmã dentro do
// mesmo ".cf-anotacao-campo", uma div ".anotacao-sugestoes" vazia (a
// caixa de sugestões daquele campo especificamente) — tudo funciona por
// delegação de evento, sem precisar de id por peça. Mesmo estilo do
// modal de fotos (script_modal_fotos.js): 1 script genérico, zero JS
// por tela.

(function () {
    var elDados = document.getElementById('dados-modelos-anotacao');
    if (!elDados) return;

    var modelos = JSON.parse(elDados.textContent || '[]');
    if (!modelos.length) return;

    var indiceDestacado = -1;
    var opcoesAtuais = [];
    var campoAtivo = null;

    function escaparHtml(texto) {
        var div = document.createElement('div');
        div.textContent = texto;
        return div.innerHTML;
    }

    function destacarTrecho(texto, filtro) {
        if (!filtro) return escaparHtml(texto);
        var indice = texto.toLowerCase().indexOf(filtro.toLowerCase());
        if (indice === -1) return escaparHtml(texto);
        var antes = escaparHtml(texto.slice(0, indice));
        var meio = escaparHtml(texto.slice(indice, indice + filtro.length));
        var depois = escaparHtml(texto.slice(indice + filtro.length));
        return antes + '<mark>' + meio + '</mark>' + depois;
    }

    function sugestoesDoCampo(campo) {
        var wrapper = campo.closest('.cf-anotacao-campo');
        return wrapper ? wrapper.querySelector('.anotacao-sugestoes') : null;
    }

    function montarSugestoes(campo, filtro) {
        var elSugestoes = sugestoesDoCampo(campo);
        if (!elSugestoes) return;

        var filtroLimpo = filtro.trim();
        opcoesAtuais = modelos.filter(function (m) {
            return m.toLowerCase().indexOf(filtroLimpo.toLowerCase()) !== -1;
        });
        indiceDestacado = -1;
        elSugestoes.innerHTML = '';

        if (opcoesAtuais.length === 0) {
            var vazio = document.createElement('div');
            vazio.className = 'anotacao-sugestoes-vazio';
            vazio.textContent = 'Nenhum modelo com esse texto — o que você digitar é salvo normalmente.';
            elSugestoes.appendChild(vazio);
            elSugestoes.hidden = false;
            return;
        }

        opcoesAtuais.forEach(function (texto) {
            var item = document.createElement('div');
            item.className = 'anotacao-sugestao';
            item.innerHTML = '<i class="fas fa-tag"></i><span>' + destacarTrecho(texto, filtroLimpo) + '</span>';
            // mousedown (não click) pra disparar antes do blur do textarea
            item.addEventListener('mousedown', function (evento) {
                evento.preventDefault();
                escolherSugestao(campo, texto);
            });
            elSugestoes.appendChild(item);
        });
        elSugestoes.hidden = false;
    }

    function escolherSugestao(campo, texto) {
        campo.value = texto;
        fecharSugestoes(campo);
        campo.focus();
    }

    function fecharSugestoes(campo) {
        var elSugestoes = sugestoesDoCampo(campo);
        if (elSugestoes) elSugestoes.hidden = true;
        indiceDestacado = -1;
    }

    function realcarItem(campo, indice) {
        var elSugestoes = sugestoesDoCampo(campo);
        if (!elSugestoes) return;
        var itens = elSugestoes.querySelectorAll('.anotacao-sugestao');
        itens.forEach(function (el, i) {
            el.classList.toggle('destacada', i === indice);
        });
        if (itens[indice]) itens[indice].scrollIntoView({ block: 'nearest' });
    }

    document.addEventListener('focusin', function (evento) {
        var campo = evento.target;
        if (!campo.classList || !campo.classList.contains('js-anotacao-autocomplete')) return;
        campoAtivo = campo;
        montarSugestoes(campo, campo.value);
    });

    document.addEventListener('input', function (evento) {
        var campo = evento.target;
        if (!campo.classList || !campo.classList.contains('js-anotacao-autocomplete')) return;
        campoAtivo = campo;
        montarSugestoes(campo, campo.value);
    });

    document.addEventListener('keydown', function (evento) {
        var campo = evento.target;
        if (!campo.classList || !campo.classList.contains('js-anotacao-autocomplete')) return;
        var elSugestoes = sugestoesDoCampo(campo);
        if (!elSugestoes || elSugestoes.hidden) return;

        if (evento.key === 'ArrowDown') {
            evento.preventDefault();
            if (!opcoesAtuais.length) return;
            indiceDestacado = (indiceDestacado + 1) % opcoesAtuais.length;
            realcarItem(campo, indiceDestacado);
        } else if (evento.key === 'ArrowUp') {
            evento.preventDefault();
            if (!opcoesAtuais.length) return;
            indiceDestacado = (indiceDestacado - 1 + opcoesAtuais.length) % opcoesAtuais.length;
            realcarItem(campo, indiceDestacado);
        } else if (evento.key === 'Enter') {
            if (indiceDestacado >= 0 && opcoesAtuais[indiceDestacado]) {
                evento.preventDefault();
                escolherSugestao(campo, opcoesAtuais[indiceDestacado]);
            }
        } else if (evento.key === 'Escape') {
            fecharSugestoes(campo);
        }
    });

    document.addEventListener('click', function (evento) {
        if (!campoAtivo) return;
        var elSugestoes = sugestoesDoCampo(campoAtivo);
        if (!elSugestoes) return;
        if (evento.target === campoAtivo || elSugestoes.contains(evento.target)) return;
        fecharSugestoes(campoAtivo);
    });
})();
