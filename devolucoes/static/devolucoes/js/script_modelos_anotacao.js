// devolucoes/static/devolucoes/js/script_modelos_anotacao.js

// Função Objetivo: comportamentos da tela de Modelos de anotação —
// mostrar/esconder o formulário de "+ Novo modelo", e confirmação
// antes de excluir. Excluir um modelo NÃO afeta anotações já salvas
// com aquele texto (é só um atalho pra digitar mais rápido na
// Conferência, não um vínculo de banco) — por isso o aviso de
// confirmação é mais simples que o de Marcas/Grupos.

(function () {
    var botaoNovo = document.getElementById('botao-novo-modelo-anotacao');
    var formNovo = document.getElementById('form-novo-modelo-anotacao');
    if (botaoNovo && formNovo) {
        botaoNovo.addEventListener('click', function () {
            formNovo.hidden = !formNovo.hidden;
        });
    }
})();

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList || !form.classList.contains('modelos-anotacao-form-excluir')) return;

        var botao = form.querySelector('.modelos-anotacao-botao-excluir');
        var nome = botao ? botao.getAttribute('data-nome') : 'este modelo';
        if (!window.confirm('Excluir o modelo "' + nome + '"? Anotações já salvas com esse texto não são afetadas.')) {
            evento.preventDefault();
        }
    });
})();
