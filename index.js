require('dotenv').config();
const puppeteer = require('puppeteer-core');
const axios = require('axios');

const SEI_USER = process.env.SEI_USER;
const SEI_PASS = process.env.SEI_PASS;

async function iniciarRPA() {
    console.log("🤖 Iniciando Motor de IA - Modo Servidor (Headless)...");
    
    let browser;
    try {
        // Lança um novo Chrome invisível usando o binário do sistema Linux
        browser = await puppeteer.launch({ 
            headless: 'new',
            executablePath: '/usr/bin/google-chrome-stable',
            timeout: 60000,
            protocolTimeout: 120000,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'] 
        });
    } catch (err) {
        console.error("❌ Erro ao lançar o Chrome headless:", err.message);
        process.exit(1);
    }

    const page = await browser.newPage();

    page.setDefaultNavigationTimeout(90000); 
    page.setDefaultTimeout(90000);

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
            page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }),
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

    console.log("🔍 Minerando processos na caixa de entrada...");

    const linksMinerados = await page.evaluate(() => {
        const todosLinks = Array.from(document.querySelectorAll('a'));
        return todosLinks
            .map(a => a.href)
            .filter(href => href && href.includes('acao=procedimento_trabalhar'))
            .filter((value, index, self) => self.indexOf(value) === index);
    });

    console.log(`\n🚀 Iniciando raspagem oficial de ${linksMinerados.length} processos...\n`);

    const abaProcessamento = await browser.newPage();

    for (let link of linksMinerados) {
        console.log(`==================================================`);
        console.log(`⏳ Abrindo processo...`);
        
        try {
            await abaProcessamento.goto(link, { waitUntil: 'domcontentloaded', timeout: 30000 });
            await new Promise(r => setTimeout(r, 3000));

            const frameArvore = abaProcessamento.frames().find(f => f.name() === 'ifrArvore');
            if (!frameArvore) continue;

            const dadosArvore = await frameArvore.evaluate(() => {
                const links = Array.from(document.querySelectorAll('a'));
                const textos = links.map(a => a.innerText.trim()).filter(t => t.length > 2);
                const numeroProc = textos.find(t => /\d+\.\d+\.\d+\/\d+-\d+/.test(t)) || textos[0];
                
                const linksDocumentos = links.filter(a => a.href && a.href.includes('id_documento'));
                const palavrasChave = ['requerimento', 'protocolo geral', 'memorando', 'ofício', 'formulário', 'solicitação'];
                
                let tagAlvo = null;

                for (let a of linksDocumentos) {
                    const nomeDoc = a.innerText.toLowerCase();
                    if (palavrasChave.some(p => nomeDoc.includes(p))) {
                        tagAlvo = a;
                        break;
                    }
                }

                if (!tagAlvo && linksDocumentos.length > 0) {
                    tagAlvo = linksDocumentos[0];
                }

                let nomeAlvo = 'Desconhecido';
                if (tagAlvo) {
                    nomeAlvo = tagAlvo.innerText.trim();
                    tagAlvo.click(); 
                }

                // BLACKLIST: Ignora botões do sistema
                const botoesLixo = ['fechar', 'link para acesso direto', 'consultar andamento', 'abrir'];

                let listaAnexosLimpa = linksDocumentos
                    .map(a => a.innerText.trim())
                    .filter(nome => nome !== nomeAlvo) // Remove o doc principal
                    .filter(nome => !botoesLixo.includes(nome.toLowerCase())) // Remove botões
                    // REGRA DE OURO DO SEI: O nome do documento tem que ter o número SEI (6 a 8 dígitos)...
                    .filter(nome => /\d{6,8}/.test(nome))
                    // ... Mas não pode ser APENAS o número (ex: "0823794")
                    .filter(nome => !/^\d+$/.test(nome))
                    // ... E não pode ser o número da pasta do Processo raiz
                    .filter(nome => !/^\d{7}\.\d{3}/.test(nome));

                // REMOVE DUPLICATAS: O SEI gera 3 textos iguais por arquivo. O Set() deixa apenas 1 único de cada.
                listaAnexosLimpa = [...new Set(listaAnexosLimpa)];

                return {
                    numeroProcesso: numeroProc,
                    nomeDocPrincipal: nomeAlvo,
                    sucesso: !!tagAlvo,
                    anexos: listaAnexosLimpa
                };
            });

            if (!dadosArvore.sucesso) {
                console.log("⚠️ Nenhum documento clicável na árvore.");
                continue;
            }

            let numeroProcessoSEI = (dadosArvore.numeroProcesso || `SEI-${Date.now()}`).replace(/[\n\r]/g, '').trim();
            console.log(`📂 Processo: ${numeroProcessoSEI}`);
            console.log(`📄 Documento Alvo: ${dadosArvore.nomeDocPrincipal}`);
            console.log(`📎 Anexos identificados: ${dadosArvore.anexos.length > 0 ? dadosArvore.anexos.join(' | ') : 'Nenhum'}`);

            console.log(`⏳ Aguardando renderização do texto no frame da direita (Polling)...`);
            
            // LOOP DE POLLING: Tenta ler o texto até 5 vezes (esperando 3s a cada tentativa)
            let textoBruto = "";
            let tentativas = 0;
            const maxTentativas = 5;

            while (textoBruto.length < 50 && tentativas < maxTentativas) {
                await new Promise(r => setTimeout(r, 3000)); // Espera 3s

                const frameVisual = abaProcessamento.frames().find(f => f.name() === 'ifrVisualizacao');
                if (frameVisual) {
                    textoBruto = await frameVisual.evaluate(() => {
                        const iframeInterno = document.querySelector('iframe');
                        if (iframeInterno && iframeInterno.contentDocument) {
                            return iframeInterno.contentDocument.body.innerText;
                        }
                        return document.body.innerText || "";
                    });
                }
                tentativas++;
            }

            if (textoBruto.length < 50) {
                console.log("⚠️ O documento parece estar vazio, falhou ao carregar no tempo limite ou é um PDF de imagem sem OCR.");
                continue;
            }

            console.log(`\n👁️ O QUE O ROBÔ LEU DO DOCUMENTO (${textoBruto.length} chars)`);

            const decisao = await classificarComIA(textoBruto, dadosArvore.anexos, numeroProcessoSEI);
            console.log("✅ DECISÃO DA IA:\n", JSON.stringify(decisao, null, 2));

            console.log(`💾 Salvando na Fila (sei_ai_db)...`);
            await salvarNaFila(numeroProcessoSEI, decisao, link, dadosArvore.anexos);

        } catch (erro) {
            console.log(`❌ Erro: ${erro.message}`);
        }
        await new Promise(r => setTimeout(r, 6000));
    }

    console.log("\n🚀 Carga oficial concluída com sucesso!");
    await abaProcessamento.close();
    await browser.disconnect();
}

async function classificarComIA(textoDocumento, listaAnexos, numeroProcesso) {
    const endpoint = "http://127.0.0.1:8008/v1/triagem";
    const textoLimitado = textoDocumento.substring(0, 4000);

    const contextoEnriquecido = `
    DADOS EXTRAÍDOS PELO SISTEMA (Metadados):
    - Processo SEI: ${numeroProcesso}
    - Arquivos Anexados: ${listaAnexos.length > 0 ? listaAnexos.join(", ") : "Nenhum"}
    
    TEXTO DO DOCUMENTO:
    ${textoLimitado}
    `;

    try {
        const resp = await axios.post(endpoint, { texto_processo: contextoEnriquecido }, { headers: { "Content-Type": "application/json" }});
        if (resp.data.servico_identificado) resp.data.servico_identificado = resp.data.servico_identificado.replace(/^ID\s\d+:\s*/i, '');
        return resp.data;
    } catch (e) {
        return { servico_identificado: "ERRO DE IA", id_servico: null, resumo_pedido: "Falha", status_documentacao: "ERRO", documentos_faltantes: [] };
    }
}

async function salvarNaFila(numeroSei, decisaoIA, linkProcesso, listaAnexos) {
    const endpointFila = "http://127.0.0.1:8008/v1/fila";
    const linkAcessoDireto = linkProcesso.replace('acao=procedimento_trabalhar', 'acao=procedimento_controlar');

    try {
        await axios.post(endpointFila, {
            numero_sei: numeroSei,
            link_sei: linkAcessoDireto,
            servico_nome: decisaoIA.servico_identificado,
            servico_id: decisaoIA.id_servico,
            resumo_ia: decisaoIA.resumo_pedido,
            status_documentacao: decisaoIA.status_documentacao,
            documentos_faltantes: decisaoIA.documentos_faltantes || [],
            anexos_enviados: listaAnexos || []
        }, { headers: { "Content-Type": "application/json" }});
    } catch (e) {
        console.error("❌ Erro ao salvar no banco:", e.message);
    }
}

iniciarRPA();