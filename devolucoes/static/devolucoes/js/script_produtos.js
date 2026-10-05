// devolucoes/static/devolucoes/js/script_produtos.js

// Função Objetivo: busca ao vivo na tela de Produtos. Filtra os cards
// dentro das seções de Marca/Grupo (client-side, sem ida ao servidor) e
// esconde a seção ou subseção inteira quando ela zera resultado — só
// fica visível o que bate com o termo digitado.

(function () {
    var campoBusca = document.getElementById('produtos_busca');
    var vazioBusca = document.getElementById('produtos_vazio_busca');
    var lista = document.getElementById('produtos_lista');

    if (!campoBusca || !lista) return;

    function normalizar(texto) {
        return (texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    }

    function filtrarItens(container, termos) {
        var algumVisivel = false;
        container.querySelectorAll('[data-item]').forEach(function (item) {
            var textoItem = normalizar(item.getAttribute('data-busca'));
            var bate = termos.every(function (termo) {
                return textoItem.indexOf(termo) !== -1;
            });
            item.style.display = bate ? '' : 'none';
            if (bate) algumVisivel = true;
        });
        return algumVisivel;
    }

    campoBusca.addEventListener('input', function () {
        var termos = normalizar(campoBusca.value).split(/\s+/).filter(Boolean);
        var algumaSecaoVisivel = false;

        lista.querySelectorAll('[data-secao]').forEach(function (secao) {
            var algumItemNaSecao = false;
            var subsecoes = secao.querySelectorAll('[data-subsecao]');

            if (subsecoes.length > 0) {
                subsecoes.forEach(function (sub) {
                    var algumItemNaSub = filtrarItens(sub, termos);
                    sub.hidden = !algumItemNaSub;
                    if (algumItemNaSub) algumItemNaSecao = true;
                });
            } else {
                algumItemNaSecao = filtrarItens(secao, termos);
            }

            secao.hidden = !algumItemNaSecao;
            if (algumItemNaSecao) algumaSecaoVisivel = true;
        });

        if (vazioBusca) vazioBusca.hidden = algumaSecaoVisivel;
    });

    // * [EXPLICAÇÃO] → pedido de Matheus (05/10/2026): voltar pra esta lista (botão "Voltar
    //   para Produtos" ou o voltar do navegador) devolve a busca e a posição da rolagem de
    //   quando a pessoa saiu. A busca é filtro feito por JavaScript — o navegador não refaz
    //   sozinho — então a foto dela é guardada/aplicada por EstadoDaTela (script_global.js).
    function refazerBusca() {
        campoBusca.dispatchEvent(new Event('input'));
    }

    // Cada marca tem a sua fila de cards que rola pro lado (.produtos-grade): a posição de cada
    // fila também é guardada (na ordem em que aparecem na página) pra pessoa não ter que
    // rolar de novo pra achar o produto.
    function lerFilas() {
        return Array.prototype.map.call(lista.querySelectorAll('.produtos-grade'), function (fila) { return Math.round(fila.scrollLeft); });
    }

    function aplicarFilas(posicoes) {
        if (!Array.isArray(posicoes)) return;
        Array.prototype.forEach.call(lista.querySelectorAll('.produtos-grade'), function (fila, i) {
            if (typeof posicoes[i] === 'number' && posicoes[i] > 0) fila.scrollLeft = posicoes[i];
        });
    }

    if (window.EstadoDaTela) {
        window.EstadoDaTela.registrar(
            function () { return { busca: campoBusca.value, filas: lerFilas() }; },
            function (dados) {
                if (typeof dados.busca === 'string' && dados.busca) {
                    campoBusca.value = dados.busca.slice(0, 200);
                    refazerBusca();          // a busca esconde cards: as filas só podem ser posicionadas depois
                }
                aplicarFilas(dados.filas);
            }
        );
    }

    // Se o navegador devolver o texto do campo por conta própria (voltar do navegador), a lista
    // tem que acompanhar o campo — senão ele mostra um texto e a lista continua inteira.
    window.addEventListener('pageshow', function () {
        if (campoBusca.value) refazerBusca();
    });
})();