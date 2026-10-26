# Política de segurança

O ForecastLab é um **projeto de portfólio** feito para rodar **localmente**. Ele vem apenas com dados sintéticos e
não precisa de contas, chaves de API nem serviços em nuvem.

## O que este repositório contém e o que não contém

* Nenhuma credencial, token, chave de API ou string de conexão — nada disso é necessário para rodar o app.
* Nenhum dado real de empresa, cliente, produto ou pessoa — a base de demonstração é gerada por código
  (`backend/synthetic_data_generator`, reproduzível com `random_seed`).
* O banco local (`database/*.duckdb`), arquivos `.env` e arquivos de chave/certificado são excluídos pelo
  `.gitignore`. Logos de clientes usados em demonstrações privadas (`frontend/public/brand/`) e o
  `frontend/.env.local` também ficam fora do git.

## Seguro por padrão em tempo de execução

* A API (`uvicorn`) escuta em `127.0.0.1` por padrão, e o `docker compose` publica as portas apenas em `127.0.0.1`;
  assim o app não fica acessível de outras máquinas, a menos que você mude isso de propósito.
* O CORS é limitado às origens locais do frontend (`FORECASTLAB_CORS`).
* Os arquivos carregados têm limite de tamanho (`FORECASTLAB_MAX_UPLOAD_MB`, padrão de 50 MB) e de tipo (`.xlsx`,
  `.csv`, `.parquet`) e são lidos no servidor; os arquivos nunca são executados.
* Não existe tela de configurações e a API não expõe caminhos de arquivos locais (como o caminho do banco DuckDB)
  nem segredos; o status da IA informa apenas o endereço do Ollama, o modelo configurado e se ele está disponível.
* O LLM local (Ollama) recebe apenas fatos agregados e já calculados; uma trava de fundamentação numérica rejeita
  qualquer número inventado pelo modelo.
* **Não há autenticação** neste MVP — não o publique em um servidor público com dados reais. Veja
  [docs/security.md](docs/security.md) para o plano enterprise (Entra ID, RBAC, gestão de segredos, logs de
  auditoria).

## Usando seus próprios dados

Se você carregar dados reais da empresa, mantenha-os locais: não faça commit deles (guarde os arquivos fora do
repositório ou em uma pasta ignorada pelo git) e não exponha as portas.

## Como reportar uma vulnerabilidade

Abra uma issue no GitHub **sem** detalhes sensíveis e peça um canal privado, ou fale com o autor pelo
[LinkedIn](https://www.linkedin.com/in/wallisonsampaio).

---

ForecastLab · Desenvolvido por Wallison Sampaio — Especialista em Inteligência Comercial | Supply Chain | Data & AI
Analytics

*Developed by Wallison Sampaio — Commercial Intelligence | Supply Chain | Data & AI Analytics Specialist*
