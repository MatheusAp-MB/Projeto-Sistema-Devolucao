// devolucoes/static/devolucoes/js/script_catalogo.js

// Função Objetivo: comportamentos da tela de catálogo — busca com
// autocomplete de peças já cadastradas (pra vincular a este produto
// sem duplicar), preview de imagem no formulário de peça nova, modal
// de foto em tela cheia, e confirmação antes de excluir peça de vez
// (ação que afeta outros vínculos, não só o que está na tela).

(function () {
    var campoBusca = document.getElementById('id_busca_peca');
    var listaResultados = document.getElementById('catalogo-resultados-peca');
    var painelVincular = document.getElementById('catalogo-painel-vincular');
    var vincularNome = document.getElementById('catalogo-vincular-nome');
    var vincularPecaId = document.getElementById('catalogo-vincular-peca-id');
    var botaoCadastrarNova = document.getElementById('catalogo-botao-cadastrar-nova');
    var painelNova = document.getElementById('catalogo-painel-nova');
    var campoNovaPecaNome = document.getElementById('catalogo-nova-peca-nome');

    if (!campoBusca || !listaResultados) return;

    var atrasoBusca = null;

    function esconderPaineis() {
        painelVincular.hidden = true;
        painelNova.hidden = true;
    }

    function renderizarResultados(resultados) {
        listaResultados.innerHTML = '';

        resultados.forEach(function (peca) {
            var item = document.createElement('button');
            item.type = 'button';
            item.className = 'catalogo-resultado-peca';

            var foto = document.createElement('div');
            foto.className = 'catalogo-resultado-peca-foto';
            if (peca.foto_url) {
                var img = document.createElement('img');
                img.src = peca.foto_url;
                img.alt = peca.nome;
                foto.appendChild(img);
            } else {
                foto.textContent = '—';
            }

            var info = document.createElement('div');
            info.className = 'catalogo-resultado-peca-info';
            var nome = document.createElement('span');
            nome.className = 'catalogo-resultado-peca-nome';
            nome.textContent = peca.nome;
            info.appendChild(nome);

            if (peca.usada_em.length) {
                var uso = document.createElement('span');
                uso.className = 'catalogo-resultado-peca-uso';
                uso.textContent = 'já usada em: ' + peca.usada_em.join(', ');
                info.appendChild(uso);
            }

            item.appendChild(foto);
            item.appendChild(info);

            item.addEventListener('click', function () {
                vincularPecaId.value = peca.id;
                vincularNome.textContent = '"' + peca.nome + '"';
                painelVincular.hidden = false;
                painelNova.hidden = true;
                listaResultados.hidden = true;
            });

            listaResultados.appendChild(item);
        });

        listaResultados.hidden = resultados.length === 0;
    }

    campoBusca.addEventListener('input', function () {
        var termo = campoBusca.value.trim();
        esconderPaineis();

        if (atrasoBusca) clearTimeout(atrasoBusca);

        if (termo.length < 2) {
            listaResultados.hidden = true;
            botaoCadastrarNova.hidden = true;
            return;
        }

        botaoCadastrarNova.hidden = false;

        atrasoBusca = setTimeout(function () {
            var url = CATALOGO_URL_BUSCAR_PECAS + '?q=' + encodeURIComponent(termo);
            fetch(url)
                .then(function (resposta) { return resposta.json(); })
                .then(function (dados) { renderizarResultados(dados.resultados); });
        }, 250);
    });

    if (botaoCadastrarNova) {
        botaoCadastrarNova.addEventListener('click', function () {
            painelNova.hidden = false;
            painelVincular.hidden = true;
            listaResultados.hidden = true;
            if (campoNovaPecaNome) campoNovaPecaNome.value = campoBusca.value.trim();
        });
    }
})();

(function () {
    var botaoPecaAvulsa = document.getElementById('catalogo-botao-peca-avulsa');
    var painelPecaAvulsa = document.getElementById('catalogo-painel-peca-avulsa');

    if (botaoPecaAvulsa && painelPecaAvulsa) {
        botaoPecaAvulsa.addEventListener('click', function () {
            painelPecaAvulsa.hidden = !painelPecaAvulsa.hidden;
        });
    }
})();

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList) return;

        if (form.classList.contains('catalogo-form-excluir-peca')) {
            var botao = form.querySelector('.catalogo-botao-excluir-peca');
            var nome = botao ? botao.getAttribute('data-peca-nome') : 'esta peça';
            var qtdProdutos = botao ? parseInt(botao.getAttribute('data-qtd-produtos'), 10) || 1 : 1;
            var aviso = qtdProdutos > 1
                ? 'Excluir "' + nome + '" de vez? Ela está vinculada a ' + qtdProdutos + ' produtos — todos eles vão perder essa peça, não só este.'
                : 'Excluir "' + nome + '" de vez?';
            if (!window.confirm(aviso)) {
                evento.preventDefault();
            }
        }
    });
})();

(function () {
    function configurarPreviewImagem(idCampo, idPreviewImagem, idPreviewCartao, idPreviewNome) {
        var campoImagem = document.getElementById(idCampo);
        var previewImagem = document.getElementById(idPreviewImagem);
        var previewCartao = document.getElementById(idPreviewCartao);
        var previewNomeArquivo = document.getElementById(idPreviewNome);

        if (!campoImagem || !previewImagem || !previewCartao || !previewNomeArquivo) return;

        campoImagem.addEventListener('change', function () {
            var arquivo = campoImagem.files && campoImagem.files[0];
            if (!arquivo) {
                previewCartao.hidden = true;
                previewImagem.src = '';
                previewNomeArquivo.textContent = '';
                return;
            }
            var leitor = new FileReader();
            leitor.onload = function (evento) {
                previewImagem.src = evento.target.result;
                previewNomeArquivo.textContent = arquivo.name;
                previewCartao.hidden = false;
            };
            leitor.readAsDataURL(arquivo);
        });
    }

    configurarPreviewImagem('id_imagem_nova_peca', 'preview_imagem_nova_peca', 'preview_imagem_nova_peca_cartao', 'preview_imagem_nova_peca_nome');
    configurarPreviewImagem('id_imagem_peca_avulsa', 'preview_imagem_peca_avulsa', 'preview_imagem_peca_avulsa_cartao', 'preview_imagem_peca_avulsa_nome');

    var modal = document.getElementById('modal-foto-catalogo');
    if (!modal) return;

    var elImagem = document.getElementById('modal-foto-catalogo-imagem');
    var elTitulo = document.getElementById('modal-foto-catalogo-titulo');
    var btnFechar = document.getElementById('modal-foto-catalogo-fechar');

    function abrirModal(url, titulo) {
        elImagem.src = url;
        elImagem.alt = titulo;
        elTitulo.textContent = titulo;
        modal.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    function fecharModal() {
        modal.hidden = true;
        document.body.style.overflow = '';
    }

    document.addEventListener('click', function (evento) {
        var item = evento.target.closest('.catalogo-peca-foto--clicavel');
        if (!item) return;
        abrirModal(item.getAttribute('data-imagem-url'), item.getAttribute('data-imagem-titulo'));
    });

    btnFechar.addEventListener('click', fecharModal);

    modal.addEventListener('click', function (evento) {
        if (evento.target === modal) fecharModal();
    });

    document.addEventListener('keydown', function (evento) {
        if (!modal.hidden && evento.key === 'Escape') fecharModal();
    });
})();