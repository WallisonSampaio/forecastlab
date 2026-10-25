# Optional client logo (white-label, local only)

ForecastLab can show a client / prospect logo next to its own brand ("Prepared for …") for **private demos**.

1. Copy the logo file into this folder, e.g. `frontend/public/brand/client-logo.png`
   (every file here except this README is ignored by git).
2. Create `frontend/.env.local` (also ignored by git):

   ```bash
   VITE_CLIENT_LOGO_URL=/brand/client-logo.png
   VITE_CLIENT_NAME=Client name
   ```

3. Restart the frontend (`vite`). The logo appears in the sidebar and on the landing page.

Only use logos you are authorized to use, and keep third-party trademarks out of the public repository and of
public screenshots unless you have permission.
