// devolucoes/static/devolucoes/js/script_produto_form.js

// Função Objetivo: comportamentos da tela de cadastro/edição de produto.
// Marca e Grupo Fornecedor são cadastros isolados: cada "Cadastrar" aqui
// chama o servidor na hora (AJAX) e já fica salvo no banco, independente
// de o Produto em si ser salvo depois — só a busca/seleção de uma marca
// já existente é que preenche o campo escondido marca_id, que é o único
// dado sobre marca que o formulário do produto realmente envia.

function obterCsrfToken() {
    var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
}

(function () {
    var campoBusca = document.getElementById('id_marca_busca');
    var campoMarcaId = document.getElementById('id_marca_id');
    var chipGrupo = document.getElementById('chip_grupo_fornecedor');
    var resultadosMarca = document.getElementById('marca_resultados');

    function atualizarChipGrupo() {
        if (!campoBusca || !chipGrupo) return;
        var nome = campoBusca.value.trim().toLowerCase();

        if (!nome) {
            chipGrupo.className = 'produto-form-chip-grupo sem-grupo';
            chipGrupo.textContent = '— grupo —';
            return;
        }

        var grupo = window.MARCA_GRUPO_MAP ? window.MARCA_GRUPO_MAP[nome] : undefined;
        if (grupo) {
            chipGrupo.className = 'produto-form-chip-grupo com-grupo';
            chipGrupo.textContent = 'Grupo: ' + grupo;
        } else {
            chipGrupo.className = 'produto-form-chip-grupo sem-grupo';
            chipGrupo.textContent = 'Sem grupo';
        }
    }

    function renderizarResultadosMarca(termo) {
        if (!resultadosMarca) return;
        resultadosMarca.innerHTML = '';

        var lista = (window.MARCAS_CADASTRADAS || []).filter(function (marca) {
            return marca.nome.toLowerCase().indexOf(termo) !== -1;
        }).slice(0, 10);

        lista.forEach(function (marca) {
            var item = document.createElement('button');
            item.type = 'button';
            item.className = 'produto-form-resultado-marca';

            var nomeSpan = document.createElement('span');
            nomeSpan.textContent = marca.nome;
            item.appendChild(nomeSpan);

            if (marca.grupo) {
                var grupoSpan = document.createElement('span');
                grupoSpan.className = 'produto-form-resultado-marca-grupo';
                grupoSpan.textContent = marca.grupo;
                item.appendChild(grupoSpan);
            }

            item.addEventListener('click', function () {
                campoBusca.value = marca.nome;
                campoMarcaId.value = marca.id;
                resultadosMarca.hidden = true;
                atualizarChipGrupo();
            });

            resultadosMarca.appendChild(item);
        });

        resultadosMarca.hidden = lista.length === 0;
    }

    if (campoBusca && campoMarcaId) {
        campoBusca.addEventListener('input', function () {
            var termo = campoBusca.value.trim().toLowerCase();

            // Digitar invalida a seleção anterior — só volta a valer
            // marca_id se o texto bater exatamente com uma marca que
            // já existe (permite digitar o nome certinho sem precisar
            // clicar no resultado).
            campoMarcaId.value = '';
            var correspondenciaExata = (window.MARCAS_CADASTRADAS || []).find(function (marca) {
                return marca.nome.toLowerCase() === termo;
            });
            if (correspondenciaExata) campoMarcaId.value = correspondenciaExata.id;

            atualizarChipGrupo();
            renderizarResultadosMarca(termo);
        });

        campoBusca.addEventListener('focus', function () {
            renderizarResultadosMarca(campoBusca.value.trim().toLowerCase());
        });

        document.addEventListener('click', function (evento) {
            if (!resultadosMarca) return;
            if (evento.target === campoBusca || resultadosMarca.contains(evento.target)) return;
            resultadosMarca.hidden = true;
        });

        atualizarChipGrupo();
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

    if (botaoCadastrarMarca && campoNovaMarcaNome && campoBusca && campoMarcaId) {
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

                    window.MARCAS_CADASTRADAS = window.MARCAS_CADASTRADAS || [];
                    window.MARCAS_CADASTRADAS.push({id: dados.id, nome: dados.nome, grupo: dados.grupo ? dados.grupo.nome : null});
                    window.MARCA_GRUPO_MAP = window.MARCA_GRUPO_MAP || {};
                    window.MARCA_GRUPO_MAP[dados.nome.toLowerCase()] = dados.grupo ? dados.grupo.nome : null;

                    campoBusca.value = dados.nome;
                    campoMarcaId.value = dados.id;
                    atualizarChipGrupo();

                    caixaNovaMarca.hidden = true;
                    campoNovaMarcaNome.value = '';
                    if (marcaFeedback) marcaFeedback.textContent = '';
                });
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