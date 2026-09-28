// devolucoes/static/devolucoes/js/script_devolucoes_pendentes.js

// Função Objetivo: (1) confirmação antes de excluir uma devolução ou de
// marcar como impressa — ambas irreversíveis (excluir apaga peças/fotos
// em cascata; marcar como impressa não tem "desfazer" na tela, decisão
// de Matheus 18/09/2026) — e (2) toda a interação das abas do fluxo
// (Aguardando Conferência/Conferidos/Mediações Abertas/Mediações
// Encerradas/Impressos): trocar de aba, filtrar por destino (Troca/
// Usado) dentro de Conferidos/Mediações Abertas/Mediações Encerradas/
// Impressos, filtrar por reembolso dentro de Mediações Encerradas/
// Impressos (os 2 filtros combinam entre si, cada um no seu próprio
// grupo .dp-filtro-secundario[data-tipo-filtro]), e a busca global por
// cliente/pedido/produto que atravessa as 5 abas sozinha. Tudo
// client-side porque o Django já manda as 5 listas prontas pro
// template — não existe requisição nova nenhuma aqui, só mostrar/
// esconder o que já veio.

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
        var grupo = painel.querySelector('.dp-filtro-secundario[data-tipo-filtro="reembolso"]');
        var chipAtiva = grupo ? grupo.querySelector('.dp-chip-filtro--ativa') : null;
        if (!chipAtiva || chipAtiva.getAttribute('data-filtro') === 'todos') return true;
        return item.getAttribute('data-reembolso') === chipAtiva.getAttribute('data-filtro');
    }

    function bateFiltroDestino(item, painel) {
        var grupo = painel.querySelector('.dp-filtro-secundario[data-tipo-filtro="destino"]');
        var chipAtiva = grupo ? grupo.querySelector('.dp-chip-filtro--ativa') : null;
        if (!chipAtiva || chipAtiva.getAttribute('data-filtro') === 'todos') return true;
        return item.getAttribute('data-destino') === chipAtiva.getAttribute('data-filtro');
    }

    function itensQueBatem(painel, termo) {
        var itens = Array.prototype.slice.call(painel.querySelectorAll('.dp-item'));
        return itens.filter(function (item) {
            var bateBusca = !termo || item.getAttribute('data-busca').indexOf(termo) !== -1;
            return bateBusca && bateFiltroReembolso(item, painel) && bateFiltroDestino(item, painel);
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


// Ícone de evidência da mediação (card de Mediações Abertas, pedido de
// Matheus, 28/09/2026): busca sob demanda, só quando o mouse passa em
// cima do ícone — nunca carrega foto de devolução nenhuma antes disso.
// O HTML de resposta já vem pronto do backend (mesmas classes vd-*
// reaproveitadas de visualizar_devolucao) e fica em cache no próprio
// navegador por devolução, pra não buscar de novo se passar o mouse
// 2x na mesma linha.
(function () {
    var painel = document.querySelector('.dp-tab-panel[data-painel="mediacao_aberta"]');
    if (!painel) return;

    var popover = document.createElement('div');
    popover.className = 'vd-cartao dp-tabela-evidencia-popover';
    document.body.appendChild(popover);

    var cacheHtmlPorId = {};
    var idAtual = null;
    var timeoutEsconder = null;

    function posicionar(icone) {
        var retangulo = icone.getBoundingClientRect();
        var margemViewport = 10;
        // * [EXPLICAÇÃO] → esse é o vão vertical entre o ícone e o
        //   popover — de propósito bem pequeno (não usa margemViewport
        //   aqui), porque um vão grande vira uma faixa "morta" que o
        //   mouse precisa atravessar sem tocar nem no ícone nem no
        //   popover. Era exatamente isso que fechava o preview antes de
        //   dar tempo do mouse chegar nele.
        var espacamento = 4;
        var largura = popover.offsetWidth;
        var altura = popover.offsetHeight;

        var esquerda = retangulo.left + (retangulo.width / 2) - (largura / 2);
        esquerda = Math.max(margemViewport, Math.min(esquerda, window.innerWidth - largura - margemViewport));

        var acima = retangulo.top - altura - espacamento;
        var topo = acima >= margemViewport ? acima : retangulo.bottom + espacamento;

        popover.style.left = esquerda + 'px';
        popover.style.top = topo + 'px';
    }

    function esconder() {
        popover.classList.remove('dp-tabela-evidencia-popover--visivel');
        idAtual = null;
    }

    function mostrar(icone) {
        var id = icone.getAttribute('data-devolucao-id');
        var url = icone.getAttribute('data-evidencia-url');
        if (!id || !url) return;
        idAtual = id;

        function exibir(html) {
            if (idAtual !== id) return;
            popover.innerHTML = html;
            popover.classList.add('dp-tabela-evidencia-popover--visivel');
            posicionar(icone);
        }

        if (cacheHtmlPorId[id]) {
            exibir(cacheHtmlPorId[id]);
            return;
        }

        popover.innerHTML = '<p class="vd-sem-fotos">Carregando...</p>';
        popover.classList.add('dp-tabela-evidencia-popover--visivel');
        posicionar(icone);

        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resposta) { return resposta.text(); })
            .then(function (html) {
                cacheHtmlPorId[id] = html;
                exibir(html);
            })
            .catch(function () {
                if (idAtual === id) {
                    popover.innerHTML = '<p class="vd-sem-fotos">Não foi possível carregar a evidência agora.</p>';
                }
            });
    }

    painel.addEventListener('mouseover', function (evento) {
        var icone = evento.target.closest('.dp-tabela-evidencia-icone');
        if (!icone) return;
        clearTimeout(timeoutEsconder);
        mostrar(icone);
    });

    painel.addEventListener('mouseout', function (evento) {
        var icone = evento.target.closest('.dp-tabela-evidencia-icone');
        if (!icone) return;
        // * [EXPLICAÇÃO] → antes só considerava "ainda em cima" se o
        //   mouse continuasse DENTRO do ícone. Se o mouse pulasse direto
        //   do ícone pro popover (sem passar por espaço vazio no meio),
        //   isso não contava e agendava o fechamento à toa — agora conta
        //   também quando cai direto dentro do popover.
        if (icone.contains(evento.relatedTarget) || popover.contains(evento.relatedTarget)) return;
        timeoutEsconder = setTimeout(esconder, 300);
    });

    popover.addEventListener('mouseenter', function () {
        clearTimeout(timeoutEsconder);
    });

    popover.addEventListener('mouseleave', function () {
        timeoutEsconder = setTimeout(esconder, 300);
    });

    // * [EXPLICAÇÃO] → o scroll da PÁGINA fecha o popover (senão ele fica
    //   visualmente descolado do ícone conforme a lista rola). Mas o
    //   scroll de DENTRO do próprio popover (arrastando as fotos/lista
    //   dele, que tem overflow-y:auto) TAMBÉM dispara esse mesmo evento
    //   'scroll' em fase de captura — sem esse filtro, rolar o conteúdo
    //   do popover fechava ele na primeira tentativa, antes de dar tempo
    //   de ver qualquer coisa.
    window.addEventListener('scroll', function (evento) {
        if (popover.contains(evento.target)) return;
        esconder();
    }, true);
})();