// devolucoes/static/devolucoes/js/script_analise_devolucoes.js

// Função Objetivo: toda a interação da tela Análise (pedido de Matheus,
// 05/10/2026) — uma tabela com as devoluções de TODAS as etapas juntas:
// busca (cliente, pedido, produto, NF, código de barras, código do
// fabricante e marca; ignora acento; cada palavra digitada precisa
// aparecer em algum lugar), filtros (Etapa, Plataforma, Marca, Destino,
// Reembolso, Tipo de venda e Período — com escolha de qual data usar),
// colunas à escolha, ordenar clicando no título da coluna, totais,
// paginação (25/50/100 por página), "padrão salvo" (filtros + colunas +
// ordem + linhas por página, guardado no banco da empresa ativa pelos
// mesmos endereços da tela Devoluções) e "Exportar para Excel".
//
// * [EXPLICAÇÃO] → igual à tela Devoluções, tudo é client-side: o Django
//   manda todas as devoluções de uma vez (bloco #an-dados, montado em
//   views._linha_da_analise) e aqui só filtramos/ordenamos/mostramos.
//   A única coisa que vai pro servidor é salvar/restaurar o padrão e a
//   exportação (que manda os números das devoluções filtradas, na ordem
//   da tabela, e o Django monta o arquivo). Esta tela NÃO altera nenhuma
//   devolução — só consulta.

(function () {
    var recipienteBarra = document.getElementById('an-barra');
    var recipienteResultado = document.getElementById('an-resultado');
    var campoBusca = document.getElementById('an-busca');
    if (!recipienteBarra || !recipienteResultado) return;

    // ===================================================================
    // Utilidades pequenas
    // ===================================================================

    // * [EXPLICAÇÃO] → MESMA regra da tela Devoluções: tira acento e põe
    //   minúsculo, nos 2 lados (o que está guardado e o que foi digitado).
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
    function dois(n) { return (n < 10 ? '0' : '') + n; }

    function lerJson(id) {
        var el = document.getElementById(id);
        if (!el) return null;
        try { return JSON.parse(el.textContent); } catch (e) { return null; }
    }

    // As datas chegam como "número do dia" (date.toordinal do Python);
    // 719163 é o número do dia 01/01/1970.
    function formatarDia(ordinal) {
        if (ordinal == null) return '—';
        var d = new Date((ordinal - 719163) * 86400000);
        return dois(d.getUTCDate()) + '/' + dois(d.getUTCMonth() + 1) + '/' + d.getUTCFullYear();
    }

    function moeda(valor) {
        return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    // dinheiro é somado em centavos (inteiros) pra não acumular erro de
    // arredondamento de número com vírgula
    function centavos(valor) { return Math.round(valor * 100); }

    // ===================================================================
    // Vocabulário (nomes que a Ana lê na tela — vêm do Django)
    // ===================================================================

    var CONFIG = lerJson('an-config') || {};
    var DADOS = lerJson('an-dados') || [];
    var NOME_EMPRESA = CONFIG.empresa || 'esta empresa';
    var HOJE = CONFIG.hoje;

    var ETAPAS = CONFIG.etapas || [];
    var DESTINOS = CONFIG.destinos || [];
    var TIPOS = CONFIG.tipos || [];
    var PLATAFORMAS_CONHECIDAS = CONFIG.plataformas || [];
    var COLUNAS = (CONFIG.colunas || []).map(function (c) { return { k: c[0], t: c[1], num: !!c[2] }; });
    var CHAVES_COLUNAS = COLUNAS.map(function (c) { return c.k; });
    var COLUNAS_PADRAO = (CONFIG.colunasPadrao || []).filter(function (k) { return tem(CHAVES_COLUNAS, k); });
    var CHAVES_ETAPAS = ETAPAS.map(function (e) { return e[0]; });

    function rotuloDe(pares, chave) {
        for (var i = 0; i < pares.length; i++) { if (pares[i][0] === chave) return pares[i][1]; }
        return chave;
    }

    var CLASSE_DO_SELO = {
        aguardando_conferencia: 'aguardando',
        conferido: 'conferido',
        mediacao_aberta: 'mediacao-aberta',
        mediacao_encerrada: 'mediacao-encerrada',
        impresso: 'impresso'
    };

    // qual data o filtro "Período" usa (campos do pacote montado no views.py)
    var OPCOES_DATA_DO_PERIODO = [
        ['criado', 'Cadastro'],
        ['venda', 'Data da venda'],
        ['abertura', 'Mediação aberta'],
        ['fim', 'Mediação encerrada'],
        ['impresso', 'Impressa em']
    ];
    var CAMPO_DA_DATA = { criado: 'cadd', venda: 'vd', abertura: 'ab', fim: 'fim', impresso: 'impd' };

    var OPCOES_PERIODO = [
        ['', 'Qualquer data'],
        ['7', 'Últimos 7 dias'],
        ['30', 'Últimos 30 dias'],
        ['90', 'Últimos 90 dias']
    ];

    var LINHAS_POR_PAGINA = [25, 50, 100];

    // 1º clique em número/data ordena do maior pro menor (o que a Ana quer
    // ver primeiro: o mais recente, o maior valor); texto, de A a Z.
    var PRIMEIRO_DECRESCENTE = /^(criado|venda|abertura|fim|impresso|reemb)$/;

    function primeiroDecrescente(chave) {
        var col = null;
        COLUNAS.forEach(function (c) { if (c.k === chave) col = c; });
        return (col && col.num) || PRIMEIRO_DECRESCENTE.test(chave);
    }

    // ===================================================================
    // As linhas (1 por devolução) e o que cada coluna mostra/ordena
    // ===================================================================

    var LINHAS = DADOS.map(function (d) {
        return {
            d: d,
            // texto já sem acento/minúsculo, pronto pra buscar e ordenar
            n: {
                ped: norm(d.ped), cli: norm(d.cli), prod: norm(d.prod), nf: norm(d.nf),
                cod: norm(d.cod), ean: norm(d.ean), marca: norm(d.mn), plat: norm(d.pn)
            }
        };
    });

    function diferenca(d) {
        if (d.val == null || d.preco == null) return null;
        return (centavos(d.preco) - centavos(d.val)) / 100;
    }

    function dinheiro(valor) { return valor == null ? '—' : 'R$ ' + moeda(valor); }

    // sv = valor usado pra ordenar (null = "sem valor", vai sempre pro
    // fim) · fm = HTML da célula · nw = não quebrar linha
    var COMPORTAMENTO = {
        pedido: { sv: function (r) { return r.n.ped; }, fm: function (r, t) { return destacar(r.d.ped, t); }, nw: true },
        cliente: { sv: function (r) { return r.n.cli; }, fm: function (r, t) { return destacar(r.d.cli, t); }, nw: true },
        produto: { sv: function (r) { return r.n.prod; }, fm: function (r) { return '<span class="an-clip" title="' + esc(r.d.prod) + '">' + esc(r.d.prod) + '</span>'; } },
        marca: { sv: function (r) { return r.n.marca; }, fm: function (r) { return esc(r.d.mn); } },
        plat: { sv: function (r) { return r.n.plat; }, fm: function (r) { return esc(r.d.pn); }, nw: true },
        tipo: { sv: function (r) { return r.d.tipo; }, fm: function (r) { return esc(rotuloDe(TIPOS, r.d.tipo)); }, nw: true },
        etapa: {
            sv: function (r) { return CHAVES_ETAPAS.indexOf(r.d.et); },
            fm: function (r) { return '<span class="dp-badge dp-badge--' + (CLASSE_DO_SELO[r.d.et] || 'aguardando') + '">' + esc(rotuloDe(ETAPAS, r.d.et)) + '</span>'; },
            nw: true
        },
        destino: { sv: function (r) { return r.d.dst || null; }, fm: function (r) { return r.d.dst ? esc(rotuloDe(DESTINOS, r.d.dst)) : '—'; }, nw: true },
        criado: { sv: function (r) { return r.d.cad; }, fm: function (r) { return formatarDia(r.d.cadd); }, nw: true },
        venda: { sv: function (r) { return r.d.vd; }, fm: function (r) { return formatarDia(r.d.vd); }, nw: true },
        abertura: { sv: function (r) { return r.d.ab; }, fm: function (r) { return formatarDia(r.d.ab); }, nw: true },
        fim: { sv: function (r) { return r.d.fim; }, fm: function (r) { return formatarDia(r.d.fim); }, nw: true },
        impresso: { sv: function (r) { return r.d.imp; }, fm: function (r) { return formatarDia(r.d.impd); }, nw: true },
        reemb: {
            sv: function (r) { return r.d.rb === 1 ? 2 : (r.d.rb === 0 ? 1 : 0); },
            fm: function (r) { return r.d.rb === 1 ? 'Sim' : (r.d.rb === 0 ? 'Não' : '—'); },
            nw: true
        },
        valor: { sv: function (r) { return r.d.val; }, fm: function (r) { return dinheiro(r.d.val); }, nw: true },
        preco: { sv: function (r) { return r.d.preco; }, fm: function (r) { return dinheiro(r.d.preco); }, nw: true },
        dif: { sv: function (r) { return diferenca(r.d); }, fm: function (r) { return dinheiro(diferenca(r.d)); }, nw: true }
    };

    // ===================================================================
    // Estado: ordem + filtros + colunas + linhas por página (+ padrão salvo)
    // ===================================================================

    // * [EXPLICAÇÃO] → o "padrão original" (de fábrica) é o que a Análise
    //   mostra quando ninguém salvou nada: do cadastro mais recente pro
    //   mais antigo, dos últimos 90 dias, 8 colunas, 25 linhas por página.
    function fabricaFiltros() {
        return { etapa: [], plat: [], marca: [], destino: '', reemb: '', tipo: '', perCampo: 'criado', per: '90' };
    }

    function fabrica() {
        return { o: 'criado:desc', f: fabricaFiltros(), cols: COLUNAS_PADRAO.slice(), pp: 25, page: 1 };
    }

    function listaDeTextos(valor, permitidos) {
        if (!Array.isArray(valor)) return [];
        var vistos = [];
        valor.forEach(function (x) {
            if (typeof x === 'string' && (!permitidos || tem(permitidos, x)) && !tem(vistos, x)) vistos.push(x);
        });
        return vistos;
    }

    // * [EXPLICAÇÃO] → o padrão salvo vem do banco como "o que tinha na
    //   cabeça da tela no dia"; antes de usar, confere item por item. Se
    //   uma opção sumiu ou o dado veio estranho, aquele item volta ao
    //   normal em vez de quebrar a tela.
    function normalizar(configuracao) {
        var v = fabrica();
        if (!configuracao || typeof configuracao !== 'object') return v;

        if (typeof configuracao.o === 'string') {
            var partes = configuracao.o.split(':');
            if (tem(CHAVES_COLUNAS, partes[0]) && (partes[1] === 'asc' || partes[1] === 'desc')) v.o = configuracao.o;
        }

        var f = configuracao.f || {};
        v.f.etapa = listaDeTextos(f.etapa, CHAVES_ETAPAS);
        v.f.plat = listaDeTextos(f.plat);
        v.f.marca = listaDeTextos(f.marca);
        if (typeof f.destino === 'string' && (f.destino === '' || DESTINOS.some(function (x) { return x[0] === f.destino; }))) v.f.destino = f.destino;
        if (tem(['', 'sim', 'nao'], f.reemb)) v.f.reemb = f.reemb;
        if (typeof f.tipo === 'string' && (f.tipo === '' || TIPOS.some(function (x) { return x[0] === f.tipo; }))) v.f.tipo = f.tipo;
        if (OPCOES_DATA_DO_PERIODO.some(function (x) { return x[0] === f.perCampo; })) v.f.perCampo = f.perCampo;
        if (typeof f.per === 'string' && OPCOES_PERIODO.some(function (x) { return x[0] === f.per; })) v.f.per = f.per;

        var colunas = listaDeTextos(configuracao.cols, CHAVES_COLUNAS);
        if (colunas.length) v.cols = colunas;
        if (tem(LINHAS_POR_PAGINA, configuracao.pp)) v.pp = configuracao.pp;
        return v;
    }

    var salvo = lerJson('an-padrao') ? normalizar(lerJson('an-padrao')) : null;
    var V = clonar(salvo || fabrica());
    var textoBusca = '';

    function baseDe() { return salvo || fabrica(); }
    function temSalvo() { return !!salvo; }

    // "mudou?" ignora a página em que a Ana está e a ordem em que ela
    // ligou/desligou as opções (só o conjunto escolhido conta)
    function assinatura(v) {
        var c = clonar(v);
        delete c.page;
        ['etapa', 'plat', 'marca'].forEach(function (k) { c.f[k] = c.f[k].slice().sort(); });
        c.cols = c.cols.slice().sort();
        return JSON.stringify(c);
    }

    function mudou() { return assinatura(V) !== assinatura(baseDe()); }

    function configuracaoParaSalvar() {
        var c = clonar(V);
        delete c.page;
        return c;
    }

    // ===================================================================
    // Regras: busca, filtros, ordem
    // ===================================================================

    function tokensDaBusca() {
        return norm(textoBusca).split(/\s+/).filter(Boolean);
    }

    // cada palavra digitada precisa aparecer em algum lugar da devolução
    function buscar(r, tokens) {
        var n = r.n;
        for (var t = 0; t < tokens.length; t++) {
            var token = tokens[t];
            if (n.cli.indexOf(token) === -1 && n.ped.indexOf(token) === -1 && n.prod.indexOf(token) === -1 &&
                n.nf.indexOf(token) === -1 && n.cod.indexOf(token) === -1 && n.ean.indexOf(token) === -1 &&
                n.marca.indexOf(token) === -1) return false;
        }
        return true;
    }

    function bate(r, f, tokens) {
        var d = r.d;
        if (!buscar(r, tokens)) return false;
        if (f.etapa.length && !tem(f.etapa, d.et)) return false;
        if (f.plat.length && !tem(f.plat, d.pn)) return false;
        if (f.marca.length && !tem(f.marca, d.mn)) return false;
        if (f.destino && d.dst !== f.destino) return false;
        // "não reembolsadas" inclui as sem informação (mesma regra dos chips da tela Devoluções)
        if (f.reemb && (d.rb === 1 ? 'sim' : 'nao') !== f.reemb) return false;
        if (f.tipo && d.tipo !== f.tipo) return false;
        if (f.per) {
            var ref = d[CAMPO_DA_DATA[f.perCampo]];
            if (ref == null || HOJE - ref > +f.per) return false;
        }
        return true;
    }

    function comparador(ordem) {
        var partes = ordem.split(':');
        var comportamento = COMPORTAMENTO[partes[0]] || COMPORTAMENTO.criado;
        var sinal = partes[1] === 'desc' ? -1 : 1;
        return function (a, b) {
            var x = comportamento.sv(a);
            var y = comportamento.sv(b);
            if (x != null || y != null) {
                if (x == null) return 1;
                if (y == null) return -1;
                if (x < y) return -1 * sinal;
                if (x > y) return 1 * sinal;
            }
            // empate: cadastro mais recente primeiro (e o número, pra ser sempre igual)
            return (b.d.cad - a.d.cad) || (b.d.id - a.d.id);
        };
    }

    // todas as devoluções que passam nos filtros e na busca, já na ordem
    function linhasFiltradas() {
        var tokens = tokensDaBusca();
        return LINHAS.filter(function (r) { return bate(r, V.f, tokens); }).sort(comparador(V.o));
    }

    function colunasEscolhidas() {
        return COLUNAS.filter(function (c) { return tem(V.cols, c.k); });
    }

    function descreverFiltros(f) {
        var d = [];
        if (f.etapa.length) d.push('Etapa: ' + f.etapa.map(function (k) { return rotuloDe(ETAPAS, k); }).join(', '));
        if (f.plat.length) d.push('Plataforma: ' + f.plat.join(', '));
        if (f.marca.length) d.push('Marca: ' + f.marca.join(', '));
        if (f.destino) d.push('Destino: ' + rotuloDe(DESTINOS, f.destino));
        if (f.reemb) d.push(f.reemb === 'sim' ? 'Reembolsadas' : 'Não reembolsadas');
        if (f.tipo) d.push(rotuloDe(TIPOS, f.tipo));
        if (f.per) d.push(rotuloDe(OPCOES_DATA_DO_PERIODO, f.perCampo) + ': ' + rotuloDe(OPCOES_PERIODO, f.per).toLowerCase());
        return d;
    }

    // ===================================================================
    // Palavras achadas (destaque amarelo em Pedido e Cliente)
    // ===================================================================

    function destacar(texto, tokens) {
        if (!tokens || !tokens.length) return esc(texto);
        var chars = Array.from(String(texto));
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

    // ===================================================================
    // Barra de filtros e linha do padrão salvo
    // ===================================================================

    function chipPopover(id, rotulo, ativo, valor) {
        return '<button type="button" class="dp-chip-filtro dp-chip-pop' + (ativo ? ' dp-chip-filtro--ativa' : '') + '" data-an-act="pop" data-pop="' + id + '" aria-haspopup="true">' +
            rotulo + (valor ? ': <b>' + esc(valor) + '</b>' : '') + ' <i class="fas fa-chevron-down"></i></button>';
    }

    function resumoLista(lista, unidade) {
        return lista.length === 1 ? lista[0] : lista.length + ' ' + unidade;
    }

    function htmlDaBarra() {
        var f = V.f;
        var h = '<div class="dp-barra an-barra">';
        h += chipPopover('etapa', 'Etapa', f.etapa.length, f.etapa.length ? resumoLista(f.etapa.map(function (k) { return rotuloDe(ETAPAS, k); }), 'etapas') : '');
        h += chipPopover('plat', 'Plataforma', f.plat.length, f.plat.length ? resumoLista(f.plat, 'plataformas') : '');
        h += chipPopover('marca', 'Marca', f.marca.length, f.marca.length ? resumoLista(f.marca, 'marcas') : '');
        h += chipPopover('destino', 'Destino', !!f.destino, f.destino ? rotuloDe(DESTINOS, f.destino) : '');
        h += chipPopover('reemb', 'Reembolso', !!f.reemb, f.reemb ? (f.reemb === 'sim' ? 'Reembolsadas' : 'Não reembolsadas') : '');
        h += chipPopover('tipo', 'Tipo de venda', !!f.tipo, f.tipo ? rotuloDe(TIPOS, f.tipo) : '');
        h += chipPopover('per', 'Período', !!f.per, f.per ? rotuloDe(OPCOES_DATA_DO_PERIODO, f.perCampo) + ' · ' + rotuloDe(OPCOES_PERIODO, f.per) : '');
        if (descreverFiltros(f).length) h += '<button type="button" class="dp-link dp-direita" data-an-act="limpar"><i class="fas fa-xmark"></i> Tirar filtros</button>';
        return h + '</div>';
    }

    function htmlDoEstado() {
        if (mudou()) {
            return '<div class="dp-estado dp-estado--temp"><span><i class="fas fa-circle-info"></i> Você mudou filtros, colunas ou ordem. Vale só até você sair da tela.</span>' +
                '<span class="dp-estado-bts"><button type="button" class="dp-bt dp-bt--forte" data-an-act="salvar"><i class="fas fa-bookmark"></i> Salvar como padrão da Análise</button>' +
                '<button type="button" class="dp-bt" data-an-act="descartar">Descartar</button>' +
                (temSalvo() ? '<button type="button" class="dp-link" data-an-act="original">Voltar ao padrão original</button>' : '') + '</span></div>';
        }
        if (temSalvo()) {
            return '<div class="dp-estado dp-estado--salvo"><span><i class="fas fa-bookmark"></i> <b>Padrão salvo</b> para ' + esc(NOME_EMPRESA) + '</span>' +
                '<span class="dp-estado-bts"><button type="button" class="dp-link" data-an-act="original">Voltar ao padrão original</button></span></div>';
        }
        return '';
    }

    function desenharBarra() {
        recipienteBarra.innerHTML = htmlDaBarra() + htmlDoEstado();
        var contador = document.getElementById('an-ncols');
        if (contador) contador.textContent = V.cols.length;
    }

    // ===================================================================
    // Totais, tabela e paginação
    // ===================================================================

    function desenharResultado() {
        var tokens = tokensDaBusca();
        var linhas = linhasFiltradas();
        var total = linhas.length;
        var paginas = Math.max(1, Math.ceil(total / V.pp));
        V.page = Math.min(Math.max(1, V.page), paginas);
        var inicio = (V.page - 1) * V.pp;
        var fatia = linhas.slice(inicio, inicio + V.pp);
        var colunas = colunasEscolhidas();
        var partes = V.o.split(':');

        var nReembolsadas = 0;
        var somaReembolsado = 0;
        var somaPreco = 0;
        var semPreco = 0;
        linhas.forEach(function (r) {
            if (r.d.rb === 1) {
                nReembolsadas++;
                if (r.d.val != null) somaReembolsado += centavos(r.d.val);
            }
            if (r.d.preco != null) somaPreco += centavos(r.d.preco);
            else semPreco++;
        });

        var h = '<div class="an-totais">' +
            '<div><span>Devoluções encontradas</span><b>' + total + '</b></div>' +
            '<div><span>Reembolsadas</span><b>' + nReembolsadas + '</b><em>R$ ' + moeda(somaReembolsado / 100) + '</em></div>' +
            '<div><span>Preço dos produtos</span><b>R$ ' + moeda(somaPreco / 100) + '</b>' +
            (semPreco ? '<small>' + semPreco + ' sem preço informado</small>' : '') + '</div></div>';

        h += '<div class="an-scroll"><table class="an-tab"><thead><tr>';
        colunas.forEach(function (c) {
            var ativo = c.k === partes[0];
            h += '<th class="' + (c.num ? 'an-num ' : '') + (ativo ? 'an-th--ord' : '') + '"' +
                (ativo ? ' aria-sort="' + (partes[1] === 'asc' ? 'ascending' : 'descending') + '"' : '') + '>' +
                '<button type="button" data-an-act="ordenar" data-k="' + c.k + '" title="Ordenar por ' + esc(c.t) + '">' + esc(c.t) +
                ' <i class="fas fa-' + (ativo ? (partes[1] === 'asc' ? 'sort-up' : 'sort-down') : 'sort') + '"></i></button></th>';
        });
        h += '<th class="an-acao"></th></tr></thead><tbody>';

        if (!fatia.length) {
            var temFiltros = descreverFiltros(V.f).length > 0;
            var mensagem = tokens.length
                ? (temFiltros ? 'Nenhuma devolução com essa busca e esses filtros.' : 'Nenhuma devolução encontrada com esse termo.')
                : 'Nenhuma devolução com esses filtros.';
            h += '<tr><td colspan="' + (colunas.length + 1) + '" class="an-vazio">' + mensagem +
                (temFiltros ? ' <a href="#" data-an-act="limpar">Tirar filtros</a>' : '') + '</td></tr>';
        }

        fatia.forEach(function (r) {
            h += '<tr>';
            colunas.forEach(function (c) {
                var comportamento = COMPORTAMENTO[c.k];
                h += '<td class="' + (c.num ? 'an-num ' : '') + (comportamento.nw ? 'an-nw' : '') + '">' + comportamento.fm(r, tokens) + '</td>';
            });
            h += '<td class="an-acao"><a class="dp-btn dp-tabela-btn an-ver" href="' + esc(enderecoNaLista(r.d)) + '" title="Abre esta devolução na tela Devoluções, na aba certa"><i class="fas fa-arrow-up-right-from-square"></i> Ver na lista</a></td></tr>';
        });
        h += '</tbody></table></div>';

        var de = total ? inicio + 1 : 0;
        var ate = Math.min(inicio + V.pp, total);
        h += '<div class="an-pag"><span>' + (total ? 'Mostrando <b>' + de + '–' + ate + '</b> de <b>' + total + '</b>' : 'Nada para mostrar') + '</span><span class="an-pag-ctl">' +
            '<label for="an-pp">Linhas por página</label><select id="an-pp" data-an-chg="pp">' +
            LINHAS_POR_PAGINA.map(function (n) { return '<option value="' + n + '"' + (n === V.pp ? ' selected' : '') + '>' + n + '</option>'; }).join('') + '</select>' +
            '<button type="button" class="dp-btn dp-tabela-btn" data-an-act="pagina" data-d="-1"' + (V.page <= 1 ? ' disabled' : '') + '><i class="fas fa-chevron-left"></i> Anterior</button>' +
            '<span class="an-pag-n">Página ' + V.page + ' de ' + paginas + '</span>' +
            '<button type="button" class="dp-btn dp-tabela-btn" data-an-act="pagina" data-d="1"' + (V.page >= paginas ? ' disabled' : '') + '>Próxima <i class="fas fa-chevron-right"></i></button></span></div>';

        recipienteResultado.innerHTML = h;
    }

    // * [EXPLICAÇÃO] → "Ver na lista": abre a tela Devoluções já na aba em
    //   que essa devolução está, com o número do pedido na busca (a tela
    //   Devoluções lê ?aba=...&busca=... — ver o fim do
    //   script_devolucoes_pendentes.js). É um link de verdade, então
    //   também dá pra abrir em outra aba do navegador.
    function enderecoNaLista(d) {
        return (CONFIG.urlLista || '') + '?aba=' + encodeURIComponent(d.et) + '&busca=' + encodeURIComponent(d.ped);
    }

    // ===================================================================
    // Janelinha de opções (Etapa, Plataforma, Marca, ..., Colunas)
    // ===================================================================

    var janela = document.createElement('div');
    janela.className = 'dp-pop';
    janela.id = 'an-pop';
    janela.hidden = true;
    document.body.appendChild(janela);
    var popAberto = null;

    function opcaoUnica(rotulo, ligada, dados) {
        return '<button type="button" class="dp-op' + (ligada ? ' dp-op--on' : '') + '" data-an-act="set" ' + dados + '><i class="fas fa-check"></i><span>' + esc(rotulo) + '</span></button>';
    }

    function opcaoMultipla(rotulo, ligada, dados, quantidade) {
        return '<label class="dp-op"><input type="checkbox" data-an-chg="tog" ' + dados + (ligada ? ' checked' : '') + '><span>' + esc(rotulo) + '</span>' +
            (quantidade != null ? '<em>' + quantidade + '</em>' : '') + '</label>';
    }

    function tituloPop(texto) { return '<h4>' + esc(texto) + '</h4>'; }

    function rodapeLimpar(campo) {
        return '<div class="dp-pop-rod"><button type="button" class="dp-link" data-an-act="limpa-multi" data-f="' + campo + '">Limpar seleção</button></div>';
    }

    function dadosDoCampo(campo, valor, fechar) {
        return 'data-f="' + campo + '" data-v="' + esc(valor) + '"' + (fechar ? ' data-close="1"' : '');
    }

    // quantas devoluções existem por valor (no total, sem olhar filtros)
    function contarPor(chave) {
        var contagem = {};
        LINHAS.forEach(function (r) {
            var valor = r.d[chave];
            if (valor) contagem[valor] = (contagem[valor] || 0) + 1;
        });
        return contagem;
    }

    function htmlDaJanela(id) {
        var f = V.f;
        var html = '';
        var contagem;

        if (id === 'etapa') {
            contagem = contarPor('et');
            html = tituloPop('Etapa') + ETAPAS.map(function (e) {
                return opcaoMultipla(e[1], tem(f.etapa, e[0]), dadosDoCampo('etapa', e[0]), contagem[e[0]] || 0);
            }).join('') + rodapeLimpar('etapa');
        } else if (id === 'plat' || id === 'marca') {
            contagem = contarPor(id === 'plat' ? 'pn' : 'mn');
            f[id].forEach(function (x) { if (!(x in contagem)) contagem[x] = 0; });
            var nomes = Object.keys(contagem);
            if (id === 'plat') {
                // plataformas na ordem do sistema; qualquer outra que apareça vem depois, em ordem alfabética
                nomes.sort(function (a, b) {
                    var ia = PLATAFORMAS_CONHECIDAS.indexOf(a);
                    var ib = PLATAFORMAS_CONHECIDAS.indexOf(b);
                    if (ia === -1 && ib === -1) return a.localeCompare(b, 'pt-BR');
                    if (ia === -1) return 1;
                    if (ib === -1) return -1;
                    return ia - ib;
                });
            } else {
                nomes.sort(function (a, b) { return a.localeCompare(b, 'pt-BR'); });
            }
            html = tituloPop(id === 'plat' ? 'Plataforma' : 'Marca') + nomes.map(function (x) {
                return opcaoMultipla(x, tem(f[id], x), dadosDoCampo(id, x), contagem[x]);
            }).join('') + rodapeLimpar(id);
        } else if (id === 'destino') {
            html = tituloPop('Destino') + [['', 'Todos']].concat(DESTINOS).map(function (o) {
                return opcaoUnica(o[1], f.destino === o[0], dadosDoCampo('destino', o[0], true));
            }).join('');
        } else if (id === 'reemb') {
            html = tituloPop('Reembolso') + [['', 'Todos'], ['sim', 'Reembolsadas'], ['nao', 'Não reembolsadas']].map(function (o) {
                return opcaoUnica(o[1], f.reemb === o[0], dadosDoCampo('reemb', o[0], true));
            }).join('');
        } else if (id === 'tipo') {
            html = tituloPop('Tipo de venda') + [['', 'Todos']].concat(TIPOS).map(function (o) {
                return opcaoUnica(o[1], f.tipo === o[0], dadosDoCampo('tipo', o[0], true));
            }).join('');
        } else if (id === 'per') {
            html = tituloPop('Qual data usar') + OPCOES_DATA_DO_PERIODO.map(function (o) {
                return opcaoUnica(o[1], f.perCampo === o[0], dadosDoCampo('perCampo', o[0]));
            }).join('') + tituloPop('Janela') + OPCOES_PERIODO.map(function (o) {
                return opcaoUnica(o[1], f.per === o[0], dadosDoCampo('per', o[0]));
            }).join('');
        } else if (id === 'cols') {
            html = tituloPop('Colunas da tabela') + COLUNAS.map(function (c) {
                return opcaoMultipla(c.t, tem(V.cols, c.k), dadosDoCampo('cols', c.k));
            }).join('') + '<div class="dp-pop-rod"><button type="button" class="dp-link" data-an-act="colunas-padrao">Voltar às colunas padrão</button></div>';
        }
        return html;
    }

    function posicionarJanela() {
        if (!popAberto) { janela.hidden = true; return; }
        var gatilho = document.querySelector('[data-an-act="pop"][data-pop="' + popAberto + '"]');
        if (!gatilho) { fecharJanela(); return; }
        janela.hidden = false;
        gatilho.setAttribute('aria-expanded', 'true');
        var r = gatilho.getBoundingClientRect();
        var largura = janela.offsetWidth;
        var altura = janela.offsetHeight;
        var esquerda = Math.min(Math.max(10, r.left), Math.max(10, window.innerWidth - largura - 10));
        var topo = r.bottom + 6;
        if (topo + altura > window.innerHeight - 10 && r.top - altura - 6 > 10) topo = r.top - altura - 6;
        janela.style.left = esquerda + 'px';
        janela.style.top = topo + 'px';
    }

    function abrirJanela(id) {
        popAberto = id;
        // a lista de colunas é a mais comprida: ganha uma janela mais alta pra caber sem rolar
        janela.classList.toggle('dp-pop--alto', id === 'cols');
        janela.innerHTML = htmlDaJanela(id);
        janela.hidden = false;
        posicionarJanela();
    }

    function fecharJanela() {
        popAberto = null;
        janela.hidden = true;
        document.querySelectorAll('[data-an-act="pop"][aria-expanded]').forEach(function (b) { b.removeAttribute('aria-expanded'); });
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
    // Salvar / restaurar o padrão e exportar (pedidos pro Django)
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

    function salvarPadrao() {
        if (!CONFIG.urlSalvar) return;
        var copia = configuracaoParaSalvar();
        var jaTinha = temSalvo();
        enviar(CONFIG.urlSalvar, { chave: CONFIG.chave || 'analise', configuracao: copia }).then(function () {
            salvo = normalizar(copia);
            desenharTudo();
            avisar((jaTinha ? 'Padrão atualizado' : 'Padrão salvo') + ' para <b>' + esc(NOME_EMPRESA) + '</b>. Na próxima vez que abrir a Análise, ela já vem assim.');
        }).catch(function (erro) {
            avisar(esc(erro.message || 'Não foi possível salvar agora.'), true);
        });
    }

    function voltarAoPadraoOriginal() {
        if (!CONFIG.urlRestaurar) return;
        enviar(CONFIG.urlRestaurar, { chave: CONFIG.chave || 'analise' }).then(function () {
            salvo = null;
            V = clonar(fabrica());
            desenharTudo();
            avisar('Voltou ao padrão original (o de antes) para <b>' + esc(NOME_EMPRESA) + '</b>.');
        }).catch(function (erro) {
            avisar(esc(erro.message || 'Não foi possível voltar ao padrão agora.'), true);
        });
    }

    var exportando = false;

    // * [EXPLICAÇÃO] → manda pro Django só os números das devoluções que
    //   estão na tabela (já filtradas, NA ORDEM da tela) e as colunas
    //   escolhidas; o servidor relê essas devoluções do banco e monta o
    //   .xlsx. O arquivo baixa sem sair da tela.
    function exportar() {
        if (exportando || !CONFIG.urlExportar) return;
        var linhas = linhasFiltradas();
        var colunas = colunasEscolhidas();
        if (!linhas.length) {
            avisar('Não há devoluções para exportar com esses filtros.', true);
            return;
        }
        var botao = document.querySelector('[data-an-act="exportar"]');
        var dados = new FormData();
        dados.append('ids', linhas.map(function (r) { return r.d.id; }).join(','));
        dados.append('colunas', colunas.map(function (c) { return c.k; }).join(','));

        exportando = true;
        if (botao) botao.disabled = true;
        avisar('Gerando o Excel com <b>' + linhas.length + '</b> ' + (linhas.length === 1 ? 'devolução' : 'devoluções') + '...');

        fetch(CONFIG.urlExportar, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': tokenCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
            body: dados
        }).then(function (resposta) {
            if (!resposta.ok) throw new Error('Não foi possível gerar o Excel agora.');
            var cabecalho = resposta.headers.get('Content-Disposition') || '';
            var achado = /filename="?([^";]+)"?/.exec(cabecalho);
            var nome = achado ? achado[1] : 'analise_devolucoes.xlsx';
            return resposta.blob().then(function (blob) { return { blob: blob, nome: nome }; });
        }).then(function (arquivo) {
            var url = URL.createObjectURL(arquivo.blob);
            var link = document.createElement('a');
            link.href = url;
            link.download = arquivo.nome;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
            avisar('Excel pronto: <b>' + esc(arquivo.nome) + '</b> (' + linhas.length + ' ' + (linhas.length === 1 ? 'devolução' : 'devoluções') + ', ' + colunas.length + ' coluna' + plural(colunas.length) + '). Veja na pasta de downloads do navegador.');
        }).catch(function (erro) {
            avisar(esc(erro.message || 'Não foi possível gerar o Excel agora.'), true);
        }).then(function () {
            exportando = false;
            if (botao) botao.disabled = false;
        });
    }

    // ===================================================================
    // Atualização geral e eventos
    // ===================================================================

    function atualizarJanelaAberta() {
        if (!popAberto) return;
        var rolagem = janela.scrollTop;
        janela.innerHTML = htmlDaJanela(popAberto);
        janela.scrollTop = rolagem;
        posicionarJanela();
    }

    function desenharTudo() {
        desenharBarra();
        desenharResultado();
        atualizarJanelaAberta();
    }

    function aplicarFiltro(campo, valor) {
        if (campo === 'cols') {
            var i = V.cols.indexOf(valor);
            if (i >= 0) { if (V.cols.length > 1) V.cols.splice(i, 1); } // pelo menos 1 coluna fica
            else V.cols.push(valor);
        } else if (Array.isArray(V.f[campo])) {
            var j = V.f[campo].indexOf(valor);
            if (j >= 0) V.f[campo].splice(j, 1);
            else V.f[campo].push(valor);
        } else {
            V.f[campo] = valor;
        }
        V.page = 1;
    }

    function rolarParaOResultado() {
        if (recipienteResultado.scrollIntoView) recipienteResultado.scrollIntoView({ block: 'start' });
    }

    document.addEventListener('click', function (e) {
        var alvo = e.target.closest('[data-an-act]');
        if (popAberto && !e.target.closest('#an-pop') && !(alvo && alvo.getAttribute('data-an-act') === 'pop')) fecharJanela();
        if (!alvo) return;
        var acao = alvo.getAttribute('data-an-act');
        if (alvo.tagName === 'A' && alvo.getAttribute('href') === '#') e.preventDefault();

        if (acao === 'pop') {
            var id = alvo.getAttribute('data-pop');
            if (popAberto === id) fecharJanela();
            else abrirJanela(id);
        } else if (acao === 'set') {
            aplicarFiltro(alvo.getAttribute('data-f'), alvo.getAttribute('data-v'));
            if (alvo.getAttribute('data-close')) fecharJanela();
            desenharTudo();
        } else if (acao === 'limpa-multi') {
            V.f[alvo.getAttribute('data-f')] = [];
            V.page = 1;
            desenharTudo();
        } else if (acao === 'colunas-padrao') {
            V.cols = COLUNAS_PADRAO.slice();
            desenharTudo();
        } else if (acao === 'limpar') {
            V.f = fabricaFiltros();
            V.f.per = '';
            V.page = 1;
            fecharJanela();
            desenharTudo();
        } else if (acao === 'ordenar') {
            var chave = alvo.getAttribute('data-k');
            var atual = V.o.split(':');
            V.o = chave + ':' + (atual[0] === chave ? (atual[1] === 'asc' ? 'desc' : 'asc') : (primeiroDecrescente(chave) ? 'desc' : 'asc'));
            V.page = 1;
            desenharTudo();
        } else if (acao === 'pagina') {
            V.page += +alvo.getAttribute('data-d');
            desenharResultado();
            rolarParaOResultado();
        } else if (acao === 'salvar') {
            salvarPadrao();
        } else if (acao === 'descartar') {
            V = clonar(baseDe());
            desenharTudo();
        } else if (acao === 'original') {
            voltarAoPadraoOriginal();
        } else if (acao === 'exportar') {
            exportar();
        }
    });

    document.addEventListener('change', function (e) {
        var alvo = e.target;
        if (!alvo.getAttribute) return;
        var tipo = alvo.getAttribute('data-an-chg');
        if (tipo === 'tog') {
            aplicarFiltro(alvo.getAttribute('data-f'), alvo.getAttribute('data-v'));
            desenharTudo();
        } else if (tipo === 'pp') {
            V.pp = +alvo.value;
            V.page = 1;
            desenharTudo();
        }
    });

    if (campoBusca) {
        // a barra de filtros não depende do que foi digitado: só a tabela e os totais se refazem
        campoBusca.addEventListener('input', function () {
            textoBusca = campoBusca.value.trim();
            V.page = 1;
            desenharResultado();
        });
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && popAberto) fecharJanela();
    });

    window.addEventListener('resize', posicionarJanela);
    window.addEventListener('scroll', posicionarJanela, true);

    desenharTudo();
})();
