// devolucoes/static/devolucoes/js/script_modal_vinculo.js

// Função Objetivo: lógica do Modal de Vínculo (peça <-> produto) — componente
// compartilhado entre a Gaveta de Peças (abre com a peça travada, buscando o
// produto) e a tela de Produto (abre com o produto travado, buscando a
// peça — Objetivo 7). Cada tela chama uma das duas funções de abertura
// abaixo (ModalVinculo.abrirComPeca / ModalVinculo.abrirComProduto) com um
// callback "aoVincular" pra atualizar sua própria parte da tela quando o
// vínculo é criado ou atualizado com sucesso — este arquivo não conhece a
// estrutura da Gaveta nem da tela de Produto, só o modal em si (mesmo
// espírito de script_marca_widget.js: um componente único, reaproveitado,
// que lê suas URLs dos atributos data-* do próprio elemento).

var ModalVinculo = (function () {
    var elModal, elFechar, elCancelar, elConfirmar;
    var elChipPeca, elChipPecaNome, elTrocarPeca, elBuscaPecaWrap, elBuscaPeca, elResultadosPeca;
    var elChipProduto, elChipProdutoNome, elTrocarProduto, elBuscaProdutoWrap, elBuscaProduto, elResultadosProduto;
    var elNaoEncontrado, elQuantidadeWrap, elQuantidade, elDuplicidade, elDuplicidadeTexto, elNovaQuantidade, elErroGeral;

    var urlVincular, urlBuscarProdutosTemplate, urlBuscarPecasTemplate;

    var pecaTravada = null;      // {id, nome} — quando o lado peça veio travado por quem abriu o modal
    var produtoTravado = null;   // {id, nome} — quando o lado produto veio travado por quem abriu o modal
    var pecaSelecionada = null;  // {id, nome} — quando o lado peça foi escolhido pela busca
    var produtoSelecionado = null; // {id, nome} — quando o lado produto foi escolhido pela busca
    var emDuplicidade = false;
    var callbackAoVincular = null;

    var inicializado = false;

    function obterCsrfToken() {
        var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }

    function inicializar() {
        if (inicializado) return;
        elModal = document.getElementById('modal_vinculo');
        if (!elModal) return;
        inicializado = true;

        urlVincular = elModal.getAttribute('data-url-vincular');
        urlBuscarProdutosTemplate = elModal.getAttribute('data-url-buscar-produtos-template');
        urlBuscarPecasTemplate = elModal.getAttribute('data-url-buscar-pecas-template');

        elFechar = document.getElementById('modal_vinculo_fechar');
        elCancelar = document.getElementById('modal_vinculo_cancelar');
        elConfirmar = document.getElementById('modal_vinculo_confirmar');

        elChipPeca = document.getElementById('modal_vinculo_chip_peca');
        elChipPecaNome = document.getElementById('modal_vinculo_chip_peca_nome');
        elTrocarPeca = document.getElementById('modal_vinculo_trocar_peca');
        elBuscaPecaWrap = document.getElementById('modal_vinculo_busca_peca_wrap');
        elBuscaPeca = document.getElementById('modal_vinculo_busca_peca');
        elResultadosPeca = document.getElementById('modal_vinculo_resultados_peca');

        elChipProduto = document.getElementById('modal_vinculo_chip_produto');
        elChipProdutoNome = document.getElementById('modal_vinculo_chip_produto_nome');
        elTrocarProduto = document.getElementById('modal_vinculo_trocar_produto');
        elBuscaProdutoWrap = document.getElementById('modal_vinculo_busca_produto_wrap');
        elBuscaProduto = document.getElementById('modal_vinculo_busca_produto');
        elResultadosProduto = document.getElementById('modal_vinculo_resultados_produto');

        elNaoEncontrado = document.getElementById('modal_vinculo_nao_encontrado');
        elQuantidadeWrap = document.getElementById('modal_vinculo_quantidade_wrap');
        elQuantidade = document.getElementById('modal_vinculo_quantidade');
        elDuplicidade = document.getElementById('modal_vinculo_duplicidade');
        elDuplicidadeTexto = document.getElementById('modal_vinculo_duplicidade_texto');
        elNovaQuantidade = document.getElementById('modal_vinculo_nova_quantidade');
        elErroGeral = document.getElementById('modal_vinculo_erro_geral');

        elFechar.addEventListener('click', fechar);
        elCancelar.addEventListener('click', fechar);
        elModal.addEventListener('click', function (evento) {
            if (evento.target === elModal) fechar();
        });
        document.addEventListener('keydown', function (evento) {
            if (evento.key === 'Escape' && !elModal.hidden) fechar();
        });

        elConfirmar.addEventListener('click', confirmar);

        elTrocarPeca.addEventListener('click', function () {
            if (pecaTravada) return;
            pecaSelecionada = null;
            elChipPeca.hidden = true;
            elBuscaPecaWrap.hidden = false;
            elBuscaPeca.value = '';
            elResultadosPeca.hidden = true;
            elBuscaPeca.focus();
            atualizarQuantidadeVisivel();
        });

        elTrocarProduto.addEventListener('click', function () {
            if (produtoTravado) return;
            produtoSelecionado = null;
            elChipProduto.hidden = true;
            elBuscaProdutoWrap.hidden = false;
            elBuscaProduto.value = '';
            elResultadosProduto.hidden = true;
            elBuscaProduto.focus();
            atualizarQuantidadeVisivel();
        });

        var debouncePeca, debounceProduto;
        elBuscaPeca.addEventListener('input', function () {
            clearTimeout(debouncePeca);
            debouncePeca = setTimeout(function () { buscarPeca(elBuscaPeca.value); }, 300);
        });
        elBuscaProduto.addEventListener('input', function () {
            clearTimeout(debounceProduto);
            debounceProduto = setTimeout(function () { buscarProduto(elBuscaProduto.value); }, 300);
        });
    }

    function limpar() {
        pecaTravada = null;
        produtoTravado = null;
        pecaSelecionada = null;
        produtoSelecionado = null;
        emDuplicidade = false;
        callbackAoVincular = null;

        elChipPeca.hidden = true;
        elTrocarPeca.hidden = true;
        elBuscaPecaWrap.hidden = true;
        elBuscaPeca.value = '';
        elResultadosPeca.hidden = true;
        elResultadosPeca.innerHTML = '';

        elChipProduto.hidden = true;
        elTrocarProduto.hidden = true;
        elBuscaProdutoWrap.hidden = true;
        elBuscaProduto.value = '';
        elResultadosProduto.hidden = true;
        elResultadosProduto.innerHTML = '';

        elNaoEncontrado.hidden = true;
        elQuantidadeWrap.hidden = true;
        elQuantidade.value = '1';
        elDuplicidade.hidden = true;
        elNovaQuantidade.value = '1';
        elErroGeral.hidden = true;
        elErroGeral.textContent = '';

        elConfirmar.textContent = 'Vincular';
    }

    function fechar() {
        elModal.hidden = true;
        limpar();
    }

    function mostrarChipPeca(nome) {
        elChipPecaNome.textContent = nome;
        elChipPeca.hidden = false;
        elBuscaPecaWrap.hidden = true;
        elResultadosPeca.hidden = true;
        elTrocarPeca.hidden = !!pecaTravada;
    }

    function mostrarChipProduto(nome) {
        elChipProdutoNome.textContent = nome;
        elChipProduto.hidden = false;
        elBuscaProdutoWrap.hidden = true;
        elResultadosProduto.hidden = true;
        elTrocarProduto.hidden = !!produtoTravado;
    }

    function atualizarQuantidadeVisivel() {
        var pecaPronta = !!(pecaTravada || pecaSelecionada);
        var produtoPronto = !!(produtoTravado || produtoSelecionado);
        elQuantidadeWrap.hidden = !(pecaPronta && produtoPronto) || emDuplicidade;
    }

    function renderizarResultados(container, resultados, tipo) {
        container.innerHTML = '';

        if (resultados.length === 0) {
            container.hidden = true;
            elNaoEncontrado.textContent = tipo === 'peca'
                ? 'Nenhuma peça encontrada (ou ela já está vinculada a este produto).'
                : 'Nenhum produto encontrado (ou ele já está vinculado a esta peça).';
            elNaoEncontrado.hidden = false;
            return;
        }

        elNaoEncontrado.hidden = true;

        resultados.forEach(function (item) {
            var linha = document.createElement('button');
            linha.type = 'button';
            linha.className = 'gaveta-vinculo-resultado-item';

            var foto = document.createElement('div');
            foto.className = 'gaveta-vinculo-resultado-foto';
            if (item.foto_url) {
                var img = document.createElement('img');
                img.src = item.foto_url;
                img.alt = item.nome;
                foto.appendChild(img);
            } else {
                foto.textContent = 'sem foto';
            }
            linha.appendChild(foto);

            var info = document.createElement('div');
            info.className = 'gaveta-vinculo-resultado-info';

            var nomeEl = document.createElement('span');
            nomeEl.className = 'gaveta-vinculo-resultado-nome';
            nomeEl.textContent = item.nome;
            info.appendChild(nomeEl);

            var legenda = document.createElement('span');
            legenda.className = 'gaveta-vinculo-resultado-legenda';
            if (tipo === 'produto' && item.marca_nome) {
                legenda.textContent = item.marca_nome;
            } else if (tipo === 'peca' && item.usada_em && item.usada_em.length > 0) {
                legenda.textContent = 'já usada em: ' + item.usada_em.join(', ');
            }
            info.appendChild(legenda);

            linha.appendChild(info);

            linha.addEventListener('click', function () {
                if (tipo === 'peca') {
                    pecaSelecionada = {id: item.id, nome: item.nome};
                    mostrarChipPeca(item.nome);
                } else {
                    produtoSelecionado = {id: item.id, nome: item.nome};
                    mostrarChipProduto(item.nome);
                }
                atualizarQuantidadeVisivel();
            });

            container.appendChild(linha);
        });

        container.hidden = false;
    }

    function buscarPeca(termo) {
        termo = termo.trim();
        if (termo.length < 2) {
            elResultadosPeca.hidden = true;
            elNaoEncontrado.hidden = true;
            return;
        }
        if (!produtoTravado) return;

        var url = urlBuscarPecasTemplate.replace('/0/', '/' + produtoTravado.id + '/');
        fetch(url + '?q=' + encodeURIComponent(termo))
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) { renderizarResultados(elResultadosPeca, dados.resultados || [], 'peca'); });
    }

    function buscarProduto(termo) {
        termo = termo.trim();
        if (termo.length < 2) {
            elResultadosProduto.hidden = true;
            elNaoEncontrado.hidden = true;
            return;
        }
        if (!pecaTravada) return;

        var url = urlBuscarProdutosTemplate.replace('/0/', '/' + pecaTravada.id + '/');
        fetch(url + '?q=' + encodeURIComponent(termo))
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) { renderizarResultados(elResultadosProduto, dados.resultados || [], 'produto'); });
    }

    function mostrarErro(mensagem) {
        elErroGeral.textContent = mensagem;
        elErroGeral.hidden = false;
    }

    function confirmar() {
        var pecaId = pecaTravada ? pecaTravada.id : (pecaSelecionada ? pecaSelecionada.id : null);
        var produtoId = produtoTravado ? produtoTravado.id : (produtoSelecionado ? produtoSelecionado.id : null);

        if (!pecaId) { mostrarErro('Selecione a peça.'); return; }
        if (!produtoId) { mostrarErro('Selecione o produto.'); return; }

        var quantidade = emDuplicidade ? elNovaQuantidade.value : elQuantidade.value;

        elErroGeral.hidden = true;

        var corpo = 'peca_id=' + encodeURIComponent(pecaId) +
            '&produto_id=' + encodeURIComponent(produtoId) +
            '&quantidade_esperada=' + encodeURIComponent(quantidade);
        if (emDuplicidade) corpo += '&confirmar_atualizacao=1';

        fetch(urlVincular, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': obterCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: corpo,
        })
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) {
                if (dados.erro) {
                    mostrarErro(dados.erro);
                    return;
                }

                if (dados.duplicidade) {
                    emDuplicidade = true;
                    elDuplicidadeTexto.textContent = 'Essa peça já está vinculada a este produto, com quantidade esperada ' +
                        dados.quantidade_atual + '. Confirme a nova quantidade abaixo pra atualizar.';
                    elNovaQuantidade.value = dados.quantidade_atual;
                    elDuplicidade.hidden = false;
                    elQuantidadeWrap.hidden = true;
                    elConfirmar.textContent = 'Confirmar atualização';
                    return;
                }

                var callback = callbackAoVincular;
                fechar();
                if (callback) callback(dados);
            })
            .catch(function () {
                mostrarErro('Não foi possível vincular agora. Tente de novo.');
            });
    }

    function abrir() {
        inicializar();
        if (!elModal) return false;
        elModal.hidden = false;
        return true;
    }

    return {
        abrirComPeca: function (pecaId, pecaNome, aoVincular) {
            if (!abrir()) return;
            limpar();
            pecaTravada = {id: pecaId, nome: pecaNome};
            callbackAoVincular = aoVincular || null;
            mostrarChipPeca(pecaNome);
            elBuscaProdutoWrap.hidden = false;
            atualizarQuantidadeVisivel();
            setTimeout(function () { elBuscaProduto.focus(); }, 0);
        },
        abrirComProduto: function (produtoId, produtoNome, aoVincular) {
            if (!abrir()) return;
            limpar();
            produtoTravado = {id: produtoId, nome: produtoNome};
            callbackAoVincular = aoVincular || null;
            mostrarChipProduto(produtoNome);
            elBuscaPecaWrap.hidden = false;
            atualizarQuantidadeVisivel();
            setTimeout(function () { elBuscaPeca.focus(); }, 0);
        },
    };
})();