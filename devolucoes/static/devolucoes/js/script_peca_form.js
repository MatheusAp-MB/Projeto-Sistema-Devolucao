// devolucoes/static/devolucoes/js/script_peca_form.js

// Função Objetivo: comportamentos da tela de editar peça — seletor de
// marca (componente compartilhado, script_marca_widget.js), preview de
// foto (mesmo padrão da tela de produto) e confirmação antes de
// excluir, avisando quantos produtos perderiam a peça.

inicializarSeletorMarca({
    caixa: 'id_marca_caixa_peca',
    caixaTexto: 'marca_caixa_texto_peca',
    campoMarcaId: 'id_marca_id_peca',
    wrap: 'marca_seletor_wrap_peca',
    painel: 'marca_painel_peca',
    busca: 'marca_busca_peca',
    lista: 'marca_lista_peca',
    chipGrupo: 'chip_grupo_fornecedor_peca',
    marcaErro: 'marca_erro_peca',
    botaoNovaMarca: 'botao_nova_marca_peca',
    caixaNovaMarca: 'caixa_nova_marca_peca',
    selectGrupo: 'id_grupo_fornecedor_peca',
    caixaNovoGrupo: 'caixa_novo_grupo_peca',
    campoNovoGrupoNome: 'id_novo_grupo_fornecedor_nome_peca',
    marcaFeedback: 'marca_feedback_peca',
    botaoCadastrarGrupo: 'botao_cadastrar_grupo_peca',
    botaoCadastrarMarca: 'botao_cadastrar_marca_peca',
    campoNovaMarcaNome: 'id_nova_marca_nome_peca',
    form: 'form-dados-peca',
});

(function () {
    var campoFoto = document.getElementById('id_foto_peca');
    var previewImagem = document.getElementById('preview_foto_peca');
    var previewTexto = document.getElementById('foto_peca_texto');

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
        var nome = botao ? botao.getAttribute('data-peca-nome') : 'esta peça';
        var qtdProdutos = botao ? parseInt(botao.getAttribute('data-qtd-produtos'), 10) || 0 : 0;
        var aviso = qtdProdutos > 0
            ? 'Excluir "' + nome + '" de vez? Ela está vinculada a ' + qtdProdutos + ' produto(s) — todos eles vão perder essa peça.'
            : 'Excluir "' + nome + '" de vez?';
        if (!window.confirm(aviso)) {
            evento.preventDefault();
        }
    });
})();