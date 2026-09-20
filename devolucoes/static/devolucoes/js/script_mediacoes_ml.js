// devolucoes/static/devolucoes/js/script_mediacoes_ml.js

// Função Objetivo: troca entre as abas "Abertas"/"Encerradas" da tela
// Mediações ML — mesmo padrão de data-aba/data-painel já usado em
// devolucoes_pendentes (script_devolucoes_pendentes.js), só sem busca
// nem filtro por enquanto (entra numa próxima etapa, junto com a busca
// real de mensagens).

(function () {
    var abas = Array.prototype.slice.call(document.querySelectorAll('.dp-aba-btn'));
    if (!abas.length) return;

    abas.forEach(function (aba) {
        aba.addEventListener('click', function () {
            abas.forEach(function (a) { a.classList.toggle('dp-aba-btn--ativa', a === aba); });
            document.querySelectorAll('.dp-tab-panel').forEach(function (painel) {
                painel.classList.toggle('dp-tab-panel--ativa', painel.getAttribute('data-painel') === aba.getAttribute('data-aba'));
            });
        });
    });
})();