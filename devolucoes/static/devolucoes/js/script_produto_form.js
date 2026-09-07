// devolucoes/static/devolucoes/js/script_produto_form.js

// Função Objetivo: comportamentos da tela de cadastro/edição de produto.
// O seletor de Marca (busca ao vivo + cadastro rápido de Marca/Grupo
// Fornecedor) é o mesmo widget usado na tela de Peça — a lógica em si
// vive em script_marca_widget.js; aqui só entra a chamada com os ids
// específicos desta tela.

inicializarSeletorMarca({
    wrap: 'marca_seletor_wrap',
    caixa: 'id_marca_caixa',
    caixaTexto: 'marca_caixa_texto',
    campoMarcaId: 'id_marca_id',
    painel: 'marca_painel',
    busca: 'marca_busca',
    lista: 'marca_lista',
    chipGrupo: 'chip_grupo_fornecedor',
    marcaErro: 'marca_erro',
    botaoNovaMarca: 'botao_nova_marca',
    caixaNovaMarca: 'caixa_nova_marca',
    selectGrupo: 'id_grupo_fornecedor',
    caixaNovoGrupo: 'caixa_novo_grupo',
    campoNovoGrupoNome: 'id_novo_grupo_fornecedor_nome',
    marcaFeedback: 'marca_feedback',
    botaoCadastrarGrupo: 'botao_cadastrar_grupo',
    botaoCadastrarMarca: 'botao_cadastrar_marca',
    campoNovaMarcaNome: 'id_nova_marca_nome',
    form: 'form-dados-produto',
});

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

// ---------- Modal de Vínculo com o produto travado (Objetivo 7) ----------
//
// [ATENÇÃO] → Produto não muda de mecanismo (decisão do Objetivo 0): a tela
// continua com formulário clássico e redirect. Por isso, diferente da
// Gaveta de Peças (que atualiza o card na hora via JS), aqui a gente só
// recarrega a página depois de vincular — o servidor já sabe montar a
// linha completa (com marca) a partir do banco, então não faz sentido
// duplicar essa montagem em JS pra um caso que também já teria que lidar
// com o estado vazio ("Nenhuma peça vinculada ainda" → lista). O
// "Desvincular" de cada linha já segue esse mesmo padrão (form clássico,
// sem JS nenhum aqui) — isso já funcionava antes do Objetivo 7.
(function () {
    var botaoVincular = document.querySelector('[data-abrir-modal-vinculo-produto]');
    if (!botaoVincular) return;

    botaoVincular.addEventListener('click', function () {
        var produtoId = botaoVincular.getAttribute('data-produto-id');
        var produtoNome = botaoVincular.getAttribute('data-produto-nome');

        ModalVinculo.abrirComProduto(produtoId, produtoNome, function () {
            window.location.reload();
        });
    });
})();