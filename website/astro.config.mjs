import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// Project site on GitHub Pages: https://beastrog.github.io/aethens/
export default defineConfig({
  site: "https://beastrog.github.io",
  base: "/aethens",
  trailingSlash: "always",
  vite: {
    plugins: [tailwindcss()],
  },
});
