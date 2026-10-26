# Segurança (versão enterprise futura)

> ForecastLab · Desenvolvido por Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

O MVP de portfólio é uma aplicação local, de um único usuário, com dados sintéticos. Ele não tem autenticação, de
propósito. Este documento resume o que já existe hoje e lista o que uma implantação enterprise acrescenta.

## Hoje (MVP local)

* Nenhuma credencial, token ou chave de API é necessária ou armazenada.
* A API e as portas do Docker escutam apenas em `127.0.0.1`; o CORS é restrito às origens locais do frontend.
* **Não existe tela de Configurações** e a API não expõe caminhos de arquivos locais (como o caminho do banco
  DuckDB) nem segredos; o status da IA informa apenas o endereço do Ollama, o modelo configurado e se ele está
  disponível.
* Carga de arquivos com limite de tamanho e de tipo, lida apenas no servidor; os arquivos nunca são executados.
* O LLM local recebe somente fatos agregados já calculados, e a trava de fundamentação numérica rejeita números
  inventados.
* O repositório contém apenas dados sintéticos; logos de clientes (white-label) ficam somente na máquina local.

## Plano enterprise

| Tema | Plano |
|---|---|
| Autenticação | OIDC com Microsoft Entra ID; dependência do FastAPI validando JWTs; MSAL no frontend |
| Autorização / RBAC | Papéis: Leitor, Planejador de Demanda, Comercial (ajustes comerciais), Líder de S&OP (aprovação), Administrador. Escopo por linha (região/canal/cliente) aplicado na camada de filtros do contexto de planejamento |
| Gestão de segredos | Azure Key Vault / AWS Secrets Manager; nenhum segredo nas imagens; identidades gerenciadas para banco e LLM |
| Logs de auditoria | Tabela de auditoria somente de inserção para cargas de arquivos, ajustes comerciais, mudanças de cenário, ativação de execuções e aprovações (quem/quando/o quê/antes/depois) |
| Criptografia | TLS em todas as conexões; criptografia em repouso para banco e data lake; chaves gerenciadas pelo cliente quando exigido |
| Proteção de dados | Sem dados pessoais por design (contas de clientes, não pessoas físicas), alinhado à LGPD; retenção por versão da base |
| Segurança do LLM | Endpoint de LLM corporativo dentro do tenant; prompts só com fatos agregados; trava de fundamentação numérica mantida; nenhum treinamento com dados da empresa |
| Cadeia de suprimentos de software | Dependências fixadas, SCA no CI, imagens assinadas |
| Proteção na carga de arquivos | Limite de tamanho (`FORECASTLAB_MAX_UPLOAD_MB`), lista de tipos permitidos, leitura apenas no servidor |
