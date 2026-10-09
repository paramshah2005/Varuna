import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  optimizeDeps: {
    include: [
      "react-dom/client",
      "gsap",
      "lucide-react",
      "@radix-ui/react-dialog",
      "@radix-ui/react-switch",
      "class-variance-authority",
      "clsx",
      "tailwind-merge",
      "recharts",
      "@react-three/fiber",
      "@react-three/drei",
      "@react-three/drei/core/OrthographicCamera.js",
    ],
  },
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
