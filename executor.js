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
    const browser = await puppeteer.launch({ 
        headless: 'new',
        executablePath: '/usr/bin/google-chrome-stable',
        timeout: 60000,
        protocolTimeout: 120000,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'] 
    });

    const page = await browser.newPage();
    page.setDefaultNavigationTimeout(90000); 
    page.setDefaultTimeout(90000);

    console.log("🔐 Fazendo login no SEI...");
    try {
        await page.goto('https://cidades.sei.sp.gov.br/rasaopaulo/sip/login.php', { waitUntil: 'networkidle2' });
        await page.waitForSelector('#txtUsuario', { timeout: 10000 });
        await page.waitForSelector('#pwdSenha', { timeout: 10000 });
        
        await page.type('#txtUsuario', SEI_USER, { delay: 50 });
        await page.type('#pwdSenha', SEI_PASS, { delay: 50 });
        
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
        await Promise.all([
            page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }),
            page.evaluate(() => document.getElementById('sbmAcessar').click())
        ]);

        console.log("✅ Login realizado com sucesso!\n");
    } catch (e) {
        console.error("❌ Falha na etapa de login:", e.message);
        await browser.close();
        return;
    }

    // 2. EXECUTAR AÇÕES (NOVO FLUXO: ANOTAÇÕES)
    for (let processo of processos) {
        console.log(`Atuando no processo ${processo.numero_sei}...`);
        
        try {
            await page.goto(processo.link_sei, { waitUntil: 'networkidle2' });
            
            // 2.1 Acessar o iframe principal onde fica a barra de ícones
            const frameProcesso = await page.frames().find(f => f.name() === 'ifrVisualizacao');
            if (!frameProcesso) throw new Error("Iframe de visualização não encontrado.");

            // 2.2 Localizar o botão de Anotação (geralmente uma imagem com title "Anotações")
            await frameProcesso.waitForSelector('img[title*="Anotação"], a[title*="Anotação"]', { timeout: 10000 });

            // 2.3 Clicar e capturar o Popup que o SEI abre
            const [popup] = await Promise.all([
                new Promise(resolve => browser.once('targetcreated', target => resolve(target.page()))),
                frameProcesso.click('img[title*="Anotação"], a[title*="Anotação"]')
            ]);

            if (!popup) throw new Error("Popup de anotação não abriu.");

            // 2.4 Preencher o texto no popup
            await popup.waitForSelector('#txaDescricao', { timeout: 10000 });
            
            // Monta o texto bonitão (Ajuste as propriedades conforme sua API devolve)
            const textoAnotacao = `🤖 IA (Triagem Prévia):\nServiço: ${processo.servico_nome || 'Não identificado'}\nResumo: ${processo.resumo_ia || 'Sem resumo disponível.'}\nDocs: ${processo.status_documentacao || 'Não avaliado'}`;
            
            await popup.type('#txaDescricao', textoAnotacao, { delay: 10 });
            
            // 2.5 Salvar
            await popup.click('#btnSalvar');
            
            // Espera a requisição terminar de salvar (delay seguro)
            await new Promise(r => setTimeout(r, 2500));
            if (!popup.isClosed()) await popup.close();

            console.log("✅ Anotação registrada com sucesso no SEI.");

            // 3. Atualiza no Banco
            const numeroTratado = encodeURIComponent(processo.numero_sei);
            const urlCompleta = `${API_URL}/acao?numero_sei=${numeroTratado}`;

            console.log(`📡 Disparando PATCH para: ${urlCompleta}`);
            await axios.patch(urlCompleta, { novo_status: 'TRIADO_COM_ANOTACAO' });
            console.log(`✅ Processo ${processo.numero_sei} atualizado no banco!`);

        } catch (erroProcesso) {
            console.log(`❌ Falha ao atuar no processo ${processo.numero_sei}:`, erroProcesso.message);
        }
    }

    await browser.close();
}