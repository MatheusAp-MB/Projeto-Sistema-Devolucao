// devolucoes/static/devolucoes/js/script_mediacoes_ml.js

// Função Objetivo: (1) abas Abertas/Encerradas + busca por pedido/
// cliente/produto atravessando as 2 abas — mesmo padrão de
// devolucoes_pendentes (script_devolucoes_pendentes.js), só sem filtro
// de reembolso (não existe nesta tela); e (2) abrir/fechar o modal de
// adicionar mediação manualmente.

(function () {
    var abas = Array.prototype.slice.call(document.querySelectorAll('.dp-aba-btn'));
    if (!abas.length) return;

    var campoBusca = document.getElementById('busca-mediacoes');
    var nota = document.getElementById('med-nota-outras-abas');

    function itensQueBatem(painel, termo) {
        var itens = Array.prototype.slice.call(painel.querySelectorAll('.med-item'));
        if (!termo) return itens;
        return itens.filter(function (item) {
            return item.getAttribute('data-busca').indexOf(termo) !== -1;
        });
    }

    function mostrarPainel(nomeAba) {
        abas.forEach(function (a) { a.classList.toggle('dp-aba-btn--ativa', a.getAttribute('data-aba') === nomeAba); });
        document.querySelectorAll('.dp-tab-panel').forEach(function (p) {
            p.classList.toggle('dp-tab-panel--ativa', p.getAttribute('data-painel') === nomeAba);
        });
    }

    function labelDaAba(aba) {
        return aba.textContent.trim().replace(/\d+$/, '').trim();
    }

    function atualizarTudo(trocarSeNecessario) {
        var termo = campoBusca.value.trim().toLowerCase();
        var resultadosPorAba = {};

        abas.forEach(function (aba) {
            var nomeAba = aba.getAttribute('data-aba');
            var painel = document.querySelector('.dp-tab-panel[data-painel="' + nomeAba + '"]');
            var encontrados = itensQueBatem(painel, termo);
            resultadosPorAba[nomeAba] = encontrados;

            aba.querySelector('.dp-aba-contagem').textContent = termo ? encontrados.length : aba.getAttribute('data-total');

            var todosItens = painel.querySelectorAll('.med-item');
            todosItens.forEach(function (item) {
                item.style.display = encontrados.indexOf(item) !== -1 ? '' : 'none';
            });
            var avisoBusca = painel.querySelector('.med-lista-vazia-busca');
            if (avisoBusca) avisoBusca.style.display = (encontrados.length > 0 || todosItens.length === 0) ? 'none' : 'block';
        });

        var abaAtual = document.querySelector('.dp-aba-btn--ativa').getAttribute('data-aba');

        if (trocarSeNecessario && termo && resultadosPorAba[abaAtual].length === 0) {
            var proxima = abas
                .map(function (a) { return a.getAttribute('data-aba'); })
                .find(function (nomeAba) { return resultadosPorAba[nomeAba].length > 0; });
            if (proxima) {
                mostrarPainel(proxima);
                abaAtual = proxima;
            }
        }

        if (nota) {
            if (termo) {
                var outras = abas
                    .map(function (a) { return { nomeAba: a.getAttribute('data-aba'), label: labelDaAba(a) }; })
                    .filter(function (a) { return a.nomeAba !== abaAtual && resultadosPorAba[a.nomeAba].length > 0; });

                if (outras.length) {
                    nota.style.display = 'block';
                    nota.innerHTML = 'Também encontrado em: ' + outras.map(function (a) {
                        return '<a href="#" data-ir-aba="' + a.nomeAba + '">' + a.label + ' (' + resultadosPorAba[a.nomeAba].length + ')</a>';
                    }).join(' · ');
                } else {
                    nota.style.display = 'none';
                    nota.innerHTML = '';
                }
            } else {
                nota.style.display = 'none';
                nota.innerHTML = '';
            }
        }
    }

    abas.forEach(function (aba) {
        aba.addEventListener('click', function () {
            mostrarPainel(aba.getAttribute('data-aba'));
            atualizarTudo(false);
        });
    });

    if (nota) {
        nota.addEventListener('click', function (e) {
            var alvo = e.target.closest('[data-ir-aba]');
            if (!alvo) return;
            e.preventDefault();
            mostrarPainel(alvo.getAttribute('data-ir-aba'));
            atualizarTudo(false);
        });
    }

    if (campoBusca) {
        campoBusca.addEventListener('input', function () {
            atualizarTudo(true);
        });
    }

    atualizarTudo(false);
})();

(function () {
    var modal = document.getElementById('modal-add-mediacao');
    var btnAbrir = document.getElementById('btn-abrir-modal-mediacao');
    var btnFechar = document.getElementById('btn-fechar-modal-mediacao');
    if (!modal || !btnAbrir) return;

    btnAbrir.addEventListener('click', function () {
        modal.hidden = false;
        var campo = document.getElementById('input-novo-pedido-mediacao');
        if (campo) { campo.value = ''; campo.focus(); }
    });

    if (btnFechar) {
        btnFechar.addEventListener('click', function () { modal.hidden = true; });
    }

    modal.addEventListener('click', function (e) {
        if (e.target === modal) modal.hidden = true;
    });
})();