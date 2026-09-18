// devolucoes/static/devolucoes/js/script_devolucoes_pendentes.js

// Função Objetivo: (1) confirmação antes de excluir uma devolução ou de
// marcar como impressa — ambas irreversíveis (excluir apaga peças/fotos
// em cascata; marcar como impressa não tem "desfazer" na tela, decisão
// de Matheus 18/09/2026) — e (2) toda a interação das abas do fluxo
// (Aguardando Conferência/Conferidos/Mediações Abertas/Mediações
// Encerradas/Impressos): trocar de aba, filtrar por reembolso dentro de
// Mediações Encerradas/Impressos, e a busca global por cliente/pedido/
// produto que atravessa as 5 abas sozinha. Tudo client-side porque o
// Django já manda as 5 listas prontas pro template — não existe
// requisição nova nenhuma aqui, só mostrar/esconder o que já veio.

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList) return;

        if (form.classList.contains('dp-form-excluir')) {
            var botaoExcluir = form.querySelector('.dp-btn--perigo');
            var numeroPedidoExcluir = botaoExcluir ? botaoExcluir.getAttribute('data-nome') : 'esta devolução';
            if (!window.confirm('Excluir a devolução do pedido ' + numeroPedidoExcluir + '? Essa ação não pode ser desfeita.')) {
                evento.preventDefault();
            }
            return;
        }

        if (form.classList.contains('dp-form-marcar-impressa')) {
            var botaoImpressa = form.querySelector('.dp-btn--confirmar');
            var numeroPedidoImpressa = botaoImpressa ? botaoImpressa.getAttribute('data-nome') : 'esta devolução';
            if (!window.confirm('Marcar a devolução do pedido ' + numeroPedidoImpressa + ' como impressa? Não tem como desmarcar depois.')) {
                evento.preventDefault();
            }
        }
    });
})();

(function () {
    var abas = Array.prototype.slice.call(document.querySelectorAll('.dp-aba-btn'));
    if (!abas.length) return;

    var paineis = document.querySelectorAll('.dp-tab-panel');
    var campoBusca = document.getElementById('dp-busca');
    var nota = document.getElementById('dp-nota-outras-abas');

    function bateFiltroReembolso(item, painel) {
        var chipAtiva = painel.querySelector('.dp-chip-filtro--ativa');
        if (!chipAtiva || chipAtiva.getAttribute('data-filtro') === 'todos') return true;
        return item.getAttribute('data-reembolso') === chipAtiva.getAttribute('data-filtro');
    }

    function itensQueBatem(painel, termo) {
        var itens = Array.prototype.slice.call(painel.querySelectorAll('.dp-item'));
        return itens.filter(function (item) {
            var bateBusca = !termo || item.getAttribute('data-busca').indexOf(termo) !== -1;
            return bateBusca && bateFiltroReembolso(item, painel);
        });
    }

    function mostrarPainel(nomeAba) {
        abas.forEach(function (a) { a.classList.toggle('dp-aba-btn--ativa', a.getAttribute('data-aba') === nomeAba); });
        paineis.forEach(function (p) { p.classList.toggle('dp-tab-panel--ativa', p.getAttribute('data-painel') === nomeAba); });
    }

    function labelDaAba(aba) {
        return aba.textContent.trim().replace(/\d+$/, '').trim();
    }

    // trocarSeNecessario = true só quando a própria digitação disparou a
    // atualização — assim, buscar troca de aba sozinho, mas trocar de aba
    // na mão ou clicar num chip de reembolso nunca força uma 2ª troca.
    function atualizarTudo(trocarSeNecessario) {
        var termo = campoBusca.value.trim().toLowerCase();
        var resultadosPorAba = {};

        abas.forEach(function (aba) {
            var nomeAba = aba.getAttribute('data-aba');
            var painel = document.querySelector('.dp-tab-panel[data-painel="' + nomeAba + '"]');
            var encontrados = itensQueBatem(painel, termo);
            resultadosPorAba[nomeAba] = encontrados;

            aba.querySelector('.dp-aba-contagem').textContent = termo ? encontrados.length : aba.getAttribute('data-total');

            var todosItens = painel.querySelectorAll('.dp-item');
            todosItens.forEach(function (item) {
                item.style.display = encontrados.indexOf(item) !== -1 ? '' : 'none';
            });
            var avisoBusca = painel.querySelector('.dp-vazio-busca');
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

    document.querySelectorAll('.dp-chip-filtro').forEach(function (chip) {
        chip.addEventListener('click', function () {
            var grupo = chip.closest('.dp-filtro-secundario');
            grupo.querySelectorAll('.dp-chip-filtro').forEach(function (c) { c.classList.remove('dp-chip-filtro--ativa'); });
            chip.classList.add('dp-chip-filtro--ativa');
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