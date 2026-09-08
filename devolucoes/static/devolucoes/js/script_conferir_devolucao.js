// devolucoes/static/devolucoes/js/script_conferir_devolucao.js

// Função Objetivo: só o stepper de quantidade (peças com quantidade
// esperada > 1) — os botões +/- ajustam o <input type="number">
// nativo, que já funciona sozinho sem JS nenhum (o navegador tem seu
// próprio spinner de +/- por teclado/scroll). O toggle "Veio/Não veio"
// e o destino do produto são radio nativo pintado via :has() (ver
// layout_conferir_devolucao.css) — não dependem de JS. A anotação usa
// <details>/<summary> nativo — também sem JS.

(function () {
    document.querySelectorAll('[data-cf-stepper]').forEach(function (stepper) {
        var input = stepper.querySelector('[data-cf-stepper-input]');
        var botaoMenos = stepper.querySelector('[data-cf-stepper-menos]');
        var botaoMais = stepper.querySelector('[data-cf-stepper-mais]');
        var minimo = parseInt(input.min, 10) || 0;
        var maximo = parseInt(input.max, 10);

        function ajustar(delta) {
            var valorAtual = parseInt(input.value, 10);
            if (isNaN(valorAtual)) valorAtual = 0;

            var novoValor = Math.max(minimo, Math.min(maximo, valorAtual + delta));
            input.value = novoValor;
        }

        botaoMenos.addEventListener('click', function () { ajustar(-1); });
        botaoMais.addEventListener('click', function () { ajustar(1); });
    });
})();