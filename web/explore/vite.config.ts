import { defineConfig } from "vite";
import { worldContent } from "./scripts/world-content.mjs";

export default defineConfig({
  base: "./",
  plugins: [worldContent()],
  build: { target: "es2022", chunkSizeWarningLimit: 1500 },
});
