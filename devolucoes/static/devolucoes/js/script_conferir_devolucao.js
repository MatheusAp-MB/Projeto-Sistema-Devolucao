// devolucoes/static/devolucoes/js/script_conferir_devolucao.js

// Função Objetivo: o stepper de quantidade (peças com quantidade
// esperada > 1) — os botões +/- ajustam o <input type="number">
// nativo, que já funciona sozinho sem JS nenhum (o navegador tem seu
// próprio spinner de +/- por teclado/scroll). O toggle "Veio/Não veio"
// e o destino do produto são radio nativo pintado via :has() (ver
// layout_conferir_devolucao.css) — não dependem de JS. A anotação usa
// <details>/<summary> nativo — também sem JS. E as fotos por peça
// (Objetivo 4) — ver comentário mais abaixo.

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

// Fotos por peça: o <input type="file" multiple> já funciona sozinho
// (clique no <label>, escolhe câmera ou galeria) mesmo sem JS nenhum —
// o JS aqui só melhora 2 coisas, e só quando o navegador suporta
// DataTransfer: 1) mostra uma prévia de cada foto escolhida antes de
// salvar, com um botão pra tirar uma foto da seleção sem precisar
// salvar primeiro; 2) clicar em "Adicionar foto" de novo ACUMULA com o
// que já tinha sido escolhido, em vez de substituir — limitação normal
// de <input type="file"> é trocar a seleção a cada novo clique;
// reconstruímos o FileList com DataTransfer pra somar em vez de trocar
// (importante pro caso de tirar várias fotos com a câmera em sequência,
// já que a câmera só entrega 1 foto por clique). Sem suporte a
// DataTransfer, o campo continua funcionando do jeito nativo, só sem
// acumular entre cliques nem prévia.
(function () {
    if (typeof DataTransfer === 'undefined') return;

    document.querySelectorAll('[data-cf-fotos-input]').forEach(function (input) {
        var container = input.closest('.cf-fotos');
        var preview = container ? container.querySelector('[data-cf-fotos-preview]') : null;
        if (!preview) return;

        var arquivosAcumulados = [];

        function atualizarInput() {
            var transferencia = new DataTransfer();
            arquivosAcumulados.forEach(function (arquivo) { transferencia.items.add(arquivo); });
            input.files = transferencia.files;
        }

        function renderizarPreview() {
            preview.innerHTML = '';

            arquivosAcumulados.forEach(function (arquivo, indice) {
                var item = document.createElement('div');
                item.className = 'cf-foto-preview-item';

                var img = document.createElement('img');
                var leitor = new FileReader();
                leitor.onload = function (evento) { img.src = evento.target.result; };
                leitor.readAsDataURL(arquivo);

                var botaoRemover = document.createElement('button');
                botaoRemover.type = 'button';
                botaoRemover.className = 'cf-foto-preview-remover';
                botaoRemover.title = 'Remover';
                botaoRemover.innerHTML = '<i class="fas fa-xmark"></i>';
                botaoRemover.addEventListener('click', function () {
                    arquivosAcumulados.splice(indice, 1);
                    atualizarInput();
                    renderizarPreview();
                });

                item.appendChild(img);
                item.appendChild(botaoRemover);
                preview.appendChild(item);
            });
        }

        input.addEventListener('change', function () {
            Array.prototype.forEach.call(input.files, function (arquivo) {
                arquivosAcumulados.push(arquivo);
            });
            atualizarInput();
            renderizarPreview();
        });
    });
})();