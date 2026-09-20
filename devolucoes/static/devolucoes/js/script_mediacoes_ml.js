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

// Confirmação antes de excluir uma mediação avulsa — mesmo padrão do
// dp-form-excluir de script_devolucoes_pendentes.js, reaproveitado aqui
// porque essa tela não carrega aquele script.
(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList || !form.classList.contains('dp-form-excluir')) return;

        var botao = form.querySelector('.dp-btn--perigo');
        var numeroPedido = botao ? botao.getAttribute('data-nome') : 'esta mediação';
        if (!window.confirm('Remover a mediação avulsa do pedido ' + numeroPedido + ' desta lista? Essa ação não pode ser desfeita.')) {
            evento.preventDefault();
        }
    });
})();

// Varredura de mediacoes em segundo plano -- 2 botoes (varredura completa
// e atualizacao dos itens em acompanhamento), banner de progresso com
// poll periodico, toast de conclusao e banner de erro 100% amigavel (sem
// nada tecnico -- a mensagem crua fica so no banco/logs, nunca aqui).
// Decisao de Matheus, 20/09/2026.
(function () {
    var btnVarredura = document.getElementById('btn-varredura-completa');
    var btnAtualizar = document.getElementById('btn-atualizar-acompanhados');
    if (!btnVarredura || !btnAtualizar) return;

    var banner = document.getElementById('med-banner-progresso');
    var bannerFase = document.getElementById('med-banner-fase');
    var bannerContagem = document.getElementById('med-banner-contagem');
    var bannerBarra = document.getElementById('med-banner-barra');
    var toast = document.getElementById('med-toast-concluido');
    var toastTexto = document.getElementById('med-toast-texto');
    var bannerErro = document.getElementById('med-banner-erro');
    var bannerErroTexto = document.getElementById('med-banner-erro-texto');
    var btnFecharErro = document.getElementById('med-banner-erro-fechar');

    var URL_STATUS = '/mediacoes/varredura/status/';
    var URL_INICIAR = '/mediacoes/varredura/iniciar/';
    var URL_ATUALIZAR = '/mediacoes/varredura/atualizar-acompanhados/';

    var ROTULO_POR_TIPO = {
        completa: 'a varredura completa',
        acompanhados: 'a atualização dos itens em acompanhamento',
    };

    var rodandoAntes = false;

    function obterCsrfTokenMediacoes() {
        var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }

    function aplicarEstado(estado) {
        btnVarredura.disabled = estado.rodando;
        btnAtualizar.disabled = estado.rodando;
        btnVarredura.classList.toggle('rodando', estado.rodando);
        btnAtualizar.classList.toggle('rodando', estado.rodando);

        if (estado.rodando) {
            banner.hidden = false;
            bannerFase.textContent = estado.fase_atual || 'Processando...';
            bannerContagem.textContent = estado.total ? (estado.processados + ' de ' + estado.total + ' processados') : '';
            var fracao = estado.total ? Math.min(100, (estado.processados / estado.total) * 100) : 0;
            bannerBarra.style.width = fracao + '%';
        } else {
            banner.hidden = true;
        }

        if (rodandoAntes && !estado.rodando) {
            // * [EXPLICACAO] -> acabou de terminar (transicao true ->
            //   false) -- mostra o desfecho certo. Em vez de tentar
            //   atualizar os cards ao vivo, recarrega a pagina (mais
            //   simples e robusto) -- "a lista atualiza sozinha" fica
            //   resolvido pelo F5 automatico.
            var rotulo = ROTULO_POR_TIPO[estado.tipo_execucao] || 'a atualização';
            if (estado.tem_erro) {
                bannerErroTexto.textContent = 'Não foi possível concluir ' + rotulo + '. Os itens já processados foram salvos normalmente — clique no botão pra tentar de novo.';
                bannerErro.hidden = false;
            } else {
                bannerErro.hidden = true;
                if (estado.itens_nao_confirmados) {
                    toastTexto.textContent = 'Concluído — ' + estado.itens_nao_confirmados + ' item(ns) não puderam ser conferidos, serão tentados na próxima.';
                } else {
                    toastTexto.textContent = 'Concluído — lista atualizada.';
                }
                toast.classList.add('mostrar');
                setTimeout(function () { window.location.reload(); }, 900);
            }
        }
        rodandoAntes = estado.rodando;
    }

    function consultarStatus() {
        fetch(URL_STATUS, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resposta) { return resposta.json(); })
            .then(aplicarEstado)
            .catch(function () {});
    }

    function iniciar(url) {
        bannerErro.hidden = true;
        fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': obterCsrfTokenMediacoes(), 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function () { consultarStatus(); })
            .catch(function () {});
    }

    btnVarredura.addEventListener('click', function () { iniciar(URL_INICIAR); });
    btnAtualizar.addEventListener('click', function () { iniciar(URL_ATUALIZAR); });

    if (btnFecharErro) {
        btnFecharErro.addEventListener('click', function () { bannerErro.hidden = true; });
    }

    consultarStatus();
    setInterval(consultarStatus, 3000);
})();

// Recolher/expandir "Encontrados pelo sistema" (comeca sempre recolhido).
(function () {
    document.querySelectorAll('[data-toggle-grupo]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var nome = btn.getAttribute('data-toggle-grupo');
            var grupo = document.querySelector('.med-grupo[data-grupo="' + nome + '"]');
            var conteudo = document.querySelector('.med-grupo-conteudo[data-conteudo="' + nome + '"]');
            var expandido = grupo.getAttribute('data-recolhido') === 'false';
            grupo.setAttribute('data-recolhido', expandido ? 'true' : 'false');
            conteudo.hidden = expandido;
            btn.setAttribute('aria-expanded', String(!expandido));
        });
    });
})();

// Chips de filtro por categoria (Reclamacao/+Mediacao/+Devolucao/+
// Mediacao+Devolucao) -- independentes por grupo (Encontrados/Em
// Acompanhamento), mesmo padrao validado no mockup aprovado.
(function () {
    document.querySelectorAll('[data-chips]').forEach(function (grupoChips) {
        var nomeGrupo = grupoChips.getAttribute('data-chips');
        var lista = document.querySelector('[data-lista="' + nomeGrupo + '"]');
        if (!lista) return;
        grupoChips.querySelectorAll('.dp-chip-filtro').forEach(function (chip) {
            chip.addEventListener('click', function () {
                grupoChips.querySelectorAll('.dp-chip-filtro').forEach(function (c) { c.classList.remove('dp-chip-filtro--ativa'); });
                chip.classList.add('dp-chip-filtro--ativa');
                var filtro = chip.getAttribute('data-filtro');
                lista.querySelectorAll('.med-item, .med-enc-item').forEach(function (item) {
                    var combinacao = item.getAttribute('data-combinacao');
                    if (!combinacao) return; // sem categoria ainda -- sempre visivel, nunca escondido pelo filtro
                    item.style.display = (filtro === 'todas' || combinacao === filtro) ? '' : 'none';
                });
            });
        });
    });
})();