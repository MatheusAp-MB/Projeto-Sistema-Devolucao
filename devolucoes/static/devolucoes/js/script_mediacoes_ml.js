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

    function normalizarTexto(str) {
        return (str || '')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    function itensQueBatem(painel, termo) {
        var itens = Array.prototype.slice.call(painel.querySelectorAll('.med-item, .med-enc-item'));
        if (!termo) return itens;
        return itens.filter(function (item) {
            return normalizarTexto(item.getAttribute('data-busca')).indexOf(termo) !== -1;
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
        var termo = normalizarTexto(campoBusca.value.trim());
        var resultadosPorAba = {};

        abas.forEach(function (aba) {
            var nomeAba = aba.getAttribute('data-aba');
            var painel = document.querySelector('.dp-tab-panel[data-painel="' + nomeAba + '"]');
            var encontrados = itensQueBatem(painel, termo);
            resultadosPorAba[nomeAba] = encontrados;

            aba.querySelector('.dp-aba-contagem').textContent = termo ? encontrados.length : aba.getAttribute('data-total');

            var todosItens = painel.querySelectorAll('.med-item, .med-enc-item');
            todosItens.forEach(function (item) {
                item.style.display = encontrados.indexOf(item) !== -1 ? '' : 'none';
            });
            var avisoBusca = painel.querySelector('.med-lista-vazia-busca');
            if (avisoBusca) avisoBusca.style.display = (encontrados.length > 0 || todosItens.length === 0) ? 'none' : 'block';

            // * [EXPLICACAO] -> "Encontrados pelo sistema" comeca sempre
            //   recolhido -- se a busca achar alguem la dentro, expande
            //   sozinho (mesmo principio do trocarSeNecessario pras abas:
            //   um resultado nao pode ficar escondido so porque o grupo
            //   comeca fechado).
            var grupoEncontrados = painel.querySelector('.med-grupo[data-grupo="encontrados"]');
            if (grupoEncontrados && termo) {
                var achouEmEncontrados = encontrados.some(function (item) { return item.classList.contains('med-enc-item'); });
                if (achouEmEncontrados && grupoEncontrados.getAttribute('data-recolhido') !== 'false') {
                    var botaoToggle = grupoEncontrados.querySelector('[data-toggle-grupo]');
                    var conteudoGrupo = grupoEncontrados.querySelector('.med-grupo-conteudo');
                    grupoEncontrados.setAttribute('data-recolhido', 'false');
                    if (conteudoGrupo) conteudoGrupo.hidden = false;
                    if (botaoToggle) botaoToggle.setAttribute('aria-expanded', 'true');
                }
            }
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
// Acompanhamento), mesmo padrao validado no mockup aprovado. O toggle
// "Só prazo vencendo" (só existe no grupo "acompanhamento") compõe
// (E lógico) com o chip de categoria ativo daquele mesmo grupo --
// refeito em função compartilhada (aplicarFiltrosDoGrupo) pra não
// duplicar a lógica de combinação entre o clique no chip e o clique no
// toggle. Estado do toggle não é persistido no sessionStorage (decisão
// de escopo, 20/09/2026) -- sempre começa desligado ao recarregar.
(function () {
    // * [EXPLICACAO] -> "Encontrados pelo sistema" continua filtrando por
    //   categoria (Reclamacao/+Mediacao/+Devolucao/+Mediacao+Devolucao),
    //   igual sempre foi. "Em acompanhamento" agora tem um conjunto
    //   diferente de chips (Todas/Só prazo vencendo/Só sem prazo/Última
    //   mensagem do ML ou Cliente/Última mensagem nossa) -- mutuamente
    //   exclusivos entre si (não combinam com categoria, que nem mais
    //   aparece como chip nesse grupo), lendo os data-* que a view já
    //   calcula por item (data-prazo-urgente, data-sem-prazo,
    //   data-ultimo-de). Mockup aprovado por Matheus, 21/09/2026.
    function aplicarFiltrosDoGrupo(grupoChips, lista, nomeGrupo) {
        var chipAtivo = grupoChips.querySelector('.dp-chip-filtro--ativa');
        var filtro = chipAtivo ? chipAtivo.getAttribute('data-filtro') : 'todas';

        if (nomeGrupo === 'acompanhamento') {
            lista.querySelectorAll('.med-item').forEach(function (item) {
                var ultimoDe = item.getAttribute('data-ultimo-de');
                var passa = filtro === 'todas'
                    || (filtro === 'urgente' && item.getAttribute('data-prazo-urgente') === '1')
                    || (filtro === 'semprazo' && item.getAttribute('data-sem-prazo') === '1')
                    || (filtro === 'contraparte' && ultimoDe && ultimoDe !== 'voce')
                    || (filtro === 'nossa' && ultimoDe === 'voce');
                item.style.display = passa ? '' : 'none';
            });
            return;
        }

        lista.querySelectorAll('.med-item, .med-enc-item').forEach(function (item) {
            var combinacao = item.getAttribute('data-combinacao');
            var passaCategoria = !combinacao || filtro === 'todas' || combinacao === filtro; // sem categoria ainda -- sempre passa, nunca escondido pelo filtro
            item.style.display = passaCategoria ? '' : 'none';
        });
    }

    document.querySelectorAll('[data-chips]').forEach(function (grupoChips) {
        var nomeGrupo = grupoChips.getAttribute('data-chips');
        var lista = document.querySelector('[data-lista="' + nomeGrupo + '"]');
        if (!lista) return;
        grupoChips.querySelectorAll('.dp-chip-filtro').forEach(function (chip) {
            chip.addEventListener('click', function () {
                grupoChips.querySelectorAll('.dp-chip-filtro').forEach(function (c) { c.classList.remove('dp-chip-filtro--ativa'); });
                chip.classList.add('dp-chip-filtro--ativa');
                aplicarFiltrosDoGrupo(grupoChips, lista, nomeGrupo);
            });
        });
    });

    window.aplicarFiltrosDoGrupoMediacoes = aplicarFiltrosDoGrupo;
})();

// Lembrar onde o usuario estava na lista ao trocar de conversa --
// cada clique em item da lista recarrega a pagina inteira (navegacao
// normal do Django), entao aqui a gente guarda o estado do lado
// cliente (busca, chip ativo, grupo expandido, ordenacao, rolagem) no
// sessionStorage logo antes de sair, e devolve tudo assim que a
// proxima pagina carrega -- sempre disparando os mesmos
// eventos/cliques que os handlers acima ja escutam, pra nao duplicar
// a logica de filtro em dois lugares.
(function () {
    var CHAVE = 'med_estado_lista';

    function salvarEstadoAntesDeSair() {
        try {
            var estado = { chips: {}, ordenacao: {}, scrollListas: {} };

            var campo = document.getElementById('busca-mediacoes');
            estado.busca = campo ? campo.value : '';
            estado.scrollY = window.scrollY;

            document.querySelectorAll('[data-chips]').forEach(function (grupoChips) {
                var ativo = grupoChips.querySelector('.dp-chip-filtro--ativa');
                if (ativo) estado.chips[grupoChips.getAttribute('data-chips')] = ativo.getAttribute('data-filtro');
            });

            var grupoEncontrados = document.querySelector('.med-grupo[data-grupo="encontrados"]');
            estado.grupoEncontradosAberto = grupoEncontrados ? grupoEncontrados.getAttribute('data-recolhido') === 'false' : false;

            document.querySelectorAll('.med-select-ordenacao').forEach(function (select) {
                estado.ordenacao[select.getAttribute('data-ordena-lista')] = select.value;
            });

            document.querySelectorAll('.med-lista-scroll[data-lista]').forEach(function (container) {
                estado.scrollListas[container.getAttribute('data-lista')] = container.scrollTop;
            });

            sessionStorage.setItem(CHAVE, JSON.stringify(estado));
        } catch (erro) {
            // sessionStorage indisponivel (modo privado, etc.) -- a tela
            // continua funcionando normal, so sem lembrar o estado.
        }
    }

    document.addEventListener('click', function (e) {
        if (e.target.closest('a.med-item-link, a.med-item')) {
            salvarEstadoAntesDeSair();
        }
    });

    var estadoBruto;
    try {
        estadoBruto = sessionStorage.getItem(CHAVE);
    } catch (erro) {
        return;
    }
    if (!estadoBruto) return;

    var estado;
    try {
        estado = JSON.parse(estadoBruto);
    } catch (erro) {
        return;
    }
    sessionStorage.removeItem(CHAVE);

    if (estado.chips) {
        Object.keys(estado.chips).forEach(function (nomeGrupo) {
            var grupoChips = document.querySelector('[data-chips="' + nomeGrupo + '"]');
            if (!grupoChips) return;
            var chip = grupoChips.querySelector('.dp-chip-filtro[data-filtro="' + estado.chips[nomeGrupo] + '"]');
            if (chip) chip.click();
        });
    }

    if (estado.grupoEncontradosAberto) {
        var botaoToggle = document.querySelector('[data-toggle-grupo="encontrados"]');
        var grupoEncontrados = document.querySelector('.med-grupo[data-grupo="encontrados"]');
        if (botaoToggle && grupoEncontrados && grupoEncontrados.getAttribute('data-recolhido') !== 'false') {
            botaoToggle.click();
        }
    }

    if (estado.ordenacao) {
        Object.keys(estado.ordenacao).forEach(function (nomeLista) {
            var select = document.querySelector('.med-select-ordenacao[data-ordena-lista="' + nomeLista + '"]');
            if (!select) return;
            select.value = estado.ordenacao[nomeLista];
            select.dispatchEvent(new Event('change'));
        });
    }

    var campoBuscaRestaurar = document.getElementById('busca-mediacoes');
    if (campoBuscaRestaurar && estado.busca) {
        campoBuscaRestaurar.value = estado.busca;
        campoBuscaRestaurar.dispatchEvent(new Event('input'));
    }

    requestAnimationFrame(function () {
        if (estado.scrollListas) {
            Object.keys(estado.scrollListas).forEach(function (nomeLista) {
                var container = document.querySelector('.med-lista-scroll[data-lista="' + nomeLista + '"]');
                if (container) container.scrollTop = estado.scrollListas[nomeLista];
            });
        }
        if (typeof estado.scrollY === 'number') {
            window.scrollTo(0, estado.scrollY);
        }
    });
})();


// Ordenação client-side por lista (Encontrados / Em acompanhamento) --
// não refaz consulta nenhuma, só reordena os nós que já estão na
// página. "recentes"/"antigas" usa a ordem que o servidor já manda
// (mais recente primeiro) e a inversa dela; "nome" ordena pelo
// data-produto de cada item.
(function () {
    var listasOrdenaveis = Array.prototype.slice.call(document.querySelectorAll('.med-lista-scroll[data-lista]'));
    var ordemOriginalPorLista = {};

    listasOrdenaveis.forEach(function (container) {
        var nomeLista = container.getAttribute('data-lista');
        ordemOriginalPorLista[nomeLista] = Array.prototype.slice.call(container.querySelectorAll('.med-item, .med-enc-item'));
    });

    document.querySelectorAll('.med-select-ordenacao').forEach(function (select) {
        var nomeLista = select.getAttribute('data-ordena-lista');
        var container = document.querySelector('.med-lista-scroll[data-lista="' + nomeLista + '"]');
        if (!container) return;

        select.addEventListener('change', function () {
            var base = ordemOriginalPorLista[nomeLista] || [];
            var itens = base.slice();
            if (select.value === 'antigas') {
                itens.reverse();
            } else if (select.value === 'nome') {
                itens.sort(function (a, b) {
                    return (a.getAttribute('data-produto') || '').localeCompare(b.getAttribute('data-produto') || '');
                });
            }
            var ancora = container.querySelector('.med-lista-vazia-busca') || null;
            itens.forEach(function (item) { container.insertBefore(item, ancora); });
        });
    });
})();

// Cliques nos cards do Painel Geral -- cada card só filtra/expande o que
// já está na mesma página (lista + detalhe convivem lado a lado, Painel
// Geral só aparece quando nada está selecionado) -- nenhum precisa de
// navegação nova, só filtro + scroll (menos "Mensagens novas não
// vistas", que já é um <a href> de verdade pro item, resolvido no
// template). Mockup aprovado por Matheus, 21/09/2026.
(function () {
    document.querySelectorAll('[data-ir-painel]').forEach(function (botao) {
        botao.addEventListener('click', function () {
            var alvo = botao.getAttribute('data-ir-painel');

            if (alvo === 'encerradas') {
                var abaEncerradas = document.querySelector('.dp-aba-btn[data-aba="encerradas"]');
                if (abaEncerradas) abaEncerradas.click();
                var painelEncerradas = document.querySelector('.dp-tab-panel[data-painel="encerradas"]');
                if (painelEncerradas) painelEncerradas.scrollIntoView({ behavior: 'smooth', block: 'start' });
                return;
            }

            var abaAbertas = document.querySelector('.dp-aba-btn[data-aba="abertas"]');
            if (abaAbertas && !abaAbertas.classList.contains('dp-aba-btn--ativa')) abaAbertas.click();

            if (alvo === 'encontrados') {
                var grupoEncontrados = document.querySelector('.med-grupo[data-grupo="encontrados"]');
                if (grupoEncontrados && grupoEncontrados.getAttribute('data-recolhido') !== 'false') {
                    var toggle = grupoEncontrados.querySelector('[data-toggle-grupo]');
                    if (toggle) toggle.click();
                }
                if (grupoEncontrados) grupoEncontrados.scrollIntoView({ behavior: 'smooth', block: 'start' });
                return;
            }

            // 'todas' / 'urgente' / 'semprazo' -- clica o chip
            // correspondente do grupo "Em acompanhamento" (mesma lógica
            // de sempre, só disparada por outro elemento) e rola até a
            // lista.
            var grupoChips = document.querySelector('[data-chips="acompanhamento"]');
            var chip = grupoChips ? grupoChips.querySelector('.dp-chip-filtro[data-filtro="' + alvo + '"]') : null;
            if (chip) chip.click();
            var listaAcompanhamento = document.querySelector('[data-lista="acompanhamento"]');
            if (listaAcompanhamento) listaAcompanhamento.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });
})();

// Campo de resposta (visual) -- anexo de foto com pré-visualização real,
// client-side, sem nenhum upload. Envio (com ou sem foto) ainda não
// implementado nesta tela -- o botão de enviar não tem nenhum handler de
// propósito (clicar nele não faz nada, mesmo comportamento do mockup
// aprovado). Decisão de Matheus, 21/09/2026.
(function () {
    document.querySelectorAll('.med-resposta-caixa').forEach(function (caixa) {
        var btnAnexar = caixa.querySelector('.med-resposta-anexar');
        var input = caixa.querySelector('.med-resposta-file-input');
        var tira = caixa.querySelector('.med-resposta-anexos');
        if (!btnAnexar || !input || !tira) return;

        btnAnexar.addEventListener('click', function () { input.click(); });

        input.addEventListener('change', function () {
            Array.prototype.forEach.call(input.files, function (arquivo) {
                if (arquivo.type.indexOf('image/') !== 0) return;
                var url = URL.createObjectURL(arquivo);
                var item = document.createElement('span');
                item.className = 'med-resposta-anexo';
                var img = document.createElement('img');
                img.src = url;
                img.alt = 'Anexo';
                var remover = document.createElement('button');
                remover.type = 'button';
                remover.className = 'med-resposta-anexo-remover';
                remover.title = 'Remover anexo';
                remover.innerHTML = '<i class="fas fa-xmark"></i>';
                remover.addEventListener('click', function () {
                    URL.revokeObjectURL(url);
                    item.remove();
                    tira.hidden = tira.children.length === 0;
                });
                item.appendChild(img);
                item.appendChild(remover);
                tira.appendChild(item);
            });
            tira.hidden = tira.children.length === 0;
            input.value = '';
        });
    });
})();

// Miniatura de anexo de mensagem (Mediacoes ML) abrindo no modal de
// fotos global (mesmo componente da tela de Pecas/Conferencia de
// Devolucao) -- so quando a miniatura carrega de verdade. Decisao de
// Matheus, 21/09/2026: o link por tras (proxy_anexo_mediacao) pode
// cair num redirect pro link antigo com cookie de sessao do ML quando
// a API do anexo falha -- clique normal (navegacao de pagina inteira)
// sempre funciona nesse caso, mas carregar como <img src> pode ser
// bloqueado por SameSite (mesmo motivo documentado em
// url_anexo_mensagem_fallback, varredura_mediacoes.py). Por isso so
// liga o modal (card-fotos-item) depois que a miniatura prova que
// carregou -- se nao carregar, o link continua um link normal e o
// clique cai no fallback de sempre (abrir o ML em nova guia).
(function () {
    function ativarLightbox(img) {
        img.closest('a').classList.add('card-fotos-item');
    }

    document.querySelectorAll('.med-msg-anexo-img').forEach(function (img) {
        if (img.complete && img.naturalWidth > 0) {
            ativarLightbox(img);
        } else {
            img.addEventListener('load', function () { ativarLightbox(img); });
        }
    });
})();

// Trava (com senha) da caixa de resposta do chat de Mediacoes ML --
// botao unico que liga/desliga. Liberar pede senha (valida no
// servidor, hardcoded, decisao de Matheus 21/09/2026: sem CRUD, sem
// .env); travar nao pede nada, e sempre a direcao segura. Qualquer
// falha (senha errada, erro de rede/servidor) mantem travado -- nunca
// libera sozinho.
(function () {
    var caixaTrava = document.querySelector('[data-trava-chat]');
    if (!caixaTrava) return;

    var status = caixaTrava.querySelector('.med-trava-chat-status');
    var btn = caixaTrava.querySelector('[data-trava-btn]');
    var caixaResposta = document.querySelector('[data-resposta-caixa]');
    var controles = caixaResposta ? Array.prototype.slice.call(
        caixaResposta.querySelectorAll('.med-resposta-anexar, .med-resposta-input, .med-resposta-enviar')
    ) : [];

    var URL_LIBERAR = '/mediacoes/chat/liberar/';
    var URL_TRAVAR = '/mediacoes/chat/travar/';

    function obterCsrfTokenTrava() {
        var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }

    function aplicarEstadoTrava(liberado) {
        caixaTrava.setAttribute('data-liberado', liberado ? 'true' : 'false');
        caixaTrava.classList.toggle('med-trava-chat--liberado', liberado);
        status.innerHTML = liberado
            ? '<i class="fas fa-lock-open"></i> Chat liberado'
            : '<i class="fas fa-lock"></i> Chat travado';
        btn.textContent = liberado ? 'Travar' : 'Liberar';
        controles.forEach(function (el) { el.disabled = !liberado; });
    }

    function chamarTrava(url, corpo) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': obterCsrfTokenTrava(),
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: corpo || '',
        }).then(function (resposta) {
            return resposta.json().then(function (dados) { return { status: resposta.status, dados: dados }; });
        });
    }

    btn.addEventListener('click', function () {
        var liberadoAgora = caixaTrava.getAttribute('data-liberado') === 'true';

        if (liberadoAgora) {
            chamarTrava(URL_TRAVAR).then(function (r) {
                if (r.status === 200 && r.dados.ok) {
                    aplicarEstadoTrava(false);
                } else {
                    window.alert('Não deu pra confirmar com o servidor que travou -- tente de novo.');
                }
            }).catch(function () {
                window.alert('Não deu pra confirmar com o servidor que travou -- tente de novo.');
            });
            return;
        }

        var senha = window.prompt('Senha pra liberar o chat:');
        if (senha === null) return;

        chamarTrava(URL_LIBERAR, 'senha=' + encodeURIComponent(senha)).then(function (r) {
            if (r.status === 200 && r.dados.ok) {
                aplicarEstadoTrava(true);
            } else {
                aplicarEstadoTrava(false);
                window.alert((r.dados && r.dados.erro) || 'Senha incorreta.');
            }
        }).catch(function () {
            aplicarEstadoTrava(false);
        });
    });
})();
