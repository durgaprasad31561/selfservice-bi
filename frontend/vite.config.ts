/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend so the browser talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // keep the big chart library and React in their own cacheable chunks
        manualChunks: {
          charts: ["recharts"],
          react: ["react", "react-dom", "react-router-dom", "@tanstack/react-query", "axios"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
