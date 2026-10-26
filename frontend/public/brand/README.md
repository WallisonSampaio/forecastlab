# Logo opcional do cliente (white-label, somente local)

O ForecastLab pode exibir o logo de um cliente ou prospect ao lado da própria marca ("Preparado para …") em
**demonstrações privadas**.

1. Copie o arquivo do logo para esta pasta, por exemplo `frontend/public/brand/client-logo.png`
   (todos os arquivos desta pasta, exceto este README, são ignorados pelo git).
2. Crie o arquivo `frontend/.env.local` (também ignorado pelo git):

   ```bash
   VITE_CLIENT_LOGO_URL=/brand/client-logo.png
   VITE_CLIENT_NAME=Nome do cliente
   ```

3. Reinicie o frontend (`vite`). O logo aparece no topo da sidebar flutuante, logo abaixo da marca ForecastLab
   ("Preparado para"), e no cabeçalho da página inicial, ao lado do logo do ForecastLab. Se o arquivo não existir,
   o espaço do logo simplesmente fica oculto.

Dica: logos quadrados com muita margem são recortados automaticamente para caber no espaço horizontal; prefira um
arquivo PNG ou SVG com fundo transparente.

Use somente logos que você tem autorização para usar e mantenha marcas de terceiros fora do repositório público e
de capturas de tela públicas, a menos que tenha permissão.
