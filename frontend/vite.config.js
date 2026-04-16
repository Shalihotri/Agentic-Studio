import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// vite.config.js
export default defineConfig({
  plugins: [react()],
  server: { 
    proxy: {
      '/agent': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/workflows': 'http://localhost:8000',
    }
  }
})
