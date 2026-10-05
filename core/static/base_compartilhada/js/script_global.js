// * [RESUMO] → Script global do sistema — menu lateral (sidebar) e
//              fechamento dos avisos globais (messages do Django, ver
//              estrutura_base_global.html).

// * [EXPLICAÇÃO] → O botão de menu (hamburguer) na toolbar faz DUAS coisas,
//                  conforme o tamanho da tela (o mesmo corte do CSS, 900px):
//
//                  - COMPUTADOR (acima de 900px): adiciona ou remove a classe
//                    'sidebar-oculta' no body e GRAVA a escolha no
//                    localStorage — sem isso, a escolha se perdia a cada
//                    recarregamento de página de verdade. A leitura desse
//                    valor já acontece antes, no <script> inline logo no
//                    início do <body> (evita flash visual). NADA mudou aqui.
//
//                  - CELULAR (até 900px): o menu é uma "gaveta" que abre por
//                    cima da tela. Liga/desliga a classe 'menu-aberto' no
//                    body. Começa sempre FECHADO e NÃO grava nada no
//                    localStorage (a escolha do computador não pode ser
//                    mexida pelo celular, e o menu aberto a cada página
//                    comeria a tela inteira). Fecha ao tocar no fundo
//                    escurecido, no X, em qualquer item do menu ou na tecla
//                    Esc.
(function () {
    var botaoMenu = document.getElementById('btn-toggle-sidebar');
    var botaoFechar = document.getElementById('btn-fechar-sidebar');
    var fundo = document.getElementById('sidebar-fundo');
    var sidebar = document.getElementById('sidebar-menu');
    var emCelular = window.matchMedia('(max-width: 900px)');

    function menuEstaAberto() {
        return document.body.classList.contains('menu-aberto');
    }

    function abrirMenu() {
        document.body.classList.add('menu-aberto');
        botaoMenu.setAttribute('aria-expanded', 'true');
        if (botaoFechar) botaoFechar.focus({ preventScroll: true });
    }

    function fecharMenu(devolverFoco) {
        document.body.classList.remove('menu-aberto');
        botaoMenu.setAttribute('aria-expanded', 'false');
        if (devolverFoco) botaoMenu.focus({ preventScroll: true });
    }

    botaoMenu.addEventListener('click', function() {
        if (emCelular.matches) {
            if (menuEstaAberto()) fecharMenu(false);
            else abrirMenu();
            return;
        }
        document.body.classList.toggle('sidebar-oculta');
        const estaOculta = document.body.classList.contains('sidebar-oculta');
        localStorage.setItem('sidebar_oculta', estaOculta);
    });

    if (fundo) fundo.addEventListener('click', function () { fecharMenu(true); });
    if (botaoFechar) botaoFechar.addEventListener('click', function () { fecharMenu(true); });

    // Tocar num item do menu fecha a gaveta ANTES de trocar de página: se a pessoa
    // voltar pelo botão "voltar" do navegador, a página não reaparece com o menu aberto.
    if (sidebar) {
        sidebar.addEventListener('click', function (evento) {
            if (evento.target.closest && evento.target.closest('a')) fecharMenu(false);
        });
    }

    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape' && menuEstaAberto()) fecharMenu(true);
    });

    // Girou o celular / esticou a janela até virar "computador": a gaveta não faz sentido lá.
    function aoMudarTamanho() {
        if (!emCelular.matches && menuEstaAberto()) fecharMenu(false);
    }
    if (emCelular.addEventListener) emCelular.addEventListener('change', aoMudarTamanho);
    else if (emCelular.addListener) emCelular.addListener(aoMudarTamanho);
})();

// * [EXPLICAÇÃO] → Avisos globais (mensagens do Django messages
//   framework, ex: "Prazo de resposta salvo.") ficavam presos na tela
//   pra sempre -- incômodo real quando a ação (ex: salvar prazo) manda
//   de volta pra MESMA tela, em vez de sair dela. Sucesso/info somem
//   sozinhos depois de alguns segundos; warning/error ficam até serem
//   fechados manualmente, porque merecem mais atenção. O X sempre
//   funciona, em qualquer tipo. Decisão de Matheus, 20/09/2026.
(function () {
    var DURACAO_TRANSICAO_MS = 300;
    var TEMPO_AUTO_DISMISS_MS = 4000;

    function fecharAviso(aviso) {
        if (!aviso || aviso.classList.contains('aviso-global--saindo')) return;
        aviso.classList.add('aviso-global--saindo');
        setTimeout(function () { aviso.remove(); }, DURACAO_TRANSICAO_MS);
    }

    document.querySelectorAll('.aviso-global').forEach(function (aviso) {
        var botaoFechar = aviso.querySelector('.aviso-global-fechar');
        if (botaoFechar) {
            botaoFechar.addEventListener('click', function () { fecharAviso(aviso); });
        }
        if (aviso.getAttribute('data-auto-dismiss') === 'true') {
            setTimeout(function () { fecharAviso(aviso); }, TEMPO_AUTO_DISMISS_MS);
        }
    });
})();