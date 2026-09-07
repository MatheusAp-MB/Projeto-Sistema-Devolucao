// devolucoes/static/devolucoes/js/script_produto_visualizar.js

// Função Objetivo: comportamento da tela "Visualizar produto" — só a
// confirmação antes de excluir o produto (o resto da tela é 100% estático,
// sem nada pra atualizar via JS: editar/vincular navegam pra outra tela e
// a lista de peças vinculadas é só leitura). Esse handler morava em
// script_produto_form.js — mudou de arquivo junto com o botão "Excluir
// produto", que virou uma ação irmã aqui em vez de ficar no rodapé do
// formulário de edição.

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList || !form.classList.contains('produto-view-form-excluir')) return;

        var botao = form.querySelector('.produto-view-acao-irma--perigo');
        var nome = botao ? botao.getAttribute('data-produto-nome') : 'este produto';
        if (!window.confirm('Excluir o produto "' + nome + '"? As peças vinculadas continuam existindo (só a ligação com este produto some).')) {
            evento.preventDefault();
        }
    });
})();