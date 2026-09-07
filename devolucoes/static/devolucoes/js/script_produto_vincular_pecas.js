// devolucoes/static/devolucoes/js/script_produto_vincular_pecas.js

// Função Objetivo: comportamentos da tela "Vincular peças" — busca +
// filtro de marca + "ver só as selecionadas" (mesmo padrão de
// aplicarFiltros/bateFiltros/filtrarCarrossel de script_gaveta_pecas.js)
// e o contador ao vivo de peças selecionadas no rodapé. Tudo isso é só
// enfeite client-side: o núcleo da tela (marcar/desmarcar peça, mudar
// quantidade, salvar) é um formulário clássico com checkbox/input nativos
// dentro do próprio card (ver _card_peca_selecionavel.html) — funciona
// inteiro mesmo com este arquivo inteiro desligado. O realce visual de
// "selecionada" (borda azul, quadradinho preenchido, campo de quantidade
// aparecendo) também não depende de JS nenhum — é CSS :has(), ver a nota
// no topo de layout_produto_vincular_pecas.css.

(function () {
    var grade = document.getElementById('vp_grade');
    var campoBusca = document.getElementById('vp_busca');
    var filtroMarca = document.getElementById('vp_filtro_marca');
    var botaoToggle = document.getElementById('vp_toggle_selecionadas');
    var semResultado = document.getElementById('vp_sem_resultado');
    var contador = document.getElementById('vp_contador');

    if (!grade) return;

    var somenteSelecionadas = false;

    function normalizar(texto) {
        return (texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    }

    function bateFiltros(card, termos, marcaFiltrada) {
        var textoCard = normalizar(card.getAttribute('data-busca'));
        var bateTexto = termos.every(function (termo) { return textoCard.indexOf(termo) !== -1; });
        var bateMarca = !marcaFiltrada || card.getAttribute('data-marca-id') === marcaFiltrada;
        var checkbox = card.querySelector('.vp-card-checkbox-real');
        var bateSelecao = !somenteSelecionadas || (checkbox && checkbox.checked);
        return bateTexto && bateMarca && bateSelecao;
    }

    function filtrarCarrossel(container, termos, marcaFiltrada) {
        var algumVisivel = false;
        container.querySelectorAll('[data-item]').forEach(function (card) {
            var visivel = bateFiltros(card, termos, marcaFiltrada);
            card.style.display = visivel ? '' : 'none';
            if (visivel) algumVisivel = true;
        });
        return algumVisivel;
    }

    function aplicarFiltros() {
        var termos = normalizar(campoBusca ? campoBusca.value : '').split(/\s+/).filter(Boolean);
        var marcaFiltrada = filtroMarca ? filtroMarca.value : '';
        var algumaSecaoVisivel = false;

        grade.querySelectorAll('[data-secao]').forEach(function (secao) {
            var algumNaSecao = false;
            var subsecoes = secao.querySelectorAll('[data-subsecao]');

            if (subsecoes.length > 0) {
                subsecoes.forEach(function (sub) {
                    var algumNaSub = filtrarCarrossel(sub, termos, marcaFiltrada);
                    sub.hidden = !algumNaSub;
                    if (algumNaSub) algumNaSecao = true;
                });
            } else {
                algumNaSecao = filtrarCarrossel(secao, termos, marcaFiltrada);
            }

            secao.hidden = !algumNaSecao;
            if (algumNaSecao) algumaSecaoVisivel = true;
        });

        if (semResultado) semResultado.hidden = algumaSecaoVisivel;
    }

    function atualizarContador() {
        if (!contador) return;
        contador.textContent = grade.querySelectorAll('.vp-card-checkbox-real:checked').length;
    }

    if (campoBusca) campoBusca.addEventListener('input', aplicarFiltros);
    if (filtroMarca) filtroMarca.addEventListener('change', aplicarFiltros);

    if (botaoToggle) {
        botaoToggle.addEventListener('click', function () {
            somenteSelecionadas = !somenteSelecionadas;
            botaoToggle.classList.toggle('ativo', somenteSelecionadas);
            aplicarFiltros();
        });
    }

    // Delegação: um único listener no container cobre todos os cards, já
    // que eles nascem prontos do servidor (nenhum é recriado via JS aqui).
    grade.addEventListener('change', function (evento) {
        if (!evento.target.classList.contains('vp-card-checkbox-real')) return;
        atualizarContador();
        if (somenteSelecionadas) aplicarFiltros();
    });
})();