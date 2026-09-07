// devolucoes/static/devolucoes/js/script_peca_form.js

// Função Objetivo: comportamentos da tela de editar peça — preview de
// foto (mesmo padrão da tela de produto) e confirmação antes de
// excluir, avisando quantos produtos perderiam a peça.

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