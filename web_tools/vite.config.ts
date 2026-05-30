import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const rootDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  appType: "mpa",
  root: "src",
  base: "./",
  build: {
    outDir: "../dist",
    emptyOutDir: false,
    rollupOptions: {
      input: {
        design_editor: resolve(rootDir, "src/design_editor/index.html"),
        elevenlabs: resolve(rootDir, "src/elevenlabs/index.html"),
        elevenlabs_assist: resolve(rootDir, "src/elevenlabs_assist/index.html")
      }
    }
  }
});
