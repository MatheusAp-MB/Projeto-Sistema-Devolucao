// devolucoes/static/devolucoes/js/script_marca_widget.js

// Função Objetivo: seletor de Marca reaproveitado em toda tela que
// cadastra ou edita Produto ou Peça — sempre escolhida de uma lista
// (nunca digitada livre), com busca ao vivo e cadastro rápido (Marca e,
// se precisar, Grupo Fornecedor) sem sair da tela. Cada chamada de
// inicializarSeletorMarca recebe os ids dos elementos daquela instância
// específica (mesma estrutura HTML, ids com sufixo diferente por tela) —
// URLs dos endpoints AJAX e a lista de marcas já cadastradas vêm dos
// atributos data-* do elemento "wrap", nunca de variável global.

function obterCsrfToken() {
    var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
}

function inicializarSeletorMarca(ids) {
    var wrap = document.getElementById(ids.wrap);
    var caixa = document.getElementById(ids.caixa);
    var caixaTexto = document.getElementById(ids.caixaTexto);
    var campoMarcaId = document.getElementById(ids.campoMarcaId);
    var painel = document.getElementById(ids.painel);
    var busca = document.getElementById(ids.busca);
    var lista = document.getElementById(ids.lista);
    var chipGrupo = document.getElementById(ids.chipGrupo);
    var marcaErro = document.getElementById(ids.marcaErro);
    var botaoNovaMarca = document.getElementById(ids.botaoNovaMarca);
    var caixaNovaMarca = document.getElementById(ids.caixaNovaMarca);
    var selectGrupo = document.getElementById(ids.selectGrupo);
    var caixaNovoGrupo = document.getElementById(ids.caixaNovoGrupo);
    var campoNovoGrupoNome = document.getElementById(ids.campoNovoGrupoNome);
    var marcaFeedback = document.getElementById(ids.marcaFeedback);
    var botaoCadastrarGrupo = document.getElementById(ids.botaoCadastrarGrupo);
    var botaoCadastrarMarca = document.getElementById(ids.botaoCadastrarMarca);
    var campoNovaMarcaNome = document.getElementById(ids.campoNovaMarcaNome);
    var form = document.getElementById(ids.form);

    if (!wrap || !caixa || !campoMarcaId) return;

    var urlCadastrarMarca = wrap.getAttribute('data-url-cadastrar-marca');
    var urlCadastrarGrupoFornecedor = wrap.getAttribute('data-url-cadastrar-grupo-fornecedor');

    var marcasCadastradas = [];
    try {
        marcasCadastradas = JSON.parse(wrap.getAttribute('data-marcas') || '[]');
    } catch (erro) {
        marcasCadastradas = [];
    }

    function atualizarChipGrupo(grupoNome) {
        if (!chipGrupo) return;
        if (grupoNome) {
            chipGrupo.className = 'produto-form-chip-grupo com-grupo';
            chipGrupo.textContent = 'Grupo: ' + grupoNome;
        } else {
            chipGrupo.className = 'produto-form-chip-grupo sem-grupo';
            chipGrupo.textContent = 'Sem grupo';
        }
    }

    function renderizarLista(termo) {
        termo = (termo || '').trim().toLowerCase();
        lista.innerHTML = '';

        var marcaIdAtual = campoMarcaId.value;
        var filtradas = marcasCadastradas.filter(function (marca) {
            return marca.nome.toLowerCase().indexOf(termo) !== -1;
        });

        if (filtradas.length === 0) {
            var vazio = document.createElement('div');
            vazio.className = 'produto-form-marca-painel-vazio';
            vazio.textContent = 'Nenhuma marca encontrada.';
            lista.appendChild(vazio);
            return;
        }

        filtradas.forEach(function (marca) {
            var item = document.createElement('button');
            item.type = 'button';
            item.className = 'produto-form-marca-opcao' + (String(marca.id) === String(marcaIdAtual) ? ' selecionada' : '');

            var nomeSpan = document.createElement('span');
            nomeSpan.textContent = marca.nome;
            item.appendChild(nomeSpan);

            if (marca.grupo) {
                var grupoSpan = document.createElement('span');
                grupoSpan.className = 'produto-form-marca-opcao-grupo';
                grupoSpan.textContent = marca.grupo;
                item.appendChild(grupoSpan);
            }

            item.addEventListener('click', function () { selecionarMarca(marca); });
            lista.appendChild(item);
        });
    }

    function selecionarMarca(marca) {
        campoMarcaId.value = marca.id;
        caixaTexto.textContent = marca.nome;
        caixa.classList.remove('vazio');
        if (marcaErro) marcaErro.hidden = true;
        atualizarChipGrupo(marca.grupo);
        fecharPainel();
    }

    function abrirPainel() {
        painel.hidden = false;
        caixa.classList.add('aberto');
        if (busca) {
            busca.value = '';
            renderizarLista('');
            setTimeout(function () { busca.focus(); }, 0);
        }
    }

    function fecharPainel() {
        painel.hidden = true;
        caixa.classList.remove('aberto');
    }

    caixa.addEventListener('click', function () {
        if (painel.hidden) abrirPainel(); else fecharPainel();
    });
    caixa.addEventListener('keydown', function (evento) {
        if (evento.key === 'Enter' || evento.key === ' ') {
            evento.preventDefault();
            if (painel.hidden) abrirPainel(); else fecharPainel();
        }
    });

    if (busca) busca.addEventListener('input', function () { renderizarLista(busca.value); });

    document.addEventListener('click', function (evento) {
        if (!wrap.contains(evento.target)) fecharPainel();
    });
    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape') fecharPainel();
    });

    // Estado inicial — editando (ou reexibindo depois de erro de
    // validação) já vem com marca_id preenchido: só falta acender o
    // chip de grupo certo.
    if (campoMarcaId.value) {
        var marcaInicial = marcasCadastradas.find(function (marca) {
            return String(marca.id) === String(campoMarcaId.value);
        });
        if (marcaInicial) atualizarChipGrupo(marcaInicial.grupo);
    }

    // Dentro do Modal de Peça (bem mais baixo que a página de Produto),
    // essas caixas reveladas podem nascer fora da área visível, sem
    // nenhuma pista de que precisa rolar pra baixo pra achar o que
    // acabou de abrir. scrollIntoView com "nearest" só rola quando a
    // caixa realmente não está visível — na página de Produto, onde
    // normalmente já cabe, não faz nada.
    function rolarAteVisivel(elemento) {
        requestAnimationFrame(function () {
            if (elemento.scrollIntoView) {
                elemento.scrollIntoView({behavior: 'smooth', block: 'nearest'});
            }
        });
    }

    if (botaoNovaMarca && caixaNovaMarca) {
        botaoNovaMarca.addEventListener('click', function () {
            caixaNovaMarca.hidden = !caixaNovaMarca.hidden;
            if (!caixaNovaMarca.hidden) rolarAteVisivel(caixaNovaMarca);
        });
    }

    if (selectGrupo && caixaNovoGrupo) {
        selectGrupo.addEventListener('change', function () {
            caixaNovoGrupo.hidden = selectGrupo.value !== '__novo__';
            if (!caixaNovoGrupo.hidden) rolarAteVisivel(caixaNovoGrupo);
        });
    }

    if (botaoCadastrarGrupo && campoNovoGrupoNome && selectGrupo) {
        botaoCadastrarGrupo.addEventListener('click', function () {
            var nome = campoNovoGrupoNome.value.trim();
            if (!nome) return;

            fetch(urlCadastrarGrupoFornecedor, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': obterCsrfToken(),
                },
                body: 'nome=' + encodeURIComponent(nome),
            })
                .then(function (resposta) { return resposta.json(); })
                .then(function (dados) {
                    if (dados.erro) {
                        if (marcaFeedback) marcaFeedback.textContent = dados.erro;
                        return;
                    }

                    var opcaoNova = document.createElement('option');
                    opcaoNova.value = dados.id;
                    opcaoNova.textContent = dados.nome;
                    selectGrupo.insertBefore(opcaoNova, selectGrupo.querySelector('option[value="__novo__"]'));
                    selectGrupo.value = dados.id;

                    caixaNovoGrupo.hidden = true;
                    campoNovoGrupoNome.value = '';
                    if (marcaFeedback) marcaFeedback.textContent = 'Grupo "' + dados.nome + '" cadastrado.';
                });
        });
    }

    if (botaoCadastrarMarca && campoNovaMarcaNome) {
        botaoCadastrarMarca.addEventListener('click', function () {
            var nome = campoNovaMarcaNome.value.trim();
            if (!nome) return;

            var grupoId = selectGrupo ? selectGrupo.value : '';
            if (grupoId === '__novo__') {
                if (marcaFeedback) marcaFeedback.textContent = 'Cadastre o grupo novo primeiro (botão "Cadastrar grupo").';
                return;
            }

            fetch(urlCadastrarMarca, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': obterCsrfToken(),
                },
                body: 'nome=' + encodeURIComponent(nome) + '&grupo_fornecedor_id=' + encodeURIComponent(grupoId),
            })
                .then(function (resposta) { return resposta.json(); })
                .then(function (dados) {
                    if (dados.erro) {
                        if (marcaFeedback) marcaFeedback.textContent = dados.erro;
                        return;
                    }

                    var novaMarca = {id: dados.id, nome: dados.nome, grupo: dados.grupo ? dados.grupo.nome : null};
                    marcasCadastradas.push(novaMarca);

                    campoNovaMarcaNome.value = '';
                    caixaNovaMarca.hidden = true;
                    if (marcaFeedback) marcaFeedback.textContent = '';

                    selecionarMarca(novaMarca);
                });
        });
    }

    if (form) {
        form.addEventListener('submit', function (evento) {
            if (campoMarcaId.value) return;

            evento.preventDefault();
            if (marcaErro) marcaErro.hidden = false;
            abrirPainel();
            caixa.focus();
        });
    }
}