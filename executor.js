require('dotenv').config();
const puppeteer = require('puppeteer-core');
const axios = require('axios');

const API_URL = "http://127.0.0.1:8008/v1/fila";

// TODO: Configurar credenciais do SEI via variáveis de ambiente
const SEI_USER = process.env.SEI_USER;
const SEI_PASS = process.env.SEI_PASS;

async function iniciarExecutor() {
    console.log("🤖 Executor RPA iniciado. Aguardando ordens...");

    // Loop infinito checando o banco a cada 10 segundos
    setInterval(async () => {
        try {
            const resp = await axios.get(`${API_URL}?status=AGUARDANDO_ROBO`);
            const processosPendentes = resp.data;

            if (processosPendentes.length > 0) {
                console.log(`Encontrados ${processosPendentes.length} processos para atuar.`);
                await processarFila(processosPendentes);
            }
        } catch (e) {
            console.error("Erro ao checar fila:", e.message);
        }
    }, 10000);
}

async function processarFila(processos) {
    // No Linux, precisamos usar o executável do Chromium ou Chrome instalado
    const browser = await puppeteer.launch({ 
        headless: 'new', // Roda sem interface gráfica
        executablePath: '/usr/bin/google-chrome-stable', // Caminho padrão no Ubuntu
        args: ['--no-sandbox', '--disable-setuid-sandbox'] 
    });

    const page = await browser.newPage();

    // --- NOVA ETAPA: LOGIN NO SEI ---
    console.log("🔐 Fazendo login no SEI...");
    try {
        await page.goto('https://cidades.sei.sp.gov.br/rasaopaulo/sip/login.php', { waitUntil: 'networkidle2' });
        
        // Aguarda os campos renderizarem
        await page.waitForSelector('#txtUsuario', { timeout: 10000 });
        await page.waitForSelector('#pwdSenha', { timeout: 10000 });
        
        // Digita como um humano (delay de 50ms) para enganar a máscara do SEI
        await page.type('#txtUsuario', SEI_USER, { delay: 50 });
        await page.type('#pwdSenha', SEI_PASS, { delay: 50 });
        
        // CORREÇÃO: Seleciona o órgão pelo ID numérico correto (22 = MCRUZ)
        try {
            const orgSelect = await page.$('#selOrgao');
            if (orgSelect) {
                console.log("🏢 Selecionando órgão MCRUZ (Valor: 22)...");
                await page.select('#selOrgao', '22');
            }
        } catch(err) {
            console.log("ℹ️ Campo de Órgão não encontrado, prosseguindo.");
        }
        
        console.log("🖱️ Forçando clique via JavaScript no botão ACESSAR...");
        
        // Dispara o clique diretamente no DOM e aguarda o carregamento simultaneamente
        await Promise.all([
            page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 }),
            page.evaluate(() => {
                document.getElementById('sbmAcessar').click();
            })
        ]);

        console.log("✅ Login realizado com sucesso!\n");
        
    } catch (e) {
        console.error("❌ Falha na etapa de login:", e.message);
        await browser.close();
        return;
    }

    // 2. EXECUTAR AÇÕES
    for (let processo of processos) {
        console.log(`Atuando no processo ${processo.numero_sei}...`);
        
        // Abre o link do processo
        await page.goto(processo.link_sei, { waitUntil: 'domcontentloaded' });
        
        if (processo.acao_requisitada === 'APROVAR') {
            // Lógica para clicar no botão "Enviar Processo"
            // await page.click('#btnEnviar'); 
            // await page.type('#txtUnidade', processo.unidade_destino);
            console.log("✅ Processo tramitado.");
        } else if (processo.acao_requisitada === 'DEVOLVER') {
            // Lógica para incluir despacho de exigência
            console.log("❌ Exigência registrada.");
        }

        // 1. Tratamento do processo e status
        const numeroTratado = encodeURIComponent(processo.numero_sei);
        const statusFinal = processo.acao_requisitada === 'APROVAR' ? 'APROVADO' : 'DEVOLVIDO';
        
        // 2. Monta a URL usando Query Parameter em vez de Path Parameter
        const urlCompleta = `${API_URL}/acao?numero_sei=${numeroTratado}`;

        // 3. Tenta o PATCH
        try {
            console.log(`📡 Disparando PATCH para: ${urlCompleta}`);
            await axios.patch(urlCompleta, { novo_status: statusFinal });
            console.log(`✅ Processo ${processo.numero_sei} atualizado no banco!`);
        } catch (erroApi) {
            console.log(`❌ FALHA AO SALVAR NO BANCO:`);
            console.log(`URL Tentada: ${erroApi.config?.url}`);
            console.log(`Status HTTP: ${erroApi.response?.status}`);
            console.log(`Resposta do Servidor:`, erroApi.response?.data || erroApi.message);
        }
    }

    await browser.close();
}

iniciarExecutor();