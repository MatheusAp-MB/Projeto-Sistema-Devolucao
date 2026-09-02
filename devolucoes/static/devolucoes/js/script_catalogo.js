// devolucoes/static/devolucoes/js/script_catalogo.js

// Função Objetivo: 2 comportamentos da tela de catálogo — preview da
// imagem escolhida ainda no formulário de "adicionar peça" (antes de
// enviar), e o modal de foto em tela cheia ao clicar num quadradinho já
// cadastrado (mesmo padrão do modal do Hub de Fotos, simplificado pra
// 1 foto só, sem carrossel).

(function () {
    var campoImagem = document.getElementById('id_imagem_nova_peca');
    var previewImagem = document.getElementById('preview_imagem_nova_peca');

    if (campoImagem && previewImagem) {
        campoImagem.addEventListener('change', function () {
            var arquivo = campoImagem.files && campoImagem.files[0];
            if (!arquivo) {
                previewImagem.style.display = 'none';
                previewImagem.src = '';
                return;
            }
            var leitor = new FileReader();
            leitor.onload = function (evento) {
                previewImagem.src = evento.target.result;
                previewImagem.style.display = 'block';
            };
            leitor.readAsDataURL(arquivo);
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