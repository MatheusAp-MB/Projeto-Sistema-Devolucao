// devolucoes/static/devolucoes/js/script_produto_vincular_pecas.js

// Função Objetivo: comportamentos da tela "Vincular peças" — busca +
// filtro de marca + filtro de produto + "ver só as selecionadas" (mesmo
// padrão de aplicarFiltros/bateFiltros/filtrarCarrossel de
// script_gaveta_pecas.js), o contador ao vivo de peças selecionadas no
// rodapé, o resumo "o que vai mudar" (novas / a desvincular / quantidades),
// a sanfona dos grupos por produto e o aviso ao sair com mudanças não
// salvas. Tudo isso é só enfeite client-side: o núcleo da tela
// (marcar/desmarcar peça, mudar quantidade, salvar) é um formulário
// clássico com checkbox/input nativos dentro do próprio card (ver
// _card_peca_selecionavel.html) — funciona inteiro mesmo com este arquivo
// inteiro desligado. O realce visual de "selecionada" (borda azul,
// quadradinho preenchido, campo de quantidade aparecendo) também não
// depende de JS nenhum — é CSS :has(), ver a nota no topo de
// layout_produto_vincular_pecas.css.

(function () {
    var grade = document.getElementById('vp_grade');
    var formulario = document.getElementById('form_vincular_pecas');
    var campoBusca = document.getElementById('vp_busca');
    var filtroMarca = document.getElementById('vp_filtro_marca');
    var filtroProduto = document.getElementById('vp_filtro_produto');
    var botaoToggle = document.getElementById('vp_toggle_selecionadas');
    var semResultado = document.getElementById('vp_sem_resultado');
    var contador = document.getElementById('vp_contador');
    var resumo = document.getElementById('vp_resumo_mudancas');
    var cabecalho = document.querySelector('.vp-header');
    var barraFiltros = document.getElementById('vp_filtros');

    if (!grade) return;

    var somenteSelecionadas = false;
    var enviando = false;
    var telaPequena = window.matchMedia ? window.matchMedia('(max-width: 720px)') : { matches: false };

    function normalizar(texto) {
        return (texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    }

    // ---------- altura do cabeçalho fixo: a barra de filtros gruda logo abaixo dele (só no PC, ver o CSS) ----------
    function medirCabecalho() {
        if (!cabecalho) return;
        document.documentElement.style.setProperty('--vp-header-h', cabecalho.offsetHeight + 'px');
    }
    medirCabecalho();
    window.addEventListener('resize', medirCabecalho);

    // ---------- filtros ----------
    function bateFiltros(card, termos, marcaFiltrada, produtoFiltrado) {
        var textoCard = normalizar(card.getAttribute('data-busca'));
        var bateTexto = termos.every(function (termo) { return textoCard.indexOf(termo) !== -1; });
        var bateMarca = !marcaFiltrada || card.getAttribute('data-marca-id') === marcaFiltrada;
        var bateProduto = !produtoFiltrado || (card.getAttribute('data-produtos') || '').indexOf('|' + produtoFiltrado + '|') !== -1;
        var checkbox = card.querySelector('.vp-card-checkbox-real');
        var bateSelecao = !somenteSelecionadas || (checkbox && checkbox.checked);
        return bateTexto && bateMarca && bateProduto && bateSelecao;
    }

    // Filtra os cards de um container (seção, subseção ou grupo de produto) e devolve se sobrou algum visível.
    function filtrarCards(container, termos, marcaFiltrada, produtoFiltrado) {
        var algumVisivel = false;
        container.querySelectorAll('[data-item]').forEach(function (card) {
            var visivel = bateFiltros(card, termos, marcaFiltrada, produtoFiltrado);
            card.style.display = visivel ? '' : 'none';
            if (visivel) algumVisivel = true;
        });
        return algumVisivel;
    }

    // Grupos por produto (sanfona): some o grupo que ficou sem nenhum card visível.
    function filtrarGrupos(container, termos, marcaFiltrada, produtoFiltrado, filtrosAtivos) {
        var algumNoContainer = false;
        container.querySelectorAll('[data-subgrupo-produto]').forEach(function (grupo) {
            var algum = filtrarCards(grupo, termos, marcaFiltrada, produtoFiltrado);
            grupo.hidden = !algum;
            // com filtro ligado, abre os grupos que têm resultado (a pessoa quer ver o que achou)
            if (algum && filtrosAtivos) grupo.open = true;
            if (algum) algumNoContainer = true;
        });
        return algumNoContainer;
    }

    // Estado inicial da sanfona: no PC tudo aberto; no celular só o grupo do produto que está sendo editado.
    function sanfonaPadrao() {
        grade.querySelectorAll('[data-subgrupo-produto]').forEach(function (grupo) {
            grupo.open = telaPequena.matches ? grupo.hasAttribute('data-atual') : true;
        });
    }

    function aplicarFiltros() {
        var termos = normalizar(campoBusca ? campoBusca.value : '').split(/\s+/).filter(Boolean);
        var marcaFiltrada = filtroMarca ? filtroMarca.value : '';
        var produtoFiltrado = filtroProduto ? filtroProduto.value : '';
        var filtrosAtivos = termos.length > 0 || !!marcaFiltrada || !!produtoFiltrado || somenteSelecionadas;
        var algumaSecaoVisivel = false;

        grade.querySelectorAll('[data-secao]').forEach(function (secao) {
            var algumNaSecao = false;
            var subsecoes = secao.querySelectorAll('[data-subsecao]');

            if (subsecoes.length > 0) {
                subsecoes.forEach(function (sub) {
                    var algumNaSub = filtrarGrupos(sub, termos, marcaFiltrada, produtoFiltrado, filtrosAtivos);
                    sub.hidden = !algumNaSub;
                    if (algumNaSub) algumNaSecao = true;
                });
            } else {
                algumNaSecao = filtrarGrupos(secao, termos, marcaFiltrada, produtoFiltrado, filtrosAtivos);
            }

            secao.hidden = !algumNaSecao;
            if (algumNaSecao) algumaSecaoVisivel = true;
        });

        // sem nenhum filtro: volta pro desenho padrão da sanfona (PC aberto / celular fechado)
        if (!filtrosAtivos) sanfonaPadrao();

        if (semResultado) semResultado.hidden = algumaSecaoVisivel;
    }

    // ---------- contadores, resumo do que vai mudar e aviso de saída ----------
    function contarMudancas() {
        var novas = 0, aRemover = 0, quantidades = 0;
        grade.querySelectorAll('.vp-card-checkbox-real').forEach(function (caixa) {
            if (caixa.checked && !caixa.defaultChecked) novas++;
            if (!caixa.checked && caixa.defaultChecked) aRemover++;
            if (caixa.checked && caixa.defaultChecked) {
                var qtd = caixa.closest('.vp-card').querySelector('.vp-card-qtd-input');
                if (qtd && qtd.value !== qtd.defaultValue) quantidades++;
            }
        });
        return { novas: novas, aRemover: aRemover, quantidades: quantidades };
    }

    function atualizarContador() {
        if (contador) contador.textContent = grade.querySelectorAll('.vp-card-checkbox-real:checked').length;

        grade.querySelectorAll('[data-subgrupo-produto]').forEach(function (grupo) {
            var alvo = grupo.querySelector('[data-qtd-selecionadas]');
            if (alvo) alvo.textContent = grupo.querySelectorAll('.vp-card-checkbox-real:checked').length;
        });

        if (resumo) {
            var m = contarMudancas();
            var partes = [];
            if (m.novas) partes.push('+' + m.novas + (m.novas === 1 ? ' nova' : ' novas'));
            if (m.aRemover) partes.push(m.aRemover + (m.aRemover === 1 ? ' será desvinculada' : ' serão desvinculadas'));
            if (m.quantidades) partes.push(m.quantidades + (m.quantidades === 1 ? ' quantidade alterada' : ' quantidades alteradas'));
            resumo.textContent = partes.join(' · ');
            resumo.hidden = partes.length === 0;
        }
    }

    function haMudancas() {
        var m = contarMudancas();
        return m.novas + m.aRemover + m.quantidades > 0;
    }

    // Aviso do navegador ao sair da página com mudanças não salvas (voltar, fechar a aba, trocar de tela).
    window.addEventListener('beforeunload', function (evento) {
        if (enviando || !haMudancas()) return;
        evento.preventDefault();
        evento.returnValue = '';
    });
    if (formulario) formulario.addEventListener('submit', function () { enviando = true; });

    // ---------- eventos ----------
    if (campoBusca) campoBusca.addEventListener('input', aplicarFiltros);
    if (filtroMarca) filtroMarca.addEventListener('change', aplicarFiltros);
    if (filtroProduto) filtroProduto.addEventListener('change', aplicarFiltros);

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
    grade.addEventListener('input', function (evento) {
        if (evento.target.classList.contains('vp-card-qtd-input')) atualizarContador();
    });

    // O formulário recarregado pelo navegador (voltar/atualizar) pode trazer checkboxes já mexidos: recalcula tudo.
    sanfonaPadrao();
    atualizarContador();
    if (telaPequena.addEventListener) telaPequena.addEventListener('change', function () { if (barraFiltros) aplicarFiltros(); });
})();
