import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Cổng 5173 phải khớp CORS_ORIGINS (backend) và "Authorized JavaScript origins" của Google OAuth.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true },
});
