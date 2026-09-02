// devolucoes/static/devolucoes/js/script_produtos.js

// Função Objetivo: 2 comportamentos da tela de produtos — mostrar/esconder
// o formulário de cadastro de produto ao clicar no botão "Cadastrar
// produto", e o preview da foto escolhida no formulário antes de enviar
// (mesmo padrão usado no formulário de adicionar peça do catálogo).

(function () {
    var botaoMostrarCadastro = document.getElementById('botao-mostrar-cadastro-produto');
    var formCadastro = document.getElementById('produtos-form-cadastro');

    if (botaoMostrarCadastro && formCadastro) {
        botaoMostrarCadastro.addEventListener('click', function () {
            formCadastro.hidden = !formCadastro.hidden;
        });
    }

    var campoImagem = document.getElementById('id_foto_novo_produto');
    var previewCartao = document.getElementById('preview_foto_novo_produto_cartao');
    var previewImagem = document.getElementById('preview_foto_novo_produto');
    var previewNomeArquivo = document.getElementById('preview_foto_novo_produto_nome');

    if (campoImagem && previewCartao && previewImagem && previewNomeArquivo) {
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
})();