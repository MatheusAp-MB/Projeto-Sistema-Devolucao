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
})();