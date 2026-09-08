// devolucoes/static/devolucoes/js/script_devolucoes_pendentes.js

// Função Objetivo: confirmação antes de excluir uma devolução — ação
// sem volta (apaga peças conferidas e fotos em cascata), então confirma
// antes. Mesmo padrão já usado em script_marcas_grupos.js.

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList || !form.classList.contains('dp-form-excluir')) return;

        var botao = form.querySelector('.dp-btn--perigo');
        var numeroPedido = botao ? botao.getAttribute('data-nome') : 'esta devolução';

        if (!window.confirm('Excluir a devolução do pedido ' + numeroPedido + '? Essa ação não pode ser desfeita.')) {
            evento.preventDefault();
        }
    });
})();