// devolucoes/static/devolucoes/js/script_catalogo.js

// Função Objetivo: 2 comportamentos da tela de catálogo — preview da
// imagem escolhida ainda no formulário de "adicionar peça" (antes de
// enviar), e o modal de foto em tela cheia ao clicar num quadradinho já
// cadastrado (mesmo padrão do modal do Hub de Fotos, simplificado pra
// 1 foto só, sem carrossel).

(function () {
    var campoImagem = document.getElementById('id_imagem_nova_peca');
    var previewImagem = document.getElementById('preview_imagem_nova_peca');
    var previewCartao = document.getElementById('preview_imagem_nova_peca_cartao');
    var previewNomeArquivo = document.getElementById('preview_imagem_nova_peca_nome');

    if (campoImagem && previewImagem && previewCartao && previewNomeArquivo) {
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
                previewCartao.hidden = false;
            };
            leitor.readAsDataURL(arquivo);
            previewNomeArquivo.textContent = arquivo.name;
        });
    }

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

(function () {
    var campoFoto = document.getElementById('id_foto_editar_produto');
    var previewFoto = document.getElementById('preview_foto_editar_produto');

    if (!campoFoto || !previewFoto) return;

    campoFoto.addEventListener('change', function () {
        var arquivo = campoFoto.files && campoFoto.files[0];
        if (!arquivo) return;

        var leitor = new FileReader();
        leitor.onload = function (evento) {
            previewFoto.src = evento.target.result;
            previewFoto.hidden = false;
        };
        leitor.readAsDataURL(arquivo);
    });
})();