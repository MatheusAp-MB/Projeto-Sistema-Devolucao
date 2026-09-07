// devolucoes/static/devolucoes/js/script_produto_form.js

// Função Objetivo: comportamentos da tela de cadastro/edição de produto.
// Marca e Grupo Fornecedor são cadastros isolados: cada "Cadastrar" aqui
// chama o servidor na hora (AJAX) e já fica salvo no banco, independente
// de o Produto em si ser salvo depois. Marca em si é sempre selecionada
// de uma lista (nunca digitada livre) — o usuário abre o painel, busca
// ou clica direto numa marca existente, ou cadastra uma nova ali mesmo.

function obterCsrfToken() {
    var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
}

(function () {
    var caixa = document.getElementById('id_marca_caixa');
    var caixaTexto = document.getElementById('marca_caixa_texto');
    var campoMarcaId = document.getElementById('id_marca_id');
    var seletorWrap = document.getElementById('marca_seletor_wrap');
    var painel = document.getElementById('marca_painel');
    var busca = document.getElementById('marca_busca');
    var lista = document.getElementById('marca_lista');
    var chipGrupo = document.getElementById('chip_grupo_fornecedor');
    var marcaErro = document.getElementById('marca_erro');

    if (!caixa || !campoMarcaId) return;

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
        var filtradas = (window.MARCAS_CADASTRADAS || []).filter(function (marca) {
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
        if (!seletorWrap.contains(evento.target)) fecharPainel();
    });
    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape') fecharPainel();
    });

    // Estado inicial — editando um produto (ou reexibindo o formulário
    // depois de um erro de validação) já vem com marca_id preenchido:
    // só falta acender o chip de grupo certo.
    if (campoMarcaId.value) {
        var marcaInicial = (window.MARCAS_CADASTRADAS || []).find(function (marca) {
            return String(marca.id) === String(campoMarcaId.value);
        });
        if (marcaInicial) atualizarChipGrupo(marcaInicial.grupo);
    }

    var botaoNovaMarca = document.getElementById('botao_nova_marca');
    var caixaNovaMarca = document.getElementById('caixa_nova_marca');

    if (botaoNovaMarca && caixaNovaMarca) {
        botaoNovaMarca.addEventListener('click', function () {
            caixaNovaMarca.hidden = !caixaNovaMarca.hidden;
        });
    }

    var selectGrupo = document.getElementById('id_grupo_fornecedor');
    var caixaNovoGrupo = document.getElementById('caixa_novo_grupo');
    var campoNovoGrupoNome = document.getElementById('id_novo_grupo_fornecedor_nome');
    var marcaFeedback = document.getElementById('marca_feedback');

    if (selectGrupo && caixaNovoGrupo) {
        selectGrupo.addEventListener('change', function () {
            caixaNovoGrupo.hidden = selectGrupo.value !== '__novo__';
        });
    }

    var botaoCadastrarGrupo = document.getElementById('botao_cadastrar_grupo');
    if (botaoCadastrarGrupo && campoNovoGrupoNome && selectGrupo) {
        botaoCadastrarGrupo.addEventListener('click', function () {
            var nome = campoNovoGrupoNome.value.trim();
            if (!nome) return;

            fetch(URL_CADASTRAR_GRUPO_FORNECEDOR, {
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

    var botaoCadastrarMarca = document.getElementById('botao_cadastrar_marca');
    var campoNovaMarcaNome = document.getElementById('id_nova_marca_nome');

    if (botaoCadastrarMarca && campoNovaMarcaNome) {
        botaoCadastrarMarca.addEventListener('click', function () {
            var nome = campoNovaMarcaNome.value.trim();
            if (!nome) return;

            var grupoId = selectGrupo ? selectGrupo.value : '';
            if (grupoId === '__novo__') {
                if (marcaFeedback) marcaFeedback.textContent = 'Cadastre o grupo novo primeiro (botão "Cadastrar grupo").';
                return;
            }

            fetch(URL_CADASTRAR_MARCA, {
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
                    window.MARCAS_CADASTRADAS = window.MARCAS_CADASTRADAS || [];
                    window.MARCAS_CADASTRADAS.push(novaMarca);

                    campoNovaMarcaNome.value = '';
                    caixaNovaMarca.hidden = true;
                    if (marcaFeedback) marcaFeedback.textContent = '';

                    selecionarMarca(novaMarca);
                });
        });
    }

    var formProduto = document.getElementById('form-dados-produto');
    if (formProduto) {
        formProduto.addEventListener('submit', function (evento) {
            if (campoMarcaId.value) return;

            evento.preventDefault();
            if (marcaErro) marcaErro.hidden = false;
            abrirPainel();
            caixa.focus();
        });
    }
})();

(function () {
    var campoFoto = document.getElementById('id_foto_produto');
    var previewImagem = document.getElementById('preview_foto_produto');
    var previewTexto = document.getElementById('foto_produto_texto');

    if (!campoFoto || !previewImagem) return;

    campoFoto.addEventListener('change', function () {
        var arquivo = campoFoto.files && campoFoto.files[0];
        if (!arquivo) return;

        var leitor = new FileReader();
        leitor.onload = function (evento) {
            previewImagem.src = evento.target.result;
            previewImagem.hidden = false;
            if (previewTexto) previewTexto.hidden = true;
        };
        leitor.readAsDataURL(arquivo);
    });
})();

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList || !form.classList.contains('produto-form-excluir-wrap')) return;

        var botao = form.querySelector('.produto-form-botao-excluir');
        var nome = botao ? botao.getAttribute('data-produto-nome') : 'este produto';
        if (!window.confirm('Excluir o produto "' + nome + '"? As peças vinculadas continuam existindo (só a ligação com este produto some).')) {
            evento.preventDefault();
        }
    });
})();