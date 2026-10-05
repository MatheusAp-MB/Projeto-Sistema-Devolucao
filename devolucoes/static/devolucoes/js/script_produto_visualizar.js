// devolucoes/static/devolucoes/js/script_produto_visualizar.js

// Função Objetivo: comportamento da tela "Visualizar produto" — só a
// confirmação antes de excluir o produto (o resto da tela é 100% estático,
// sem nada pra atualizar via JS: editar/vincular navegam pra outra tela e
// a lista de peças vinculadas é só leitura). Esse handler morava em
// script_produto_form.js — mudou de arquivo junto com o botão "Excluir
// produto", que virou uma ação irmã aqui em vez de ficar no rodapé do
// formulário de edição.

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList || !form.classList.contains('produto-view-form-excluir')) return;

        var botao = form.querySelector('.produto-view-acao-irma--perigo');
        var nome = botao ? botao.getAttribute('data-produto-nome') : 'este produto';
        if (!window.confirm('Excluir o produto "' + nome + '"? As peças vinculadas continuam existindo (só a ligação com este produto some).')) {
            evento.preventDefault();
        }
    });
})();

// ---------- Ordem das peças: arrastar e soltar ----------
//
// * [EXPLICAÇÃO] → pedido de Matheus (05/10/2026): a ordem das peças deste produto é a ordem em que elas
//   aparecem na Editar conferência (Visualizar devolução e relatório seguem a mesma). A pessoa arrasta a
//   peça pela alça e solta onde quer; a ordem é gravada na hora, sem botão "Salvar".
//
// * [ATENÇÃO] → usa Pointer Events (mouse E dedo na mesma lógica). Só a alça tem touch-action:none, então
//   no celular o resto da linha continua rolando a tela normalmente. Quem troca de lugar durante o
//   arrasto é sempre a peça VIZINHA, nunca a que está sendo arrastada: mover no DOM o elemento que
//   segura o ponteiro faria o navegador soltar o arrasto no meio. Se o servidor recusar a gravação, a
//   lista volta pra última ordem que ele aceitou. Teclado: setas ↑/↓ com a alça em foco.
(function () {
    var lista = document.querySelector('[data-ordenar-pecas]');
    if (!lista) return;

    var url = lista.getAttribute('data-url-ordenar');
    var status = document.getElementById('pv_status_ordem');
    var reduzirMovimento = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var arrasto = null;           // estado do arrasto em andamento (null = ninguém arrastando)
    var quadro = 0;               // id do requestAnimationFrame da rolagem automática
    var timerStatus = null;
    var timerTeclado = null;
    var filaDeGravacao = Promise.resolve();

    function linhas() {
        return Array.prototype.slice.call(lista.querySelectorAll('.produto-view-peca-linha'));
    }

    function idsAtuais() {
        return linhas().map(function (linha) { return linha.getAttribute('data-vinculo-id'); });
    }

    var ultimaOrdemGravada = idsAtuais();

    function renumerar() {
        linhas().forEach(function (linha, indice) {
            var numero = linha.querySelector('.produto-view-peca-posicao');
            if (numero) numero.textContent = String(indice + 1);
        });
    }

    function mostrarStatus(texto, erro) {
        if (!status) return;
        status.textContent = texto;
        status.classList.toggle('produto-view-status-ordem--erro', !!erro);
        clearTimeout(timerStatus);
        if (!erro) timerStatus = setTimeout(function () { status.textContent = ''; }, 2500);
    }

    function obterCsrfToken() {
        var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }

    function restaurarOrdem(ids) {
        ids.forEach(function (id) {
            var linha = lista.querySelector('[data-vinculo-id="' + id + '"]');
            if (linha) lista.appendChild(linha);
        });
        renumerar();
    }

    // Grava a ordem que está na tela agora. As gravações entram numa fila (uma por vez) pra duas
    // soltadas seguidas nunca chegarem ao servidor fora de ordem.
    function gravar() {
        filaDeGravacao = filaDeGravacao.then(function () {
            var ids = idsAtuais();
            if (ids.join(',') === ultimaOrdemGravada.join(',')) return null;

            var corpo = new URLSearchParams();
            corpo.append('vinculos', ids.join(','));
            return fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': obterCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: corpo.toString(),
            }).then(function (resposta) {
                return resposta.json().catch(function () { return {}; }).then(function (dados) {
                    return { ok: resposta.ok && dados.ok, dados: dados };
                });
            }).then(function (r) {
                if (r.ok) {
                    ultimaOrdemGravada = ids;
                    mostrarStatus('Ordem salva.', false);
                } else {
                    restaurarOrdem(ultimaOrdemGravada);
                    mostrarStatus((r.dados && r.dados.erro) || 'Não deu pra salvar a ordem. Tente de novo.', true);
                }
            }).catch(function () {
                restaurarOrdem(ultimaOrdemGravada);
                mostrarStatus('Não deu pra salvar a ordem — confira a internet e tente de novo.', true);
            });
        });
        return filaDeGravacao;
    }

    // ----- rolagem: a tela pode rolar pela janela ou por um contêiner interno -----

    function acharRolavel(elemento) {
        var pai = elemento.parentElement;
        while (pai && pai !== document.body && pai !== document.documentElement) {
            var overflowY = window.getComputedStyle(pai).overflowY;
            if ((overflowY === 'auto' || overflowY === 'scroll') && pai.scrollHeight > pai.clientHeight) return pai;
            pai = pai.parentElement;
        }
        return window;
    }

    function lerRolagem(rolavel) {
        return rolavel === window ? (window.pageYOffset || 0) : rolavel.scrollTop;
    }

    // behavior 'instant': se a tela tiver rolagem suave ligada no CSS, cada passo da rolagem automática
    // recomeçaria a animação e a tela quase não andaria durante o arrasto.
    function rolarPor(rolavel, delta) {
        if (rolavel === window) window.scrollBy({ top: delta, left: 0, behavior: 'instant' });
        else rolavel.scrollTo({ top: rolavel.scrollTop + delta, behavior: 'instant' });
    }

    function limitesVisiveis(rolavel) {
        if (rolavel === window) return { topo: 0, base: window.innerHeight };
        var caixa = rolavel.getBoundingClientRect();
        return { topo: Math.max(0, caixa.top), base: Math.min(window.innerHeight, caixa.bottom) };
    }

    // ----- arrasto -----

    function acompanharPonteiro() {
        // a linha arrastada acompanha o ponteiro: deslocamento do ponteiro + quanto a tela rolou
        // - quanto a linha já "andou" na lista por causa das trocas de lugar
        var a = arrasto;
        var dy = (a.ultimoY - a.inicioY) + (lerRolagem(a.rolavel) - a.inicioRolagem) - (a.linha.offsetTop - a.inicioTopo);
        a.linha.style.transform = 'translateY(' + dy + 'px)';
    }

    function meioDe(elemento) {
        var caixa = elemento.getBoundingClientRect();
        return caixa.top + caixa.height / 2;
    }

    function trocarComVizinho(vizinho, descendo) {
        var topoAntes = vizinho.getBoundingClientRect().top;
        if (descendo) lista.insertBefore(vizinho, arrasto.linha);
        else lista.insertBefore(vizinho, arrasto.linha.nextSibling);
        var deslocamento = topoAntes - vizinho.getBoundingClientRect().top;
        if (!reduzirMovimento && deslocamento) {
            vizinho.style.transition = 'none';
            vizinho.style.transform = 'translateY(' + deslocamento + 'px)';
            void vizinho.offsetHeight;
            vizinho.style.transition = 'transform 140ms ease';
            vizinho.style.transform = '';
        }
        acompanharPonteiro();
        renumerar();
    }

    function atualizarArrasto() {
        if (!arrasto) return;
        acompanharPonteiro();
        for (var voltas = 0; voltas < 50; voltas++) {
            var centro = meioDe(arrasto.linha);
            var proxima = arrasto.linha.nextElementSibling;
            var anterior = arrasto.linha.previousElementSibling;
            if (proxima && centro > meioDe(proxima)) trocarComVizinho(proxima, true);
            else if (anterior && centro < meioDe(anterior)) trocarComVizinho(anterior, false);
            else break;
        }
    }

    function rolarSozinho() {
        if (!arrasto) return;
        var limites = limitesVisiveis(arrasto.rolavel);
        var margem = 56;
        var delta = 0;
        if (arrasto.ultimoY < limites.topo + margem) delta = -Math.ceil(14 * (1 - Math.max(0, arrasto.ultimoY - limites.topo) / margem));
        else if (arrasto.ultimoY > limites.base - margem) delta = Math.ceil(14 * (1 - Math.max(0, limites.base - arrasto.ultimoY) / margem));
        if (delta) {
            rolarPor(arrasto.rolavel, delta);
            atualizarArrasto();
        }
        quadro = window.requestAnimationFrame(rolarSozinho);
    }

    function aoMover(evento) {
        if (!arrasto || evento.pointerId !== arrasto.pointerId) return;
        evento.preventDefault();
        arrasto.ultimoY = evento.clientY;
        atualizarArrasto();
    }

    function terminarArrasto(evento) {
        if (!arrasto || (evento && evento.pointerId !== arrasto.pointerId)) return;
        var a = arrasto;
        arrasto = null;
        window.cancelAnimationFrame(quadro);
        window.removeEventListener('pointermove', aoMover);
        window.removeEventListener('pointerup', terminarArrasto);
        window.removeEventListener('pointercancel', terminarArrasto);
        try { a.alca.releasePointerCapture(a.pointerId); } catch (erro) { /* já solto */ }
        a.linha.classList.remove('produto-view-peca-linha--arrastando');
        lista.classList.remove('produto-view-pecas-lista--arrastando');
        a.linha.style.transition = reduzirMovimento ? 'none' : 'transform 120ms ease';
        a.linha.style.transform = '';
        setTimeout(function () { a.linha.style.transition = ''; }, 160);
        renumerar();
        gravar();
    }

    lista.addEventListener('pointerdown', function (evento) {
        var alca = evento.target.closest ? evento.target.closest('.produto-view-peca-alca') : null;
        if (!alca || arrasto) return;
        if (evento.pointerType === 'mouse' && evento.button !== 0) return;

        var linha = alca.closest('.produto-view-peca-linha');
        if (!linha) return;
        evento.preventDefault();

        var rolavel = acharRolavel(lista);
        arrasto = {
            linha: linha,
            alca: alca,
            pointerId: evento.pointerId,
            rolavel: rolavel,
            inicioY: evento.clientY,
            ultimoY: evento.clientY,
            inicioRolagem: lerRolagem(rolavel),
            inicioTopo: linha.offsetTop,
        };
        try { alca.setPointerCapture(evento.pointerId); } catch (erro) { /* sem captura: os ouvintes na janela seguram */ }
        linha.style.transition = 'none';
        linha.classList.add('produto-view-peca-linha--arrastando');
        lista.classList.add('produto-view-pecas-lista--arrastando');
        window.addEventListener('pointermove', aoMover, { passive: false });
        window.addEventListener('pointerup', terminarArrasto);
        window.addEventListener('pointercancel', terminarArrasto);
        quadro = window.requestAnimationFrame(rolarSozinho);
    });

    // segurar o dedo na alça não deve abrir o menu do navegador
    lista.addEventListener('contextmenu', function (evento) {
        if (evento.target.closest && evento.target.closest('.produto-view-peca-alca')) evento.preventDefault();
    });

    // ----- teclado: com a alça em foco, ↑ e ↓ movem a peça de lugar -----
    lista.addEventListener('keydown', function (evento) {
        var alca = evento.target.closest ? evento.target.closest('.produto-view-peca-alca') : null;
        if (!alca || (evento.key !== 'ArrowUp' && evento.key !== 'ArrowDown')) return;
        evento.preventDefault();

        var linha = alca.closest('.produto-view-peca-linha');
        if (evento.key === 'ArrowUp' && linha.previousElementSibling) lista.insertBefore(linha, linha.previousElementSibling);
        else if (evento.key === 'ArrowDown' && linha.nextElementSibling) lista.insertBefore(linha.nextElementSibling, linha);
        else return;

        alca.focus();
        renumerar();
        mostrarStatus('Posição ' + (linhas().indexOf(linha) + 1) + ' de ' + linhas().length + '.', false);
        clearTimeout(timerTeclado);
        timerTeclado = setTimeout(gravar, 500);
    });
})();
