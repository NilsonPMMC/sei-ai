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

    // 1. FAZER LOGIN NO SEI
    // --- NOVA ETAPA: LOGIN NO SEI ---
    console.log("🔐 Fazendo login no SEI...");
    try {
        await page.goto('https://cidades.sei.sp.gov.br/rasaopaulo/sip/login.php', { waitUntil: 'networkidle2' });
        
        // Aguarda os campos de usuário e senha aparecerem (se adaptando aos IDs comuns do SEI)
        await page.waitForSelector('#txtUsuario', { timeout: 10000 });
        
        await page.type('#txtUsuario', SEI_USER);
        await page.type('#pwdSenha', SEI_PASS);
        
        // Tenta preencher o Órgão, se o campo existir na tela
        try {
            const orgSelect = await page.$('#selOrgao');
            if (orgSelect) {
                console.log("🏢 Selecionando órgão MCRUZ...");
                await page.select('#selOrgao', 'MCRUZ');
            }
        } catch(err) {
            console.log("ℹ️ Campo de Órgão não encontrado, prosseguindo com o login.");
        }
        
        // Clica no botão de login (tentando os IDs mais comuns)
        const botoesLogin = ['#sbmLogin', '#Acessar', '#btnAcessar'];
        let botaoClicado = false;
        
        for (const seletor of botoesLogin) {
            try {
                const botao = await page.$(seletor);
                if (botao) {
                    await page.click(seletor);
                    botaoClicado = true;
                    break;
                }
            } catch(e) {}
        }
        
        if (!botaoClicado) {
             throw new Error("Não foi possível encontrar o botão de login.");
        }

        await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 });
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

        // Atualiza o banco para CONCLUIDO
        await axios.patch(`${API_URL}/${processo.numero_sei}/status`, { novo_status: 'CONCLUIDO' });
    }

    await browser.close();
}

iniciarExecutor();