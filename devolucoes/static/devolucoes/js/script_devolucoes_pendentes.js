// devolucoes/static/devolucoes/js/script_devolucoes_pendentes.js

// Função Objetivo: (1) confirmação antes de excluir uma devolução ou de
// marcar como impressa — ambas irreversíveis (excluir apaga peças/fotos
// em cascata; marcar como impressa não tem "desfazer" na tela, decisão
// de Matheus 18/09/2026) — e (2) toda a interação das abas do fluxo
// (Aguardando Conferência/Conferidos/Mediações Abertas/Mediações
// Encerradas/Impressos): trocar de aba, filtrar por destino (Troca/
// Usado) dentro de Conferidos/Mediações Abertas/Mediações Encerradas/
// Impressos, filtrar por reembolso dentro de Mediações Encerradas/
// Impressos (os 2 filtros combinam entre si, cada um no seu próprio
// grupo .dp-filtro-secundario[data-tipo-filtro]), e a busca global por
// cliente/pedido/produto que atravessa as 5 abas sozinha. Tudo
// client-side porque o Django já manda as 5 listas prontas pro
// template — não existe requisição nova nenhuma aqui, só mostrar/
// esconder o que já veio.
//
// 05/10/2026 (pedido de Matheus — "organização e filtros" da listagem):
// (3) ordenar cada aba ("Ordenar por"), (4) filtros novos na barra
// (Plataforma, Marca, Período, Reclamação dentro/fora dos 7 dias,
// com anotação/evidência e, só em Mediações Abertas, Prazo de resposta e
// Mensagem nova), (5) busca ampliada (agora também NF, código de barras,
// código do fabricante e marca; ignora acento; cada palavra digitada
// precisa aparecer em algum lugar) com o aviso "Achou em:" na linha, e
// (6) "padrão salvo" por aba — ordem + filtros (incluindo os chips de
// destino/reembolso que já existiam) guardados no banco da empresa ativa
// (PreferenciaTela, via POST em salvar_padrao_tela/restaurar_padrao_tela).
// Continua tudo client-side: ordenar = reordenar as linhas que já estão na
// página; os dados de cada linha chegam num atributo data-dp (JSON) montado
// em views._dados_da_linha_para_a_tela. Enquanto há texto na busca, os
// filtros da barra nova ficam em pausa (Destino/Reembolso continuam
// valendo) e o número da aba mostra quantos acharam.
// (7) o botão "Ver na lista" da tela Análise abre esta tela com
// ?aba=...&busca=... (fim do arquivo): já cai na aba certa, com o pedido
// na busca.

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList) return;

        if (form.classList.contains('dp-form-excluir')) {
            var botaoExcluir = form.querySelector('.dp-btn--perigo');
            var numeroPedidoExcluir = botaoExcluir ? botaoExcluir.getAttribute('data-nome') : 'esta devolução';
            if (!window.confirm('Excluir a devolução do pedido ' + numeroPedidoExcluir + '? Essa ação não pode ser desfeita.')) {
                evento.preventDefault();
            }
            return;
        }

        if (form.classList.contains('dp-form-marcar-impressa')) {
            var botaoImpressa = form.querySelector('.dp-btn--confirmar');
            var numeroPedidoImpressa = botaoImpressa ? botaoImpressa.getAttribute('data-nome') : 'esta devolução';
            if (!window.confirm('Marcar a devolução do pedido ' + numeroPedidoImpressa + ' como impressa? Não tem como desmarcar depois.')) {
                evento.preventDefault();
            }
        }
    });
})();

(function () {
    var abas = Array.prototype.slice.call(document.querySelectorAll('.dp-aba-btn'));
    if (!abas.length) return;

    var paineis = document.querySelectorAll('.dp-tab-panel');
    var campoBusca = document.getElementById('dp-busca');
    var nota = document.getElementById('dp-nota-outras-abas');

    // ===================================================================
    // Utilidades pequenas
    // ===================================================================

    // * [EXPLICAÇÃO] → MESMA regra de _sem_acentos_minusculo() do views.py:
    //   tira acento e põe minúsculo. É por isso que "joao" acha "João" —
    //   o texto que vem do Django e o que a pessoa digita passam pela
    //   mesma limpeza.
    function norm(texto) {
        return String(texto == null ? '' : texto).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    }

    function esc(texto) {
        return String(texto == null ? '' : texto).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function clonar(objeto) { return JSON.parse(JSON.stringify(objeto)); }
    function tem(lista, valor) { return lista.indexOf(valor) !== -1; }
    function plural(n) { return n === 1 ? '' : 's'; }

    function lerJson(id) {
        var el = document.getElementById(id);
        if (!el) return null;
        try { return JSON.parse(el.textContent); } catch (e) { return null; }
    }

    // ===================================================================
    // Vocabulário (nomes que a Ana lê na tela)
    // ===================================================================

    var CONFIG = lerJson('dp-config') || {};
    var SALVOS = lerJson('dp-padroes-salvos') || {};
    var NOME_EMPRESA = CONFIG.empresa || 'esta empresa';

    var ROTULO_ORDEM = {
        'cadastro:desc': 'Cadastro mais recente',
        'cadastro:asc': 'Cadastro mais antigo',
        'cliente:asc': 'Cliente (A–Z)',
        'produto:asc': 'Produto (A–Z)',
        'plat:asc': 'Plataforma (A–Z)',
        'prazo:asc': 'Prazo de resposta mais próximo',
        'abertura:asc': 'Mediação aberta há mais tempo',
        'msg:desc': 'Mensagem nova primeiro',
        'fim:desc': 'Encerrada mais recentemente',
        'valor:desc': 'Maior valor reembolsado',
        'impresso:desc': 'Impressa mais recentemente'
    };

    // * [EXPLICAÇÃO] → o 1º item de cada menu é sempre a ordem que o sistema
    //   já tinha antes (cadastro mais recente) — a "ordem de fábrica".
    var MENU_ORDEM = {
        aguardando_conferencia: ['cadastro:desc', 'cadastro:asc', 'cliente:asc', 'produto:asc', 'plat:asc'],
        conferido: ['cadastro:desc', 'cadastro:asc', 'cliente:asc', 'produto:asc', 'plat:asc'],
        mediacao_aberta: ['cadastro:desc', 'prazo:asc', 'abertura:asc', 'msg:desc', 'cliente:asc', 'produto:asc', 'plat:asc'],
        mediacao_encerrada: ['cadastro:desc', 'fim:desc', 'valor:desc', 'cliente:asc', 'produto:asc', 'plat:asc'],
        impresso: ['cadastro:desc', 'impresso:desc', 'cliente:asc', 'produto:asc', 'plat:asc']
    };

    var ROTULO_PRAZO = {
        vencido: 'Vencido',
        hoje: 'Vence hoje',
        proximo: 'Vence em até 2 dias',
        ok: 'Em dia (3 dias ou mais)',
        sem: 'Sem prazo registrado'
    };

    var OPCOES_PERIODO = [
        ['', 'Qualquer data'],
        ['7', 'Últimos 7 dias'],
        ['30', 'Últimos 30 dias'],
        ['90', 'Últimos 90 dias']
    ];

    // * [EXPLICAÇÃO] → "Período" olha a data que faz sentido pra cada aba:
    //   cadastro nas 2 primeiras, abertura da mediação em Mediações
    //   Abertas, encerramento em Mediações Encerradas e impressão em
    //   Impressos (campos do pacote data-dp montado no views.py).
    var DATA_REFERENCIA = {
        aguardando_conferencia: { campo: 'cadd', rotulo: 'cadastro' },
        conferido: { campo: 'cadd', rotulo: 'cadastro' },
        mediacao_aberta: { campo: 'ab', rotulo: 'abertura da mediação' },
        mediacao_encerrada: { campo: 'fim', rotulo: 'encerramento da mediação' },
        impresso: { campo: 'impd', rotulo: 'impressão do relatório' }
    };

    var ABAS_COM_DESTINO = ['conferido', 'mediacao_aberta', 'mediacao_encerrada', 'impresso'];
    var ABAS_COM_REEMBOLSO = ['mediacao_encerrada', 'impresso'];
    var CAMPOS_EXTRAS_BUSCA = ['nf', 'cod', 'ean', 'marca'];

    // ===================================================================
    // Dados de cada linha (vêm prontos do Django, atributo data-dp)
    // ===================================================================

    var painelDaAba = {};
    var itensDaAba = {};

    abas.forEach(function (botaoAba) {
        var nomeAba = botaoAba.getAttribute('data-aba');
        var painel = document.querySelector('.dp-tab-panel[data-painel="' + nomeAba + '"]');
        painelDaAba[nomeAba] = painel;

        itensDaAba[nomeAba] = Array.prototype.slice.call(painel.querySelectorAll('.dp-item')).map(function (el, indice) {
            var d = {};
            try { d = JSON.parse(el.getAttribute('data-dp') || '{}'); } catch (e) { d = {}; }
            var elProduto = el.querySelector('.dp-tabela-produto-nome');
            var elCliente = el.querySelector('.dp-tabela-cliente-nome');
            var elPedido = el.querySelector('.dp-pedido-num');
            return {
                el: el,
                d: d,
                i: indice,
                // texto já sem acento/minúsculo, pronto pra comparar com o que foi digitado
                n: {
                    cli: d.cli || norm(el.getAttribute('data-busca')),
                    ped: d.ped || '',
                    prod: d.prod || '',
                    nf: norm(d.nf),
                    cod: norm(d.cod),
                    ean: norm(d.ean),
                    marca: d.marca || ''
                },
                elProduto: elProduto, txtProduto: elProduto ? elProduto.textContent : '',
                elCliente: elCliente, txtCliente: elCliente ? elCliente.textContent : '',
                elPedido: elPedido, txtPedido: elPedido ? elPedido.textContent : '',
                chaveDestaque: '',
                elAchou: null,
                chaveAchou: '',
                visivel: true
            };
        });
    });

    // ===================================================================
    // Estado de cada aba: ordem + filtros (+ padrão salvo)
    // ===================================================================

    function fabricaFiltros() {
        return { destino: 'todos', reembolso: 'todos', plat: [], marca: [], per: '', rec7: '', anot: '', prazo: [], msg: false };
    }

    function fabrica() {
        return { o: 'cadastro:desc', f: fabricaFiltros() };
    }

    function listaDeTextos(valor, permitidos) {
        if (!Array.isArray(valor)) return [];
        return valor.filter(function (x) {
            return typeof x === 'string' && (!permitidos || tem(permitidos, x));
        });
    }

    // * [EXPLICAÇÃO] → o padrão salvo vem do banco como "o que tinha na
    //   cabeça da tela no dia"; antes de usar, confere item por item. Se
    //   uma opção sumiu ou o dado veio estranho, aquele item volta ao
    //   normal em vez de quebrar a tela.
    function normalizar(configuracao, aba) {
        var v = fabrica();
        if (!configuracao || typeof configuracao !== 'object') return v;
        if (typeof configuracao.o === 'string' && tem(MENU_ORDEM[aba], configuracao.o)) v.o = configuracao.o;
        var f = configuracao.f || {};
        if (tem(ABAS_COM_DESTINO, aba) && tem(['troca', 'usado', 'todos'], f.destino)) v.f.destino = f.destino;
        if (tem(ABAS_COM_REEMBOLSO, aba) && tem(['todos', 'sim', 'nao'], f.reembolso)) v.f.reembolso = f.reembolso;
        v.f.plat = listaDeTextos(f.plat);
        v.f.marca = listaDeTextos(f.marca);
        if (typeof f.per === 'string' && OPCOES_PERIODO.some(function (p) { return p[0] === f.per; })) v.f.per = f.per;
        if (tem(['', 'dentro', 'fora'], f.rec7)) v.f.rec7 = f.rec7;
        if (tem(['', 'nota', 'evid'], f.anot)) v.f.anot = f.anot;
        if (aba === 'mediacao_aberta') {
            v.f.prazo = listaDeTextos(f.prazo, Object.keys(ROTULO_PRAZO));
            v.f.msg = f.msg === true;
        }
        return v;
    }

    var padroes = {};
    var V = {};
    abas.forEach(function (botaoAba) {
        var nomeAba = botaoAba.getAttribute('data-aba');
        padroes[nomeAba] = SALVOS[nomeAba] ? normalizar(SALVOS[nomeAba], nomeAba) : null;
        V[nomeAba] = clonar(padroes[nomeAba] || fabrica());
    });

    function baseDe(aba) { return padroes[aba] || fabrica(); }
    function temSalvo(aba) { return !!padroes[aba]; }

    function assinatura(v) {
        var c = clonar(v);
        ['plat', 'marca', 'prazo'].forEach(function (k) { c.f[k] = c.f[k].slice().sort(); });
        return JSON.stringify(c);
    }

    function mudou(aba) { return assinatura(V[aba]) !== assinatura(baseDe(aba)); }

    function nomeDaAbaAtual() {
        return document.querySelector('.dp-aba-btn--ativa').getAttribute('data-aba');
    }

    // ===================================================================
    // Regras: busca, chips que já existiam, filtros novos, ordem
    // ===================================================================

    function tokensDaBusca() {
        return campoBusca ? norm(campoBusca.value).split(/\s+/).filter(Boolean) : [];
    }

    // * [EXPLICAÇÃO] → cada palavra digitada precisa aparecer em algum
    //   lugar da devolução. Primeiro olha onde a busca sempre olhou
    //   (cliente, pedido, produto); se não achar ali, olha nos campos
    //   novos (NF, código do fabricante, código de barras, marca) e
    //   devolve em quais achou — é o aviso "Achou em:" da linha.
    function buscar(it, tokens) {
        if (!tokens.length) return { ok: true, ach: [] };
        var n = it.n;
        var ach = [];
        for (var t = 0; t < tokens.length; t++) {
            var token = tokens[t];
            if (n.cli.indexOf(token) !== -1 || n.ped.indexOf(token) !== -1 || n.prod.indexOf(token) !== -1) continue;
            var achou = null;
            for (var e = 0; e < CAMPOS_EXTRAS_BUSCA.length; e++) {
                if (n[CAMPOS_EXTRAS_BUSCA[e]].indexOf(token) !== -1) { achou = CAMPOS_EXTRAS_BUSCA[e]; break; }
            }
            if (!achou) return { ok: false, ach: [] };
            if (!tem(ach, achou)) ach.push(achou);
        }
        return { ok: true, ach: ach };
    }

    // chips "Filtrar por destino" e "Filtrar por reembolso" (já existiam)
    function bateChips(it, aba, f) {
        if (tem(ABAS_COM_DESTINO, aba) && f.destino !== 'todos' && it.el.getAttribute('data-destino') !== f.destino) return false;
        if (tem(ABAS_COM_REEMBOLSO, aba) && f.reembolso !== 'todos' && it.el.getAttribute('data-reembolso') !== f.reembolso) return false;
        return true;
    }

    // filtros da barra nova
    function bateNovos(it, aba, f) {
        var d = it.d;
        if (f.plat.length && !tem(f.plat, d.pn)) return false;
        if (f.marca.length && !tem(f.marca, d.mn)) return false;
        if (f.per) {
            var ref = d[DATA_REFERENCIA[aba].campo];
            if (ref == null || (CONFIG.hoje - ref) > Number(f.per)) return false;
        }
        if (f.rec7 && d.rec7 !== f.rec7) return false;
        if (f.anot === 'nota' && !d.nota) return false;
        if (f.anot === 'evid' && !d.evid) return false;
        if (aba === 'mediacao_aberta') {
            if (f.prazo.length && !tem(f.prazo, d.pst || 'sem')) return false;
            if (f.msg && !d.msg) return false;
        }
        return true;
    }

    function descreverFiltros(f, aba) {
        var desc = [];
        if (tem(ABAS_COM_DESTINO, aba) && f.destino !== 'todos') desc.push('Destino: ' + (f.destino === 'troca' ? 'Troca' : 'Usado'));
        if (tem(ABAS_COM_REEMBOLSO, aba) && f.reembolso !== 'todos') desc.push('Reembolso: ' + (f.reembolso === 'sim' ? 'reembolsados' : 'não reembolsados'));
        if (f.plat.length) desc.push('Plataforma: ' + f.plat.join(', '));
        if (f.marca.length) desc.push('Marca: ' + f.marca.join(', '));
        if (f.per) desc.push('Período: ' + OPCOES_PERIODO.filter(function (p) { return p[0] === f.per; })[0][1].toLowerCase());
        if (f.rec7) desc.push('Reclamação ' + (f.rec7 === 'dentro' ? 'dentro' : 'fora') + ' dos 7 dias');
        if (f.anot) desc.push(f.anot === 'nota' ? 'com anotação' : 'com evidência');
        if (aba === 'mediacao_aberta') {
            if (f.prazo.length) desc.push('Prazo: ' + f.prazo.map(function (p) { return ROTULO_PRAZO[p].toLowerCase(); }).join(', '));
            if (f.msg) desc.push('só com mensagem nova');
        }
        return desc;
    }

    function novosAtivos(f, aba) {
        var n = 0;
        if (f.plat.length) n++;
        if (f.marca.length) n++;
        if (f.per) n++;
        if (f.rec7) n++;
        if (f.anot) n++;
        if (aba === 'mediacao_aberta') {
            if (f.prazo.length) n++;
            if (f.msg) n++;
        }
        return n;
    }

    function valorDeOrdem(d, chave) {
        switch (chave) {
            case 'cadastro': return d.cad;
            case 'cliente': return d.cli;
            case 'produto': return d.prod;
            case 'plat': return d.plat;
            case 'prazo': return d.prz;
            case 'abertura': return d.ab;
            case 'msg': return d.msg;
            case 'fim': return d.fim;
            case 'valor': return d.val;
            case 'impresso': return d.imp;
        }
        return null;
    }

    // * [EXPLICAÇÃO] → quem não tem o dado (ex.: sem prazo) vai sempre pro
    //   fim da lista, qualquer que seja o sentido da ordem; empate cai na
    //   ordem original do Django (cadastro mais recente primeiro) — por
    //   isso a lista nunca "embaralha" entre uma ordenação e outra.
    function comparadorDeOrdem(ordem) {
        var partes = ordem.split(':');
        var chave = partes[0];
        var sentido = partes[1] === 'desc' ? -1 : 1;
        return function (a, b) {
            var x = valorDeOrdem(a.d, chave);
            var y = valorDeOrdem(b.d, chave);
            var xVazio = x == null;
            var yVazio = y == null;
            if (xVazio && yVazio) return a.i - b.i;
            if (xVazio) return 1;
            if (yVazio) return -1;
            if (x < y) return -1 * sentido;
            if (x > y) return 1 * sentido;
            return a.i - b.i;
        };
    }

    // ===================================================================
    // Destaques na linha: palavras achadas e "Achou em:"
    // ===================================================================

    function destacar(texto, tokens) {
        var chars = Array.from(texto);
        var normais = chars.map(function (c) { return norm(c); });
        // se a limpeza muda o nº de letras (casos raros), não arrisca marcar errado
        if (normais.some(function (x) { return x.length !== 1; })) return esc(texto);
        var junto = normais.join('');
        var marcado = new Array(chars.length).fill(false);
        tokens.forEach(function (token) {
            var pos = junto.indexOf(token);
            while (pos !== -1) {
                for (var j = pos; j < pos + token.length; j++) marcado[j] = true;
                pos = junto.indexOf(token, pos + token.length);
            }
        });
        var saida = '';
        var ligado = false;
        chars.forEach(function (c, i) {
            if (marcado[i] && !ligado) { saida += '<span class="dp-destaque">'; ligado = true; }
            if (!marcado[i] && ligado) { saida += '</span>'; ligado = false; }
            saida += esc(c);
        });
        return saida + (ligado ? '</span>' : '');
    }

    function aplicarDestaquesNaLinha(it, tokens) {
        var chave = tokens.join(' ');
        if (it.chaveDestaque === chave) return;
        it.chaveDestaque = chave;
        [['elProduto', 'txtProduto'], ['elCliente', 'txtCliente'], ['elPedido', 'txtPedido']].forEach(function (par) {
            var el = it[par[0]];
            if (!el) return;
            if (chave) el.innerHTML = destacar(it[par[1]], tokens);
            else el.textContent = it[par[1]];
        });
    }

    function aplicarAchouNaLinha(it, ach, tokens) {
        var chave = ach.join(',') + '|' + tokens.join(' ');
        if (it.chaveAchou === chave) return;
        it.chaveAchou = chave;
        if (!ach.length) {
            if (it.elAchou) {
                it.elAchou.innerHTML = '';
                it.elAchou.style.display = 'none';
            }
            return;
        }
        if (!it.elAchou) {
            var celulaProduto = it.el.querySelector('.dp-tabela-produto');
            if (!celulaProduto) return;
            it.elAchou = document.createElement('p');
            it.elAchou.className = 'dp-achou';
            celulaProduto.appendChild(it.elAchou);
        }
        var rotulos = {
            nf: 'NF ' + (it.d.nf || ''),
            cod: 'código do fabricante ' + (it.d.cod || ''),
            ean: 'código de barras ' + (it.d.ean || ''),
            marca: 'marca ' + (it.d.mn || '')
        };
        it.elAchou.innerHTML = '<i class="fas fa-magnifying-glass"></i> Achou em: ' +
            ach.map(function (k) { return destacar(rotulos[k], tokens); }).join(' · ');
        it.elAchou.style.display = '';
    }

    // ===================================================================
    // Aplicar na tela: aba ativa (mostrar/esconder, reordenar, destaques)
    // ===================================================================

    var ordemAplicada = {};
    abas.forEach(function (botaoAba) { ordemAplicada[botaoAba.getAttribute('data-aba')] = 'cadastro:desc'; });

    function mostrarPainel(nomeAba) {
        abas.forEach(function (a) { a.classList.toggle('dp-aba-btn--ativa', a.getAttribute('data-aba') === nomeAba); });
        paineis.forEach(function (p) { p.classList.toggle('dp-tab-panel--ativa', p.getAttribute('data-painel') === nomeAba); });
        trazerAbaParaVista(nomeAba);
        lembrarAba(nomeAba);
    }

    // * [EXPLICAÇÃO] → pedido de Matheus (05/10/2026): estando em "Impressos" (ou qualquer
    //   outra aba), atualizar a página (F5) voltava pra "Aguardando Conferência". Agora a
    //   aba ativa fica guardada no navegador (sessionStorage: vale só pra essa guia do
    //   navegador, some quando ela é fechada; uma chave por empresa) e é restaurada
    //   SÓ quando a página é recarregada ou quando se volta/avança pelo histórico.
    //   Abrir a tela pelo menu, por um link ou depois de salvar/excluir/imprimir
    //   continua abrindo em "Aguardando Conferência", como sempre foi — de propósito:
    //   quem acabou de cadastrar uma devolução precisa ver ela na 1ª aba.
    var CHAVE_ABA = 'dp-aba-ativa:' + NOME_EMPRESA;

    function lembrarAba(nomeAba) {
        try { window.sessionStorage.setItem(CHAVE_ABA, nomeAba); } catch (e) { /* sem armazenamento: segue sem lembrar */ }
    }

    function tipoDaNavegacao() {
        try {
            var entrada = window.performance.getEntriesByType('navigation')[0];
            if (entrada && entrada.type) return entrada.type; // 'navigate' | 'reload' | 'back_forward' | 'prerender'
        } catch (e) { /* tenta o jeito antigo abaixo */ }
        try {
            var antigo = window.performance.navigation && window.performance.navigation.type;
            if (antigo === 1) return 'reload';
            if (antigo === 2) return 'back_forward';
        } catch (e) { /* desconhecido: trata como navegação normal */ }
        return 'navigate';
    }

    function restaurarAbaAoRecarregar() {
        var tipo = tipoDaNavegacao();
        if (tipo !== 'reload' && tipo !== 'back_forward') return;
        var salva = null;
        try { salva = window.sessionStorage.getItem(CHAVE_ABA); } catch (e) { return; }
        if (salva && Object.prototype.hasOwnProperty.call(painelDaAba, salva)) mostrarPainel(salva);
    }

    // * [EXPLICAÇÃO] → pedido de Matheus (05/10/2026): abrir uma devolução (Visualizar) e
    //   apertar "Voltar" tem que devolver a lista EXATAMENTE como estava — mesma aba,
    //   mesmos filtros, mesma ordem, mesma busca e na mesma posição da tela, pra pessoa
    //   não ter que rolar de novo procurando a devolução. Como funciona:
    //   1) ao sair da lista (clicar em Visualizar, ou a página fechar/trocar) a tela guarda
    //      uma "foto" do estado: no sessionStorage (uma chave por empresa) e na própria
    //      entrada do histórico (history.state — cada entrada do histórico fica com a
    //      sua foto);
    //   2) o botão "Voltar" da tela Visualizar abre a lista com ?voltar=<id da devolução>.
    //      Se a foto guardada é de quando se saiu justamente por essa devolução, ela é
    //      restaurada. Qualquer outra abertura (menu, salvar, excluir, imprimir) continua
    //      em "Aguardando Conferência", como sempre foi;
    //   3) o voltar do navegador/celular (back_forward) restaura a foto daquela entrada
    //      do histórico. Quando o navegador já guardou a página inteira (o normal), ela
    //      volta sozinha como estava e nada disso é preciso.
    //   A posição é guardada como "a linha da devolução clicada estava a X px do topo da
    //   tela": assim, mesmo que a lista tenha mudado um pouco (um aviso no topo que não
    //   aparece mais, uma devolução que saiu de cima), a devolução volta pro mesmo lugar
    //   da tela. Sem a linha (ou se ela sumiu da aba), usa a posição absoluta da rolagem.
    var CHAVE_ESTADO = 'dp-estado:' + NOME_EMPRESA;
    var cliqueNaLista = null; // { id, topo } da devolução aberta por último, enquanto a página não sai

    function idDoLinkVisualizar(link) {
        var achou = (link.getAttribute('href') || '').match(/\/devolucoes\/(\d+)\/visualizar\/?/);
        return achou ? achou[1] : null;
    }

    function montarEstado() {
        var porAba = {};
        abas.forEach(function (botaoAba) {
            var nomeAba = botaoAba.getAttribute('data-aba');
            porAba[nomeAba] = clonar(V[nomeAba]);
        });
        return {
            v: 1,
            aba: nomeDaAbaAtual(),
            busca: campoBusca ? campoBusca.value : '',
            abas: porAba,
            y: Math.round(window.pageYOffset || 0),
            id: cliqueNaLista ? cliqueNaLista.id : null,
            topo: cliqueNaLista ? cliqueNaLista.topo : null
        };
    }

    function guardarEstado() {
        var estado = montarEstado();
        try { window.sessionStorage.setItem(CHAVE_ESTADO, JSON.stringify(estado)); } catch (e) { /* sem armazenamento: segue sem guardar */ }
        try {
            var atual = window.history.state;
            var novo = (atual && typeof atual === 'object') ? Object.assign({}, atual) : {};
            novo.dpEstado = estado;
            window.history.replaceState(novo, '');
        } catch (e) { /* sem histórico: segue sem guardar */ }
    }

    function estadoValido(estado) {
        return !!estado && typeof estado === 'object' && estado.v === 1 && !!estado.abas && typeof estado.abas === 'object';
    }

    // devolve a "foto" a restaurar nesta abertura da tela, ou null (abertura normal)
    function estadoParaRestaurar(tipo) {
        // tira ?voltar=... do endereço (lê antes, limpa sempre) — atualizar a página não repete nada
        var idVoltar = null;
        try {
            var parametros = new URLSearchParams(window.location.search);
            idVoltar = parametros.get('voltar');
            if (parametros.has('voltar')) {
                parametros.delete('voltar');
                var resto = parametros.toString();
                window.history.replaceState(window.history.state, '', window.location.pathname + (resto ? '?' + resto : '') + window.location.hash);
            }
        } catch (e) { /* sem URLSearchParams/histórico: segue sem */ }

        if (tipo === 'back_forward') {
            var doHistorico = null;
            try { doHistorico = window.history.state && window.history.state.dpEstado; } catch (e) { /* ignora */ }
            return estadoValido(doHistorico) ? doHistorico : null;
        }
        if (!idVoltar || !/^\d+$/.test(idVoltar)) return null;
        try {
            var salvo = JSON.parse(window.sessionStorage.getItem(CHAVE_ESTADO) || 'null');
            return (estadoValido(salvo) && String(salvo.id) === idVoltar) ? salvo : null;
        } catch (e) { return null; }
    }

    // confere cada pedaço da foto antes de usar (mesmo cuidado do padrão salvo)
    function aplicarEstado(estado) {
        abas.forEach(function (botaoAba) {
            var nomeAba = botaoAba.getAttribute('data-aba');
            if (estado.abas[nomeAba]) V[nomeAba] = normalizar(estado.abas[nomeAba], nomeAba);
            sincronizarChips(nomeAba);
        });
        if (campoBusca && typeof estado.busca === 'string') campoBusca.value = estado.busca.slice(0, 200);
        if (typeof estado.aba === 'string' && Object.prototype.hasOwnProperty.call(painelDaAba, estado.aba)) mostrarPainel(estado.aba);
    }

    function posicionarNaFoto(estado) {
        var alvoY = typeof estado.y === 'number' ? estado.y : 0;
        if (estado.id && /^\d+$/.test(String(estado.id)) && typeof estado.topo === 'number') {
            var painel = painelDaAba[nomeDaAbaAtual()];
            var link = painel && painel.querySelector('a[href*="/' + estado.id + '/visualizar/"]');
            var linha = link && link.closest('.dp-item');
            if (linha && linha.getClientRects().length) {
                alvoY = (window.pageYOffset || 0) + linha.getBoundingClientRect().top - estado.topo;
            }
        }
        window.scrollTo({ top: Math.max(0, alvoY), left: 0, behavior: 'instant' });
    }

    // * [EXPLICAÇÃO] → o tamanho final das linhas só fica certo quando as fontes e as
    //   imagens terminam de carregar; por isso a posição é refeita no "load" e quando as
    //   fontes ficam prontas — mas só enquanto a pessoa ainda não mexeu na tela.
    function restaurarRolagem(estado, retomarRolagemDoNavegador) {
        var mexeu = false;
        var marcar = function () { mexeu = true; };
        ['wheel', 'touchstart', 'mousedown', 'keydown'].forEach(function (nomeEvento) {
            window.addEventListener(nomeEvento, marcar, { passive: true, once: true });
        });
        var aplicar = function () { if (!mexeu) posicionarNaFoto(estado); };
        var devolverAoNavegador = function () {
            if (!retomarRolagemDoNavegador) return;
            window.setTimeout(function () {
                try { window.history.scrollRestoration = 'auto'; } catch (e) { /* ignora */ }
            }, 400);
        };
        aplicar();
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(aplicar);
        if (document.readyState === 'complete') {
            devolverAoNavegador();
        } else {
            window.addEventListener('load', function () { aplicar(); devolverAoNavegador(); });
        }
    }

    document.addEventListener('click', function (e) {
        if (e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || !e.target.closest) return;
        var link = e.target.closest('a[href*="/visualizar/"]');
        var linha = link && link.closest('.dp-item');
        if (!linha) return;
        cliqueNaLista = { id: idDoLinkVisualizar(link), topo: Math.round(linha.getBoundingClientRect().top) };
        guardarEstado();
    }, true);

    window.addEventListener('pagehide', guardarEstado);
    window.addEventListener('pageshow', function (e) { if (e.persisted) cliqueNaLista = null; });

    // * [EXPLICAÇÃO] → no celular as abas viram uma fila que desliza pro lado (CSS).
    //   Quando a aba ativa muda (toque, busca que pula de aba, "Ver na lista"
    //   da Análise), a fila rola até ela ficar no meio. No computador as abas
    //   quebram de linha e não rolam (scrollWidth = clientWidth), então aqui
    //   não acontece nada.
    function trazerAbaParaVista(nomeAba) {
        var ativa = abas.filter(function (a) { return a.getAttribute('data-aba') === nomeAba; })[0];
        var fila = ativa && ativa.parentNode;
        if (!fila || fila.scrollWidth <= fila.clientWidth + 1) return;
        var alvo = ativa.offsetLeft - (fila.clientWidth - ativa.offsetWidth) / 2;
        fila.scrollLeft = Math.max(0, alvo);
    }

    function labelDaAba(aba) {
        return aba.textContent.trim().replace(/\d+$/, '').trim();
    }

    // devolve { visiveis: n } depois de mexer no HTML da aba
    function aplicarPainel(nomeAba, tokens) {
        var painel = painelDaAba[nomeAba];
        var itens = itensDaAba[nomeAba];
        var v = V[nomeAba];
        var buscando = tokens.length > 0;
        var visiveis = 0;

        itens.forEach(function (it) {
            var b = buscar(it, tokens);
            // * [EXPLICAÇÃO] → regra combinada com Matheus: enquanto há texto na
            //   busca, os filtros da barra nova ficam em pausa (os chips de
            //   destino/reembolso que já existiam continuam valendo).
            it.visivel = b.ok && bateChips(it, nomeAba, v.f) && (buscando || bateNovos(it, nomeAba, v.f));
            it.achados = b.ach;
            if (it.visivel) visiveis++;
        });

        if (ordemAplicada[nomeAba] !== v.o) {
            var recipiente = painel.querySelector('.dp-tabela-scroll');
            if (recipiente) {
                itens.slice().sort(comparadorDeOrdem(v.o)).forEach(function (it) { recipiente.appendChild(it.el); });
            }
            ordemAplicada[nomeAba] = v.o;
        }

        itens.forEach(function (it) {
            it.el.style.display = it.visivel ? '' : 'none';
            aplicarDestaquesNaLinha(it, tokens);
            aplicarAchouNaLinha(it, it.achados, tokens);
        });

        var aviso = painel.querySelector('.dp-vazio-busca');
        if (aviso) {
            if (aviso.getAttribute('data-texto-busca') === null) aviso.setAttribute('data-texto-busca', aviso.innerHTML);
            if (itens.length && visiveis === 0) {
                aviso.innerHTML = buscando
                    ? aviso.getAttribute('data-texto-busca')
                    : 'Nenhuma devolução nessa aba com os filtros escolhidos. <a href="#" data-dp-act="ver-todas">Ver todas</a>';
                aviso.style.display = 'block';
            } else {
                aviso.style.display = 'none';
            }
        }

        return { visiveis: visiveis, total: itens.length };
    }

    function sincronizarChips(nomeAba) {
        var painel = painelDaAba[nomeAba];
        var f = V[nomeAba].f;
        painel.querySelectorAll('.dp-filtro-secundario').forEach(function (grupo) {
            var tipo = grupo.getAttribute('data-tipo-filtro');
            grupo.querySelectorAll('.dp-chip-filtro').forEach(function (chip) {
                chip.classList.toggle('dp-chip-filtro--ativa', chip.getAttribute('data-filtro') === f[tipo]);
            });
        });
    }

    // ===================================================================
    // Barra "Ordenar / filtros" e linha do padrão salvo (desenhadas por JS)
    // ===================================================================

    function rotuloOrdem(o) { return ROTULO_ORDEM[o]; }

    function chipPopover(id, rotulo, ativo, valor) {
        return '<button type="button" class="dp-chip-filtro dp-chip-pop' + (ativo ? ' dp-chip-filtro--ativa' : '') + '" data-dp-act="pop" data-pop="' + id + '" aria-haspopup="true">' +
            rotulo + (valor ? ': <b>' + esc(valor) + '</b>' : '') + ' <i class="fas fa-chevron-down"></i></button>';
    }

    function resumoLista(lista, unidade) {
        return lista.length === 1 ? lista[0] : lista.length + ' ' + unidade;
    }

    function htmlDaBarra(nomeAba) {
        var v = V[nomeAba];
        var f = v.f;
        var h = '<div class="dp-barra">';
        h += chipPopover('ord', '<i class="fas fa-arrow-down-short-wide"></i> Ordenar por', v.o !== 'cadastro:desc', v.o !== 'cadastro:desc' ? rotuloOrdem(v.o) : '');
        h += '<span class="dp-barra-sep"></span>';
        h += chipPopover('plat', 'Plataforma', f.plat.length, f.plat.length ? resumoLista(f.plat, 'plataformas') : '');
        h += chipPopover('marca', 'Marca', f.marca.length, f.marca.length ? resumoLista(f.marca, 'marcas') : '');
        var periodoAtual = OPCOES_PERIODO.filter(function (p) { return p[0] === f.per; })[0];
        h += chipPopover('per', 'Período', !!f.per, f.per ? periodoAtual[1] : '');
        if (nomeAba === 'mediacao_aberta') {
            h += chipPopover('prazo', 'Prazo de resposta', f.prazo.length, f.prazo.length ? resumoLista(f.prazo.map(function (p) { return ROTULO_PRAZO[p]; }), 'situações') : '');
            h += '<button type="button" class="dp-chip-filtro dp-chip-pop' + (f.msg ? ' dp-chip-filtro--ativa' : '') + '" data-dp-act="tog-msg"><i class="fas fa-comment-dots"></i> Mensagem nova</button>';
        }
        var nMais = (f.rec7 ? 1 : 0) + (f.anot ? 1 : 0);
        h += '<button type="button" class="dp-chip-filtro dp-chip-pop' + (nMais ? ' dp-chip-filtro--ativa' : '') + '" data-dp-act="pop" data-pop="mais" aria-haspopup="true"><i class="fas fa-sliders"></i> Mais filtros' + (nMais ? ' <b>' + nMais + '</b>' : '') + '</button>';
        if (descreverFiltros(f, nomeAba).length) h += '<button type="button" class="dp-link dp-direita" data-dp-act="ver-todas"><i class="fas fa-xmark"></i> Ver todas (tirar filtros)</button>';
        return h + '</div>';
    }

    function htmlDoEstado(nomeAba) {
        var v = V[nomeAba];
        if (mudou(nomeAba)) {
            return '<div class="dp-estado dp-estado--temp"><span><i class="fas fa-circle-info"></i> Você mudou a organização desta aba. Ela vale só até você sair da tela.</span>' +
                '<span class="dp-estado-bts"><button type="button" class="dp-bt dp-bt--forte" data-dp-act="salvar"><i class="fas fa-bookmark"></i> Salvar como padrão desta aba</button>' +
                '<button type="button" class="dp-bt" data-dp-act="descartar">Descartar</button>' +
                (temSalvo(nomeAba) ? '<button type="button" class="dp-link" data-dp-act="original">Voltar ao padrão original</button>' : '') + '</span></div>';
        }
        if (temSalvo(nomeAba)) {
            var partes = [rotuloOrdem(v.o)].concat(descreverFiltros(v.f, nomeAba));
            return '<div class="dp-estado dp-estado--salvo"><span><i class="fas fa-bookmark"></i> <b>Padrão salvo</b> para ' + esc(NOME_EMPRESA) + ': ' + esc(partes.join(' · ')) + '</span>' +
                '<span class="dp-estado-bts"><button type="button" class="dp-link" data-dp-act="original">Voltar ao padrão original</button></span></div>';
        }
        return '';
    }

    function desenharBloco(nomeAba, resultado, tokens) {
        var recipiente = painelDaAba[nomeAba].querySelector('[data-organiza]');
        if (!recipiente) return;
        var v = V[nomeAba];
        var resumo = '<p class="dp-resumo">Mostrando <b>' + resultado.visiveis + '</b> de <b>' + resultado.total + '</b> nesta aba · ordem: <b>' + esc(rotuloOrdem(v.o)) + '</b>';
        if (tokens.length && novosAtivos(v.f, nomeAba)) {
            resumo += ' · <span class="dp-aviso"><i class="fas fa-circle-info"></i> enquanto você busca, os filtros da barra acima ficam em pausa (Destino e Reembolso continuam valendo)</span>';
        }
        recipiente.innerHTML = htmlDaBarra(nomeAba) + htmlDoEstado(nomeAba) + resumo + '</p>';
    }

    // ===================================================================
    // Janelinha de opções (Ordenar, Plataforma, Marca, Período, ...)
    // ===================================================================

    var janela = document.createElement('div');
    janela.className = 'dp-pop dp-pop--lista'; // --lista: o CSS de celular só mexe na janelinha desta tela (a Análise usa a mesma classe)
    janela.id = 'dp-pop';
    janela.hidden = true;
    document.body.appendChild(janela);
    var popAberto = null;

    function opcaoUnica(rotulo, ligada, dados) {
        return '<button type="button" class="dp-op' + (ligada ? ' dp-op--on' : '') + '" data-dp-act="set" ' + dados + '><i class="fas fa-check"></i><span>' + esc(rotulo) + '</span></button>';
    }

    function opcaoMultipla(rotulo, ligada, dados, quantidade) {
        return '<label class="dp-op"><input type="checkbox" data-dp-chg="tog" ' + dados + (ligada ? ' checked' : '') + '><span>' + esc(rotulo) + '</span>' +
            (quantidade != null ? '<em>' + quantidade + '</em>' : '') + '</label>';
    }

    function tituloPop(texto) { return '<h4>' + esc(texto) + '</h4>'; }

    function rodapeLimpar(campo) {
        return '<div class="dp-pop-rod"><button type="button" class="dp-link" data-dp-act="limpa-multi" data-f="' + campo + '">Limpar seleção</button></div>';
    }

    function dadosDoCampo(campo, valor, fechar) {
        return 'data-f="' + campo + '" data-v="' + esc(valor) + '"' + (fechar ? ' data-close="1"' : '');
    }

    // contagem por valor, só entre as devoluções da aba (sem olhar filtros)
    function valoresDistintos(itens, chave) {
        var vistos = {};
        itens.forEach(function (it) { if (it.d[chave]) vistos[it.d[chave]] = (vistos[it.d[chave]] || 0) + 1; });
        return vistos;
    }

    function htmlDaJanela(id) {
        var nomeAba = nomeDaAbaAtual();
        var v = V[nomeAba];
        var f = v.f;
        var itens = itensDaAba[nomeAba];
        var html = '';
        var contagem;

        if (id === 'ord') {
            html = tituloPop('Ordenar esta aba por') + MENU_ORDEM[nomeAba].map(function (o) {
                return opcaoUnica(rotuloOrdem(o) + (o === 'cadastro:desc' ? ' (como é hoje)' : ''), v.o === o, dadosDoCampo('o', o, true));
            }).join('');
        } else if (id === 'plat' || id === 'marca') {
            var chaveDado = id === 'plat' ? 'pn' : 'mn';
            contagem = valoresDistintos(itens, chaveDado);
            f[id].forEach(function (x) { if (!(x in contagem)) contagem[x] = 0; });
            html = tituloPop(id === 'plat' ? 'Plataforma' : 'Marca') + Object.keys(contagem).sort(function (a, b) { return a.localeCompare(b, 'pt-BR'); }).map(function (x) {
                return opcaoMultipla(x, tem(f[id], x), dadosDoCampo(id, x), contagem[x]);
            }).join('') + rodapeLimpar(id);
        } else if (id === 'per') {
            html = tituloPop('Período · ' + DATA_REFERENCIA[nomeAba].rotulo) + OPCOES_PERIODO.map(function (p) {
                return opcaoUnica(p[1], f.per === p[0], dadosDoCampo('per', p[0], true));
            }).join('');
        } else if (id === 'prazo') {
            html = tituloPop('Prazo de resposta') + Object.keys(ROTULO_PRAZO).map(function (k) {
                var qtd = itens.filter(function (it) { return (it.d.pst || 'sem') === k; }).length;
                return opcaoMultipla(ROTULO_PRAZO[k], tem(f.prazo, k), dadosDoCampo('prazo', k), qtd);
            }).join('') + rodapeLimpar('prazo');
        } else if (id === 'mais') {
            html = tituloPop('Reclamação dentro dos 7 dias') + [['', 'Tanto faz'], ['dentro', 'Dentro dos 7 dias'], ['fora', 'Fora dos 7 dias']].map(function (o) {
                return opcaoUnica(o[1], f.rec7 === o[0], dadosDoCampo('rec7', o[0]));
            }).join('') + tituloPop('Anotações') + [['', 'Tanto faz'], ['nota', 'Com anotação da mediação'], ['evid', 'Com evidência (fotos)']].map(function (o) {
                return opcaoUnica(o[1], f.anot === o[0], dadosDoCampo('anot', o[0]));
            }).join('');
        }
        return html;
    }

    function posicionarJanela() {
        if (!popAberto) { janela.hidden = true; return; }
        var gatilho = document.querySelector('.dp-tab-panel--ativa [data-dp-act="pop"][data-pop="' + popAberto + '"]');
        if (!gatilho) { fecharJanela(); return; }
        janela.hidden = false;
        gatilho.setAttribute('aria-expanded', 'true');
        var r = gatilho.getBoundingClientRect();
        var largura = janela.offsetWidth;
        var altura = janela.offsetHeight;
        var esquerda = Math.min(Math.max(10, r.left), Math.max(10, window.innerWidth - largura - 10));
        var topo = r.bottom + 6;
        if (topo + altura > window.innerHeight - 10 && r.top - altura - 6 > 10) topo = r.top - altura - 6;
        // * [EXPLICAÇÃO] → em tela baixa (celular) não cabia nem embaixo nem em cima do
        //   botão e a janelinha saía da tela. Agora ela sobe o quanto precisar pra ficar
        //   inteira à vista (cobrindo o botão, se for o caso). Se já cabia, não muda nada.
        topo = Math.max(10, Math.min(topo, window.innerHeight - altura - 10));
        janela.style.left = esquerda + 'px';
        janela.style.top = topo + 'px';
    }

    function abrirJanela(id) {
        popAberto = id;
        janela.innerHTML = htmlDaJanela(id);
        janela.hidden = false;
        posicionarJanela();
    }

    function fecharJanela() {
        popAberto = null;
        janela.hidden = true;
        document.querySelectorAll('.dp-chip-pop[aria-expanded]').forEach(function (b) { b.removeAttribute('aria-expanded'); });
    }

    // ===================================================================
    // Avisos rápidos (toast)
    // ===================================================================

    var toast = null;
    var timerToast = null;

    function avisar(html, erro) {
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'dp-toast';
            toast.setAttribute('role', 'status');
            toast.setAttribute('aria-live', 'polite');
            document.body.appendChild(toast);
        }
        toast.classList.toggle('dp-toast--erro', !!erro);
        toast.innerHTML = '<i class="fas fa-' + (erro ? 'triangle-exclamation' : 'circle-check') + '"></i><span>' + html + '</span>';
        toast.classList.add('dp-toast--visivel');
        clearTimeout(timerToast);
        timerToast = setTimeout(function () { toast.classList.remove('dp-toast--visivel'); }, erro ? 7000 : 4600);
    }

    // ===================================================================
    // Salvar / restaurar o padrão (POST pro Django — banco da empresa ativa)
    // ===================================================================

    function tokenCsrf() {
        var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }

    function enviar(url, corpo) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': tokenCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify(corpo)
        }).then(function (resposta) {
            return resposta.json().catch(function () { return {}; }).then(function (json) {
                if (!resposta.ok || !json.ok) throw new Error(json.erro || 'Não foi possível concluir agora.');
                return json;
            });
        });
    }

    function salvarPadrao(nomeAba) {
        if (!CONFIG.urlSalvar) return;
        var copia = clonar(V[nomeAba]);
        var jaTinha = temSalvo(nomeAba);
        enviar(CONFIG.urlSalvar, { chave: nomeAba, configuracao: copia }).then(function () {
            padroes[nomeAba] = copia;
            atualizarTudo(false);
            avisar((jaTinha ? 'Padrão atualizado' : 'Padrão salvo') + ' para <b>' + esc(NOME_EMPRESA) + '</b>. Na próxima vez que abrir a aba <b>' +
                esc(labelDaAba(document.querySelector('.dp-aba-btn[data-aba="' + nomeAba + '"]'))) + '</b>, ela já vem assim.');
        }).catch(function (erro) {
            avisar(esc(erro.message || 'Não foi possível salvar agora.'), true);
        });
    }

    function voltarAoPadraoOriginal(nomeAba) {
        if (!CONFIG.urlRestaurar) return;
        enviar(CONFIG.urlRestaurar, { chave: nomeAba }).then(function () {
            padroes[nomeAba] = null;
            V[nomeAba] = clonar(fabrica());
            sincronizarChips(nomeAba);
            atualizarTudo(false);
            avisar('Voltou ao padrão original (o de antes) para <b>' + esc(NOME_EMPRESA) + '</b>.');
        }).catch(function (erro) {
            avisar(esc(erro.message || 'Não foi possível voltar ao padrão agora.'), true);
        });
    }

    // ===================================================================
    // Atualização geral
    // ===================================================================

    // trocarSeNecessario = true só quando a própria digitação disparou a
    // atualização — assim, buscar troca de aba sozinho, mas trocar de aba
    // na mão ou clicar num chip nunca força uma 2ª troca.
    function atualizarTudo(trocarSeNecessario) {
        var tokens = tokensDaBusca();
        var buscando = tokens.length > 0;
        var acertosPorAba = {};

        abas.forEach(function (botaoAba) {
            var nomeAba = botaoAba.getAttribute('data-aba');
            var f = V[nomeAba].f;
            var acertos = itensDaAba[nomeAba].filter(function (it) {
                return buscar(it, tokens).ok && bateChips(it, nomeAba, f);
            }).length;
            acertosPorAba[nomeAba] = acertos;
            // * [EXPLICAÇÃO] → o número da aba continua sendo o total da aba
            //   (como sempre foi); só durante a busca ele mostra quantos
            //   acharam. A linha "Mostrando X de Y" é que diz quantos estão
            //   aparecendo com os filtros novos.
            botaoAba.querySelector('.dp-aba-contagem').textContent = buscando ? acertos : botaoAba.getAttribute('data-total');
        });

        var abaAtual = nomeDaAbaAtual();

        if (trocarSeNecessario && buscando && acertosPorAba[abaAtual] === 0) {
            var proxima = abas
                .map(function (a) { return a.getAttribute('data-aba'); })
                .find(function (nomeAba) { return acertosPorAba[nomeAba] > 0; });
            if (proxima) {
                mostrarPainel(proxima);
                abaAtual = proxima;
            }
        }

        if (nota) {
            if (buscando) {
                var outras = abas
                    .map(function (a) { return { nomeAba: a.getAttribute('data-aba'), label: labelDaAba(a) }; })
                    .filter(function (a) { return a.nomeAba !== abaAtual && acertosPorAba[a.nomeAba] > 0; });

                if (outras.length) {
                    nota.style.display = 'block';
                    nota.innerHTML = 'Também encontrado em: ' + outras.map(function (a) {
                        return '<a href="#" data-ir-aba="' + a.nomeAba + '">' + a.label + ' (' + acertosPorAba[a.nomeAba] + ')</a>';
                    }).join(' · ');
                } else {
                    nota.style.display = 'none';
                    nota.innerHTML = '';
                }
            } else {
                nota.style.display = 'none';
                nota.innerHTML = '';
            }
        }

        var resultado = aplicarPainel(abaAtual, tokens);
        desenharBloco(abaAtual, resultado, tokens);
        if (popAberto) {
            var rolagem = janela.scrollTop;
            janela.innerHTML = htmlDaJanela(popAberto);
            janela.scrollTop = rolagem;
            posicionarJanela();
        }
    }

    function aplicarFiltro(campo, valor) {
        var v = V[nomeDaAbaAtual()];
        if (campo === 'o') {
            v.o = valor;
        } else if (Array.isArray(v.f[campo])) {
            var i = v.f[campo].indexOf(valor);
            if (i >= 0) v.f[campo].splice(i, 1);
            else v.f[campo].push(valor);
        } else {
            v.f[campo] = valor;
        }
    }

    // ===================================================================
    // Eventos
    // ===================================================================

    abas.forEach(function (aba) {
        aba.addEventListener('click', function () {
            fecharJanela();
            mostrarPainel(aba.getAttribute('data-aba'));
            atualizarTudo(false);
        });
    });

    // chips que já existiam (Destino / Reembolso)
    document.querySelectorAll('.dp-filtro-secundario .dp-chip-filtro').forEach(function (chip) {
        chip.addEventListener('click', function () {
            var grupo = chip.closest('.dp-filtro-secundario');
            var nomeAba = nomeDaAbaAtual();
            V[nomeAba].f[grupo.getAttribute('data-tipo-filtro')] = chip.getAttribute('data-filtro');
            sincronizarChips(nomeAba);
            atualizarTudo(false);
        });
    });

    if (nota) {
        nota.addEventListener('click', function (e) {
            var alvo = e.target.closest('[data-ir-aba]');
            if (!alvo) return;
            e.preventDefault();
            fecharJanela();
            mostrarPainel(alvo.getAttribute('data-ir-aba'));
            atualizarTudo(false);
        });
    }

    if (campoBusca) {
        campoBusca.addEventListener('input', function () {
            atualizarTudo(true);
        });

        // * [EXPLICAÇÃO] → no celular a caixa de busca é estreita e o texto-guia
        //   comprido era cortado no meio ("...NF, c"). Lá ele fica curto; o texto
        //   completo continua como nome acessível do campo. No computador não muda.
        var textoGuiaCompleto = campoBusca.getAttribute('placeholder') || '';
        var textoGuiaCurto = 'Cliente, pedido ou produto...';
        var telaPequena = window.matchMedia ? window.matchMedia('(max-width: 700px)') : null;
        var ajustarTextoGuia = function () {
            var curto = !!(telaPequena && telaPequena.matches);
            campoBusca.setAttribute('placeholder', curto ? textoGuiaCurto : textoGuiaCompleto);
            if (curto) campoBusca.setAttribute('aria-label', textoGuiaCompleto);
            else campoBusca.removeAttribute('aria-label');
        };
        ajustarTextoGuia();
        if (telaPequena && telaPequena.addEventListener) telaPequena.addEventListener('change', ajustarTextoGuia);
    }

    document.addEventListener('click', function (e) {
        var alvo = e.target.closest('[data-dp-act]');
        if (popAberto && !e.target.closest('#dp-pop') && !(alvo && alvo.getAttribute('data-dp-act') === 'pop')) fecharJanela();
        if (!alvo) return;
        var acao = alvo.getAttribute('data-dp-act');
        if (alvo.tagName === 'A') e.preventDefault();
        var nomeAba = nomeDaAbaAtual();

        if (acao === 'pop') {
            var id = alvo.getAttribute('data-pop');
            if (popAberto === id) fecharJanela();
            else abrirJanela(id);
        } else if (acao === 'set') {
            aplicarFiltro(alvo.getAttribute('data-f'), alvo.getAttribute('data-v'));
            if (alvo.getAttribute('data-close')) fecharJanela();
            atualizarTudo(false);
        } else if (acao === 'limpa-multi') {
            V[nomeAba].f[alvo.getAttribute('data-f')] = [];
            atualizarTudo(false);
        } else if (acao === 'tog-msg') {
            V[nomeAba].f.msg = !V[nomeAba].f.msg;
            atualizarTudo(false);
        } else if (acao === 'ver-todas') {
            V[nomeAba].f = fabricaFiltros();
            sincronizarChips(nomeAba);
            fecharJanela();
            atualizarTudo(false);
        } else if (acao === 'salvar') {
            salvarPadrao(nomeAba);
        } else if (acao === 'descartar') {
            V[nomeAba] = clonar(baseDe(nomeAba));
            sincronizarChips(nomeAba);
            atualizarTudo(false);
        } else if (acao === 'original') {
            voltarAoPadraoOriginal(nomeAba);
        }
    });

    document.addEventListener('change', function (e) {
        var alvo = e.target;
        if (alvo.getAttribute && alvo.getAttribute('data-dp-chg') === 'tog') {
            aplicarFiltro(alvo.getAttribute('data-f'), alvo.getAttribute('data-v'));
            atualizarTudo(false);
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && popAberto) fecharJanela();
    });

    window.addEventListener('resize', posicionarJanela);
    window.addEventListener('scroll', posicionarJanela, true);

    // padrão salvo já vale desde a 1ª vez que a tela abre
    abas.forEach(function (botaoAba) { sincronizarChips(botaoAba.getAttribute('data-aba')); });
    var tipoDeAbertura = tipoDaNavegacao();
    var fotoParaRestaurar = estadoParaRestaurar(tipoDeAbertura);
    if (fotoParaRestaurar) {
        // só no voltar do histórico o navegador ainda tentaria rolar por conta própria: segura até terminar
        if (tipoDeAbertura === 'back_forward') {
            try { window.history.scrollRestoration = 'manual'; } catch (e) { /* ignora */ }
        }
        aplicarEstado(fotoParaRestaurar);
    } else {
        restaurarAbaAoRecarregar();
    }
    lembrarAba(nomeDaAbaAtual()); // guarda a aba com que a tela abriu (senão sobra a de uma visita antiga)
    atualizarTudo(false);
    if (fotoParaRestaurar) restaurarRolagem(fotoParaRestaurar, tipoDeAbertura === 'back_forward');

    // * [EXPLICAÇÃO] → "Ver na lista" da tela Análise (05/10/2026) abre esta
    //   tela com ?aba=<aba>&busca=<número do pedido>: já cai na aba certa,
    //   com o pedido na busca. Se um filtro de Destino/Reembolso (que
    //   continua valendo durante a busca) esconderia justamente essa
    //   devolução, ele é solto só nesta visita, pra ela aparecer. Depois de
    //   abrir, o endereço é limpo — atualizar a página volta ao normal.
    (function abrirPeloEndereco() {
        if (!campoBusca) return;
        var parametros;
        try { parametros = new URLSearchParams(window.location.search); } catch (e) { return; }
        var busca = parametros.get('busca');
        if (!busca) return;
        var aba = parametros.get('aba');
        var tokens = norm(busca).split(/\s+/).filter(Boolean);

        if (aba && Object.prototype.hasOwnProperty.call(painelDaAba, aba)) {
            var achados = itensDaAba[aba].filter(function (it) { return buscar(it, tokens).ok; });
            if (achados.length && !achados.some(function (it) { return bateChips(it, aba, V[aba].f); })) {
                V[aba].f.destino = 'todos';
                V[aba].f.reembolso = 'todos';
                sincronizarChips(aba);
            }
            mostrarPainel(aba);
        }

        campoBusca.value = busca;
        atualizarTudo(true);
        avisar('Mostrando a devolução do pedido <b>' + esc(busca) + '</b>. Limpe a busca para ver a aba toda.');
        try { window.history.replaceState(null, '', window.location.pathname); } catch (e) { /* sem histórico: segue assim mesmo */ }
    })();
})();


// Popover flutuante compartilhado pelos 2 ícones da célula ANOTAÇÕES —
// existe em TODAS as abas agora (pedido de Matheus, 28/09/2026, ampliado
// 02/10/2026 pro padrão valer nas 5 abas): o de evidência busca o
// conteúdo sob demanda (só quando o mouse passa em cima, nunca carrega
// foto de devolução nenhuma antes disso — HTML já vem pronto do backend,
// mesmas classes vd-* reaproveitadas de visualizar_devolucao, com cache
// no navegador por devolução); o de anotação da mediação já tem o texto
// pronto na própria linha (dentro de um <template>, sem custo nenhum de
// rede) — o popover só lê o conteúdo de um jeito ou de outro e mostra do
// mesmo formato pros 2. Os listeners ficam no `document` (não presos a 1
// painel só) porque o ícone agora pode aparecer em qualquer uma das 5
// abas.
(function () {
    var popover = document.createElement('div');
    popover.className = 'vd-cartao dp-tabela-popover';
    document.body.appendChild(popover);

    var cacheHtmlPorId = {};
    var idAtual = null;
    var timeoutEsconder = null;
    // * [EXPLICAÇÃO] → celular (sem mouse): o toque dispara "mouseover" e logo depois
    //   "mouseout" de mentirinha, conforme o navegador, e a janelinha fechava sozinha
    //   pouco depois de abrir. Aqui o toque no ícone FIXA a janelinha; ela só fecha
    //   com um toque fora dela (ou rolando a página). No computador nada muda.
    var semMouse = window.matchMedia ? window.matchMedia('(hover: none)') : null;
    var fixadoPorToque = false;

    function posicionar(icone) {
        var retangulo = icone.getBoundingClientRect();
        var margemViewport = 10;
        // * [EXPLICAÇÃO] → esse é o vão vertical entre o ícone e o
        //   popover — de propósito bem pequeno (não usa margemViewport
        //   aqui), porque um vão grande vira uma faixa "morta" que o
        //   mouse precisa atravessar sem tocar nem no ícone nem no
        //   popover. Era exatamente isso que fechava o preview antes de
        //   dar tempo do mouse chegar nele.
        var espacamento = 4;
        var largura = popover.offsetWidth;
        var altura = popover.offsetHeight;

        var esquerda = retangulo.left + (retangulo.width / 2) - (largura / 2);
        esquerda = Math.max(margemViewport, Math.min(esquerda, window.innerWidth - largura - margemViewport));

        var acima = retangulo.top - altura - espacamento;
        var topo = acima >= margemViewport ? acima : retangulo.bottom + espacamento;

        popover.style.left = esquerda + 'px';
        popover.style.top = topo + 'px';
    }

    function esconder() {
        popover.classList.remove('dp-tabela-popover--visivel');
        idAtual = null;
        fixadoPorToque = false;
    }

    function mostrar(icone) {
        // * [EXPLICAÇÃO] → ícone de anotação: o texto já está pronto na
        //   própria linha, dentro de um <template> escondido (sem
        //   nenhum custo de rede) — só copia o conteúdo dele pro
        //   popover. Ícone de evidência: continua buscando sob demanda,
        //   como antes.
        var alvoInline = icone.getAttribute('data-popover-alvo');
        if (alvoInline) {
            var template = document.getElementById(alvoInline);
            if (!template) return;
            idAtual = alvoInline;
            popover.innerHTML = template.innerHTML;
            popover.classList.add('dp-tabela-popover--visivel');
            posicionar(icone);
            return;
        }

        var id = icone.getAttribute('data-devolucao-id');
        var url = icone.getAttribute('data-evidencia-url');
        if (!id || !url) return;
        idAtual = id;

        function exibir(html) {
            if (idAtual !== id) return;
            popover.innerHTML = html;
            popover.classList.add('dp-tabela-popover--visivel');
            posicionar(icone);
        }

        if (cacheHtmlPorId[id]) {
            exibir(cacheHtmlPorId[id]);
            return;
        }

        popover.innerHTML = '<p class="vd-sem-fotos">Carregando...</p>';
        popover.classList.add('dp-tabela-popover--visivel');
        posicionar(icone);

        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resposta) { return resposta.text(); })
            .then(function (html) {
                cacheHtmlPorId[id] = html;
                exibir(html);
            })
            .catch(function () {
                if (idAtual === id) {
                    popover.innerHTML = '<p class="vd-sem-fotos">Não foi possível carregar a evidência agora.</p>';
                }
            });
    }

    document.addEventListener('mouseover', function (evento) {
        var icone = evento.target.closest('.dp-tabela-evidencia-icone, .dp-tabela-anotacao-icone');
        if (!icone) return;
        clearTimeout(timeoutEsconder);
        mostrar(icone);
    });

    document.addEventListener('click', function (evento) {
        if (!semMouse || !semMouse.matches) return;
        var icone = evento.target.closest('.dp-tabela-evidencia-icone, .dp-tabela-anotacao-icone');
        if (icone) {
            clearTimeout(timeoutEsconder);
            fixadoPorToque = true;
            var chave = icone.getAttribute('data-popover-alvo') || icone.getAttribute('data-devolucao-id');
            // o "mouseover" do próprio toque normalmente já abriu a janelinha: não busca de novo
            if (idAtual !== chave || !popover.classList.contains('dp-tabela-popover--visivel')) mostrar(icone);
            return;
        }
        if (popover.contains(evento.target)) return;
        if (fixadoPorToque) esconder();
    });

    document.addEventListener('mouseout', function (evento) {
        if (fixadoPorToque) return;
        var icone = evento.target.closest('.dp-tabela-evidencia-icone, .dp-tabela-anotacao-icone');
        if (!icone) return;
        // * [EXPLICAÇÃO] → antes só considerava "ainda em cima" se o
        //   mouse continuasse DENTRO do ícone. Se o mouse pulasse direto
        //   do ícone pro popover (sem passar por espaço vazio no meio),
        //   isso não contava e agendava o fechamento à toa — agora conta
        //   também quando cai direto dentro do popover.
        if (icone.contains(evento.relatedTarget) || popover.contains(evento.relatedTarget)) return;
        timeoutEsconder = setTimeout(esconder, 300);
    });

    popover.addEventListener('mouseenter', function () {
        clearTimeout(timeoutEsconder);
    });

    popover.addEventListener('mouseleave', function () {
        if (fixadoPorToque) return;
        timeoutEsconder = setTimeout(esconder, 300);
    });

    // * [EXPLICAÇÃO] → o scroll da PÁGINA fecha o popover (senão ele fica
    //   visualmente descolado do ícone conforme a lista rola). Mas o
    //   scroll de DENTRO do próprio popover (arrastando as fotos/lista
    //   dele, que tem overflow-y:auto) TAMBÉM dispara esse mesmo evento
    //   'scroll' em fase de captura — sem esse filtro, rolar o conteúdo
    //   do popover fechava ele na primeira tentativa, antes de dar tempo
    //   de ver qualquer coisa.
    window.addEventListener('scroll', function (evento) {
        if (popover.contains(evento.target)) return;
        esconder();
    }, true);
})();