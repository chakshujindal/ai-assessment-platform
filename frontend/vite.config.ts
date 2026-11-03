import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs on :8000; Vite proxies /api so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
