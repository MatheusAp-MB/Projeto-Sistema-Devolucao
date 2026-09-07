// devolucoes/static/devolucoes/js/script_gaveta_pecas.js

// Função Objetivo: comportamentos da tela "Peças" (Gaveta de Peças) —
// busca + filtros (marca, status) client-side, expandir/recolher o card
// quando ele tem produtos vinculados, abrir/fechar o Modal de Peça
// (cadastro e edição, os dois via AJAX) e disparar o Modal de Vínculo com
// a peça travada (a lógica do modal em si mora em script_modal_vinculo.js,
// compartilhada com a tela de Produto no Objetivo 7), e as ações rápidas
// de cada card (excluir peça, desvincular de um produto). Tudo isso
// atualiza a grade na hora, sem recarregar a página.
//
// * [ATENÇÃO] → a ÚNICA situação que ainda recarrega a página é a
//               transição do estado vazio (nenhuma peça cadastrada ainda)
//               pro estado populado (grade + filtros) — o HTML dos dois
//               estados é bem diferente e só acontece uma vez na vida do
//               sistema (a primeira peça cadastrada), então não vale a
//               pena remontar essa estrutura inteira via JS. O mesmo vale
//               ao excluir a última peça restante: volta pro estado vazio
//               recarregando.
//
// * [ATENÇÃO] → a foto da peça no card tem a classe
//               catalogo-peca-foto--clicavel (reaproveitada do antigo
//               Catálogo) mas o "abrir foto grande" ainda não tem JS
//               nenhum aqui — combinei deixar isso pro Objetivo 8, junto
//               com o CSS da Gaveta, porque hoje essa classe não tem
//               nenhum estilo carregado nesta tela (layout_gaveta_pecas.css
//               ainda não existe) e não faz sentido montar um lightbox
//               agora sem CSS nenhum pra ele.

(function () {
    var grade = document.getElementById('gaveta_grade');
    var campoBusca = document.getElementById('gaveta_busca');
    var filtroMarca = document.getElementById('gaveta_filtro_marca');
    var filtroStatus = document.getElementById('gaveta_filtro_status');
    var vazioBusca = document.getElementById('gaveta_vazio_busca');

    var botaoNovaPeca = document.getElementById('gaveta_botao_nova_peca');
    var botaoNovaPecaVazio = document.getElementById('gaveta_botao_nova_peca_vazio');

    var modalPeca = document.getElementById('modal_peca');

    if (!modalPeca) return;

    var modalPecaTitulo = document.getElementById('modal_peca_titulo');
    var modalPecaFechar = document.getElementById('modal_peca_fechar');
    var modalPecaCancelar = document.getElementById('modal_peca_cancelar');
    var formModalPeca = document.getElementById('form_modal_peca');
    var campoPecaId = document.getElementById('modal_peca_id');
    var campoNome = document.getElementById('modal_peca_nome');
    var campoNomeTecnico = document.getElementById('modal_peca_nome_tecnico');
    var campoCodigoFabricante = document.getElementById('modal_peca_codigo_fabricante');
    var campoMarcaId = document.getElementById('modal_peca_marca_id');
    var marcaCaixa = document.getElementById('modal_peca_marca_caixa');
    var marcaCaixaTexto = document.getElementById('modal_peca_marca_caixa_texto');
    var chipGrupo = document.getElementById('modal_peca_chip_grupo');
    var marcaErro = document.getElementById('modal_peca_marca_erro');
    var campoImagem = document.getElementById('modal_peca_imagem');
    var previewImagem = document.getElementById('modal_peca_preview_imagem');
    var fotoTexto = document.getElementById('modal_peca_foto_texto');
    var fotoTextoTitulo = document.getElementById('modal_peca_foto_texto_titulo');
    var erroGeral = document.getElementById('modal_peca_erro_geral');
    var botaoSalvarOutra = document.getElementById('modal_peca_botao_salvar_outra');

    var marcaSeletorWrap = document.getElementById('modal_peca_marca_seletor_wrap');

    var marcasCadastradas = [];
    try {
        marcasCadastradas = JSON.parse(marcaSeletorWrap.getAttribute('data-marcas') || '[]');
    } catch (erro) {
        marcasCadastradas = [];
    }

    var urlCadastrar = modalPeca.getAttribute('data-url-cadastrar');
    var urlEditarTemplate = modalPeca.getAttribute('data-url-editar-template');
    var urlExcluirPecaTemplate = grade ? grade.getAttribute('data-url-excluir-peca-template') : null;
    var urlDesvincularTemplate = grade ? grade.getAttribute('data-url-desvincular-template') : null;

    function obterCsrfToken() {
        var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }

    function normalizar(texto) {
        return (texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    }

    // ---------- seletor de marca do Modal de Peça (widget compartilhado) ----------

    var seletorMarcaModalPeca = inicializarSeletorMarca({
        wrap: 'modal_peca_marca_seletor_wrap',
        caixa: 'modal_peca_marca_caixa',
        caixaTexto: 'modal_peca_marca_caixa_texto',
        campoMarcaId: 'modal_peca_marca_id',
        painel: 'modal_peca_marca_painel',
        busca: 'modal_peca_marca_busca',
        lista: 'modal_peca_marca_lista',
        chipGrupo: 'modal_peca_chip_grupo',
        marcaErro: 'modal_peca_marca_erro',
        botaoNovaMarca: 'modal_peca_botao_nova_marca',
        caixaNovaMarca: 'modal_peca_caixa_nova_marca',
        selectGrupo: 'modal_peca_grupo_fornecedor',
        caixaNovoGrupo: 'modal_peca_caixa_novo_grupo',
        campoNovoGrupoNome: 'modal_peca_novo_grupo_nome',
        marcaFeedback: 'modal_peca_marca_feedback',
        botaoCadastrarGrupo: 'modal_peca_botao_cadastrar_grupo',
        botaoCadastrarMarca: 'modal_peca_botao_cadastrar_marca',
        campoNovaMarcaNome: 'modal_peca_nova_marca_nome',
        form: 'form_modal_peca',
    });

    // ---------- busca + filtros da grade ----------

    function aplicarFiltros() {
        if (!grade) return;
        var termos = normalizar(campoBusca ? campoBusca.value : '').split(/\s+/).filter(Boolean);
        var marcaFiltrada = filtroMarca ? filtroMarca.value : '';
        var statusFiltrado = filtroStatus ? filtroStatus.value : '';
        var algumVisivel = false;

        grade.querySelectorAll('[data-item]').forEach(function (card) {
            var textoCard = normalizar(card.getAttribute('data-busca'));
            var bateTexto = termos.every(function (termo) { return textoCard.indexOf(termo) !== -1; });
            var bateMarca = !marcaFiltrada || card.getAttribute('data-marca-id') === marcaFiltrada;
            var bateStatus = !statusFiltrado || card.getAttribute('data-status') === statusFiltrado;
            var visivel = bateTexto && bateMarca && bateStatus;

            card.style.display = visivel ? '' : 'none';
            if (visivel) algumVisivel = true;
        });

        if (vazioBusca) vazioBusca.hidden = algumVisivel;
    }

    if (campoBusca) campoBusca.addEventListener('input', aplicarFiltros);
    if (filtroMarca) filtroMarca.addEventListener('change', aplicarFiltros);
    if (filtroStatus) filtroStatus.addEventListener('change', aplicarFiltros);

    // ---------- Modal de Peça: montar/limpar/abrir/fechar ----------

    function definirMarcaNoModal(marcaId, marcaNome) {
        if (marcaId) {
            campoMarcaId.value = marcaId;
            marcaCaixaTexto.textContent = marcaNome || '';
            marcaCaixa.classList.remove('vazio');

            var marca = marcasCadastradas.find(function (m) { return String(m.id) === String(marcaId); });
            if (chipGrupo) {
                if (marca && marca.grupo) {
                    chipGrupo.className = 'produto-form-chip-grupo com-grupo';
                    chipGrupo.textContent = 'Grupo: ' + marca.grupo;
                } else {
                    chipGrupo.className = 'produto-form-chip-grupo sem-grupo';
                    chipGrupo.textContent = 'Sem grupo';
                }
            }
        } else {
            campoMarcaId.value = '';
            marcaCaixaTexto.textContent = 'Selecione uma marca';
            marcaCaixa.classList.add('vazio');
            if (chipGrupo) {
                chipGrupo.className = 'produto-form-chip-grupo sem-grupo';
                chipGrupo.textContent = '— grupo —';
            }
        }
    }

    function resetarFormularioPeca() {
        formModalPeca.reset();
        campoPecaId.value = '';
        definirMarcaNoModal('', '');
        if (marcaErro) marcaErro.hidden = true;
        if (erroGeral) { erroGeral.hidden = true; erroGeral.textContent = ''; }
        previewImagem.hidden = true;
        previewImagem.src = '';
        if (fotoTexto) fotoTexto.hidden = false;
        if (fotoTextoTitulo) fotoTextoTitulo.textContent = 'Escolher foto *';
        campoImagem.required = true;
        if (seletorMarcaModalPeca) seletorMarcaModalPeca.resetar();
    }

    function abrirModalPecaCadastro() {
        resetarFormularioPeca();
        modalPecaTitulo.textContent = 'Cadastrar peça';
        botaoSalvarOutra.hidden = false;
        modalPeca.hidden = false;
        setTimeout(function () { campoNome.focus(); }, 0);
    }

    function abrirModalPecaEdicao(dados) {
        resetarFormularioPeca();
        modalPecaTitulo.textContent = 'Editar peça';
        campoPecaId.value = dados.id;
        campoNome.value = dados.nome || '';
        campoNomeTecnico.value = dados.nomeTecnico || '';
        campoCodigoFabricante.value = dados.codigoFabricante || '';
        definirMarcaNoModal(dados.marcaId, dados.marcaNome);

        if (dados.imagemUrl) {
            previewImagem.src = dados.imagemUrl;
            previewImagem.hidden = false;
            if (fotoTexto) fotoTexto.hidden = true;
            if (fotoTextoTitulo) fotoTextoTitulo.textContent = 'Trocar foto';
        }
        campoImagem.required = false;

        botaoSalvarOutra.hidden = true;
        modalPeca.hidden = false;
    }

    function fecharModalPeca() {
        modalPeca.hidden = true;
        resetarFormularioPeca();
    }

    if (botaoNovaPeca) botaoNovaPeca.addEventListener('click', abrirModalPecaCadastro);
    if (botaoNovaPecaVazio) botaoNovaPecaVazio.addEventListener('click', abrirModalPecaCadastro);
    modalPecaFechar.addEventListener('click', fecharModalPeca);
    modalPecaCancelar.addEventListener('click', fecharModalPeca);
    modalPeca.addEventListener('click', function (evento) {
        if (evento.target === modalPeca) fecharModalPeca();
    });
    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape' && !modalPeca.hidden) fecharModalPeca();
    });

    // ---------- preview de imagem ao escolher arquivo ----------

    campoImagem.addEventListener('change', function () {
        var arquivo = campoImagem.files && campoImagem.files[0];
        if (!arquivo) return;

        var leitor = new FileReader();
        leitor.onload = function (evento) {
            previewImagem.src = evento.target.result;
            previewImagem.hidden = false;
            if (fotoTexto) fotoTexto.hidden = true;
        };
        leitor.readAsDataURL(arquivo);
    });

    // ---------- montar/atualizar a seção de vínculo dentro de um card ----------

    function obterInfo(card) {
        return card.querySelector('.gaveta-peca-card-info');
    }

    function removerBadgeAtual(info) {
        info.querySelectorAll('.gaveta-peca-card-badge, [data-lista-produtos-vinculados]').forEach(function (el) {
            el.remove();
        });
    }

    function construirSecaoAvulsa() {
        var span = document.createElement('span');
        span.className = 'gaveta-peca-card-badge avulsa';
        span.textContent = 'Avulsa';
        return span;
    }

    function construirSecaoVinculada() {
        var frag = document.createDocumentFragment();
        var botao = document.createElement('button');
        botao.type = 'button';
        botao.className = 'gaveta-peca-card-badge vinculada';
        botao.setAttribute('data-badge-vinculo', '');
        frag.appendChild(botao);

        var lista = document.createElement('div');
        lista.className = 'gaveta-peca-card-produtos';
        lista.setAttribute('data-lista-produtos-vinculados', '');
        lista.hidden = true;
        frag.appendChild(lista);

        return frag;
    }

    function garantirListaVinculada(card) {
        var info = obterInfo(card);
        var listaAtual = info.querySelector('[data-lista-produtos-vinculados]');
        if (listaAtual) return listaAtual;

        removerBadgeAtual(info);
        info.appendChild(construirSecaoVinculada());
        card.setAttribute('data-status', 'vinculada');
        return info.querySelector('[data-lista-produtos-vinculados]');
    }

    function atualizarContagemBadge(card) {
        var info = obterInfo(card);
        var lista = info.querySelector('[data-lista-produtos-vinculados]');
        var qtd = lista ? lista.children.length : 0;

        if (qtd === 0) {
            removerBadgeAtual(info);
            info.appendChild(construirSecaoAvulsa());
            card.setAttribute('data-status', 'avulsa');
            return;
        }

        var botao = info.querySelector('[data-badge-vinculo]');
        if (botao) botao.textContent = 'Vinculada a ' + qtd + ' produto' + (qtd > 1 ? 's' : '');
        card.setAttribute('data-status', 'vinculada');
    }

    function construirLinhaProduto(compatibilidadeId, produtoNome, pecaNome) {
        var linha = document.createElement('div');
        linha.className = 'gaveta-peca-card-produto-linha';

        var span = document.createElement('span');
        span.textContent = produtoNome;
        linha.appendChild(span);

        var form = document.createElement('form');
        form.method = 'post';
        if (urlDesvincularTemplate) form.action = urlDesvincularTemplate.replace('/0/', '/' + compatibilidadeId + '/');
        form.className = 'gaveta-form-desvincular';
        form.setAttribute('data-form-desvincular', '');

        var csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = obterCsrfToken();
        form.appendChild(csrfInput);

        var botao = document.createElement('button');
        botao.type = 'submit';
        botao.className = 'gaveta-botao-desvincular';
        botao.setAttribute('data-nome-produto', produtoNome);
        botao.setAttribute('data-nome-peca', pecaNome);
        botao.textContent = 'Desvincular';
        form.appendChild(botao);

        linha.appendChild(form);
        return linha;
    }

    // ---------- montar um card novo do zero (depois de um cadastro) ----------

    function criarCard(dados) {
        var card = document.createElement('div');
        card.className = 'gaveta-peca-card';
        card.setAttribute('data-item', '');
        card.setAttribute('data-peca-id', dados.id);
        card.setAttribute('data-busca', normalizar(dados.nome) + ' ' + normalizar(dados.marcaNome));
        card.setAttribute('data-marca-id', dados.marcaId);
        card.setAttribute('data-status', 'avulsa');

        var foto = document.createElement('div');
        foto.className = 'gaveta-peca-card-foto' + (dados.imagemUrl ? ' catalogo-peca-foto--clicavel' : '');
        if (dados.imagemUrl) {
            foto.setAttribute('data-imagem-url', dados.imagemUrl);
            foto.setAttribute('data-imagem-titulo', dados.nome);
            var img = document.createElement('img');
            img.src = dados.imagemUrl;
            img.alt = dados.nome;
            foto.appendChild(img);
        } else {
            var vazia = document.createElement('span');
            vazia.className = 'gaveta-peca-card-foto-vazia';
            vazia.textContent = 'sem foto';
            foto.appendChild(vazia);
        }
        card.appendChild(foto);

        var info = document.createElement('div');
        info.className = 'gaveta-peca-card-info';

        var nomeEl = document.createElement('p');
        nomeEl.className = 'gaveta-peca-card-nome';
        nomeEl.title = dados.nome;
        nomeEl.textContent = dados.nome;
        info.appendChild(nomeEl);

        var marcaEl = document.createElement('p');
        marcaEl.className = 'gaveta-peca-card-marca';
        marcaEl.textContent = dados.marcaNome;
        info.appendChild(marcaEl);

        info.appendChild(construirSecaoAvulsa());
        card.appendChild(info);

        var rodape = document.createElement('div');
        rodape.className = 'gaveta-peca-card-rodape';

        var botaoEditar = document.createElement('button');
        botaoEditar.type = 'button';
        botaoEditar.className = 'gaveta-peca-card-acao';
        botaoEditar.setAttribute('data-abrir-modal-peca', '');
        botaoEditar.setAttribute('data-peca-id', dados.id);
        botaoEditar.setAttribute('data-peca-nome', dados.nome);
        botaoEditar.setAttribute('data-peca-nome-tecnico', dados.nomeTecnico || '');
        botaoEditar.setAttribute('data-peca-codigo-fabricante', dados.codigoFabricante || '');
        botaoEditar.setAttribute('data-peca-marca-id', dados.marcaId);
        botaoEditar.setAttribute('data-peca-marca-nome', dados.marcaNome);
        botaoEditar.setAttribute('data-peca-imagem-url', dados.imagemUrl || '');
        botaoEditar.textContent = 'Editar';
        rodape.appendChild(botaoEditar);

        if (urlExcluirPecaTemplate) {
            var formExcluir = document.createElement('form');
            formExcluir.method = 'post';
            formExcluir.action = urlExcluirPecaTemplate.replace('/0/', '/' + dados.id + '/');
            formExcluir.className = 'gaveta-form-excluir-peca';
            formExcluir.setAttribute('data-form-excluir-peca', '');

            var csrfInputExcluir = document.createElement('input');
            csrfInputExcluir.type = 'hidden';
            csrfInputExcluir.name = 'csrfmiddlewaretoken';
            csrfInputExcluir.value = obterCsrfToken();
            formExcluir.appendChild(csrfInputExcluir);

            var botaoExcluir = document.createElement('button');
            botaoExcluir.type = 'submit';
            botaoExcluir.className = 'gaveta-peca-card-acao';
            botaoExcluir.setAttribute('data-peca-nome', dados.nome);
            botaoExcluir.setAttribute('data-qtd-produtos', '0');
            botaoExcluir.textContent = 'Excluir';
            formExcluir.appendChild(botaoExcluir);

            rodape.appendChild(formExcluir);
        }

        var botaoVincular = document.createElement('button');
        botaoVincular.type = 'button';
        botaoVincular.className = 'gaveta-peca-card-acao gaveta-peca-card-acao--destaque';
        botaoVincular.setAttribute('data-abrir-modal-vinculo', '');
        botaoVincular.setAttribute('data-peca-id', dados.id);
        botaoVincular.setAttribute('data-peca-nome', dados.nome);
        botaoVincular.textContent = 'Vincular a um produto';
        rodape.appendChild(botaoVincular);

        card.appendChild(rodape);
        return card;
    }

    function inserirNovoCard(dados) {
        if (!grade) {
            // Primeira peça cadastrada no sistema — o estado vazio tem um
            // HTML totalmente diferente (sem grade, sem filtros). Mais
            // simples e seguro recarregar aqui do que remontar tudo isso
            // via JS pra um caso que só acontece uma vez.
            window.location.reload();
            return;
        }

        var card = criarCard({
            id: dados.id,
            nome: dados.nome,
            nomeTecnico: dados.nome_tecnico,
            codigoFabricante: dados.codigo_fabricante,
            marcaId: dados.marca_id,
            marcaNome: dados.marca_nome,
            imagemUrl: dados.imagem_url,
        });
        grade.insertBefore(card, grade.firstChild);
        aplicarFiltros();
    }

    function atualizarCardExistente(dados) {
        if (!grade) return;
        var card = grade.querySelector('.gaveta-peca-card[data-peca-id="' + dados.id + '"]');
        if (!card) return;

        card.setAttribute('data-busca', normalizar(dados.nome) + ' ' + normalizar(dados.marca_nome));
        card.setAttribute('data-marca-id', dados.marca_id);

        var nomeEl = card.querySelector('.gaveta-peca-card-nome');
        if (nomeEl) { nomeEl.textContent = dados.nome; nomeEl.title = dados.nome; }

        var marcaEl = card.querySelector('.gaveta-peca-card-marca');
        if (marcaEl) marcaEl.textContent = dados.marca_nome;

        var fotoEl = card.querySelector('.gaveta-peca-card-foto');
        if (fotoEl && dados.imagem_url) {
            fotoEl.className = 'gaveta-peca-card-foto catalogo-peca-foto--clicavel';
            fotoEl.setAttribute('data-imagem-url', dados.imagem_url);
            fotoEl.setAttribute('data-imagem-titulo', dados.nome);
            fotoEl.innerHTML = '';
            var img = document.createElement('img');
            img.src = dados.imagem_url;
            img.alt = dados.nome;
            fotoEl.appendChild(img);
        }

        var botaoEditar = card.querySelector('[data-abrir-modal-peca]');
        if (botaoEditar) {
            botaoEditar.setAttribute('data-peca-nome', dados.nome);
            botaoEditar.setAttribute('data-peca-nome-tecnico', dados.nome_tecnico || '');
            botaoEditar.setAttribute('data-peca-codigo-fabricante', dados.codigo_fabricante || '');
            botaoEditar.setAttribute('data-peca-marca-id', dados.marca_id);
            botaoEditar.setAttribute('data-peca-marca-nome', dados.marca_nome);
            botaoEditar.setAttribute('data-peca-imagem-url', dados.imagem_url || '');
        }

        var botaoVincular = card.querySelector('[data-abrir-modal-vinculo]');
        if (botaoVincular) botaoVincular.setAttribute('data-peca-nome', dados.nome);

        var botaoExcluir = card.querySelector('.gaveta-form-excluir-peca button[type=submit]');
        if (botaoExcluir) botaoExcluir.setAttribute('data-peca-nome', dados.nome);

        aplicarFiltros();
    }

    // ---------- submit do Modal de Peça (cadastro e edição, via AJAX) ----------

    formModalPeca.addEventListener('submit', function (evento) {
        evento.preventDefault();

        if (erroGeral) { erroGeral.hidden = true; erroGeral.textContent = ''; }
        if (marcaErro) marcaErro.hidden = true;

        if (!campoMarcaId.value) {
            if (marcaErro) marcaErro.hidden = false;
            return;
        }

        var continuarCadastrando = evento.submitter === botaoSalvarOutra;
        var ehEdicao = !!campoPecaId.value;
        var url = ehEdicao ? urlEditarTemplate.replace('/0/', '/' + campoPecaId.value + '/') : urlCadastrar;

        fetch(url, {
            method: 'POST',
            headers: {'X-CSRFToken': obterCsrfToken()},
            body: new FormData(formModalPeca),
        })
            .then(function (resposta) {
                return resposta.json().then(function (dados) { return {ok: resposta.ok, dados: dados}; });
            })
            .then(function (resultado) {
                if (!resultado.ok) {
                    if (resultado.dados.campo === 'marca' && marcaErro) {
                        marcaErro.hidden = false;
                    } else if (erroGeral) {
                        erroGeral.textContent = resultado.dados.erro;
                        erroGeral.hidden = false;
                    }
                    return;
                }

                if (ehEdicao) {
                    atualizarCardExistente(resultado.dados);
                } else {
                    inserirNovoCard(resultado.dados);
                }

                if (continuarCadastrando) {
                    resetarFormularioPeca();
                    modalPecaTitulo.textContent = 'Cadastrar peça';
                    setTimeout(function () { campoNome.focus(); }, 0);
                } else {
                    fecharModalPeca();
                }
            })
            .catch(function () {
                if (erroGeral) {
                    erroGeral.textContent = 'Não foi possível salvar agora. Tente de novo.';
                    erroGeral.hidden = false;
                }
            });
    });

    // ---------- ações da grade: expandir card, editar, vincular, excluir, desvincular ----------

    if (grade) {
        grade.addEventListener('click', function (evento) {
            var badge = evento.target.closest('[data-badge-vinculo]');
            if (badge) {
                var cardBadge = badge.closest('.gaveta-peca-card');
                var lista = cardBadge ? cardBadge.querySelector('[data-lista-produtos-vinculados]') : null;
                if (lista) lista.hidden = !lista.hidden;
                return;
            }

            var botaoEditar = evento.target.closest('[data-abrir-modal-peca]');
            if (botaoEditar) {
                abrirModalPecaEdicao({
                    id: botaoEditar.getAttribute('data-peca-id'),
                    nome: botaoEditar.getAttribute('data-peca-nome'),
                    nomeTecnico: botaoEditar.getAttribute('data-peca-nome-tecnico'),
                    codigoFabricante: botaoEditar.getAttribute('data-peca-codigo-fabricante'),
                    marcaId: botaoEditar.getAttribute('data-peca-marca-id'),
                    marcaNome: botaoEditar.getAttribute('data-peca-marca-nome'),
                    imagemUrl: botaoEditar.getAttribute('data-peca-imagem-url'),
                });
                return;
            }

            var botaoVincular = evento.target.closest('[data-abrir-modal-vinculo]');
            if (botaoVincular) {
                var pecaId = botaoVincular.getAttribute('data-peca-id');
                var pecaNome = botaoVincular.getAttribute('data-peca-nome');

                ModalVinculo.abrirComPeca(pecaId, pecaNome, function (dados) {
                    var card = grade.querySelector('.gaveta-peca-card[data-peca-id="' + dados.peca_id + '"]');
                    if (!card) return;

                    var lista = garantirListaVinculada(card);
                    lista.appendChild(construirLinhaProduto(dados.id, dados.produto_nome, dados.peca_nome));
                    atualizarContagemBadge(card);
                    aplicarFiltros();
                });
            }
        });

        grade.addEventListener('submit', function (evento) {
            var formExcluir = evento.target.closest('.gaveta-form-excluir-peca');
            if (formExcluir) {
                evento.preventDefault();

                var card = formExcluir.closest('.gaveta-peca-card');
                var botao = formExcluir.querySelector('button[type=submit]');
                var nome = botao ? botao.getAttribute('data-peca-nome') : 'esta peça';
                var qtd = botao ? parseInt(botao.getAttribute('data-qtd-produtos') || '0', 10) : 0;

                var mensagem = 'Excluir a peça "' + nome + '"?';
                if (qtd > 0) {
                    mensagem += ' Ela está vinculada a ' + qtd + ' produto' + (qtd > 1 ? 's' : '') + ' — o vínculo também será removido.';
                }
                if (!window.confirm(mensagem)) return;

                fetch(formExcluir.action, {
                    method: 'POST',
                    headers: {'X-CSRFToken': obterCsrfToken(), 'X-Requested-With': 'XMLHttpRequest'},
                })
                    .then(function (resposta) { return resposta.json(); })
                    .then(function () {
                        if (card) card.remove();

                        if (grade.children.length === 0) {
                            // Última peça excluída — volta pro estado vazio,
                            // que tem HTML diferente da grade. Mesmo raciocínio
                            // do cadastro da primeira peça: recarregar aqui é
                            // mais simples e seguro do que remontar via JS.
                            window.location.reload();
                            return;
                        }

                        aplicarFiltros();
                    });
                return;
            }

            var formDesvincular = evento.target.closest('.gaveta-form-desvincular');
            if (formDesvincular) {
                evento.preventDefault();

                var botaoDesvincular = formDesvincular.querySelector('button[type=submit]');
                var nomeProduto = botaoDesvincular ? botaoDesvincular.getAttribute('data-nome-produto') : 'este produto';
                var nomePeca = botaoDesvincular ? botaoDesvincular.getAttribute('data-nome-peca') : 'esta peça';

                if (!window.confirm('Desvincular "' + nomePeca + '" do produto "' + nomeProduto + '"?')) return;

                fetch(formDesvincular.action, {
                    method: 'POST',
                    headers: {'X-CSRFToken': obterCsrfToken(), 'X-Requested-With': 'XMLHttpRequest'},
                })
                    .then(function (resposta) { return resposta.json(); })
                    .then(function (dados) {
                        var card = grade.querySelector('.gaveta-peca-card[data-peca-id="' + dados.peca_id + '"]');
                        if (!card) return;

                        var linha = formDesvincular.closest('.gaveta-peca-card-produto-linha');
                        if (linha) linha.remove();

                        atualizarContagemBadge(card);
                        aplicarFiltros();
                    });
            }
        });
    }
})();