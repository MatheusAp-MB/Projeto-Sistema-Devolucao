// * [RESUMO] → Script global do sistema — toggle da sidebar (ocultar/exibir).

// * [EXPLICAÇÃO] → Ao clicar no botão de menu (hamburguer) na toolbar,
//                  adiciona ou remove a classe 'sidebar-oculta' no body,
//                  e GRAVA a escolha no localStorage — sem isso, a escolha
//                  se perdia a cada recarregamento de página de verdade.
//                  A leitura desse valor já acontece antes, no <script>
//                  inline logo no início do <body> (evita flash visual).
document.getElementById('btn-toggle-sidebar').addEventListener('click', function() {
    document.body.classList.toggle('sidebar-oculta');
    const estaOculta = document.body.classList.contains('sidebar-oculta');
    localStorage.setItem('sidebar_oculta', estaOculta);
});