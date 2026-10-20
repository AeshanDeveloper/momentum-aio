import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@config": path.resolve(__dirname, "./src/config"),
      "@shared": path.resolve(__dirname, "./src/shared"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 3000,
  },
});
