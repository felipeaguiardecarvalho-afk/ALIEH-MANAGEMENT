import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const localNodeModules = path.join(__dirname, "node_modules");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Acesso por 127.0.0.1 ou IP da LAN (HMR / _next em dev).
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {
    root: __dirname,
  },
  // Monorepo: a raiz do repo também declara `next`; se o Webpack resolver primeiro o
  // `node_modules` da raiz (instalação incompleta ou outra versão), faltam ficheiros
  // como `dist/api/headers.js`. Priorizar sempre os pacotes de `web-prototype/`.
  webpack: (config) => {
    const mods = Array.isArray(config.resolve.modules)
      ? config.resolve.modules
      : ["node_modules"];
    const rest = mods.filter(
      (m) => path.resolve(String(m)) !== path.resolve(localNodeModules),
    );
    config.resolve.modules = [localNodeModules, ...rest];
    return config;
  },
};

export default nextConfig;
