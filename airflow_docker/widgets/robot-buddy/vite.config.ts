import react from "@vitejs/plugin-react-swc";
import { resolve } from "node:path";
import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";
import dts from "vite-plugin-dts";
import { defineConfig } from "vitest/config";

// https://vitejs.dev/config/
export default defineConfig(({ command }) => {
  const isLibraryBuild = command === 'build';

  return {
    base: "./",
    build: isLibraryBuild ? {
      chunkSizeWarningLimit: 1600,
      lib: {
        entry: resolve("src", "main.tsx"),
        fileName: 'main',
        formats: ['umd'],
        name: 'AirflowPlugin',
      },
      rollupOptions: {
        external: ["react", "react-dom", "react-router-dom", "react/jsx-runtime"],
        output: {
          globals: {
            react: "React",
            "react-dom": "ReactDOM",
            "react-router-dom": "ReactRouterDOM",
            "react/jsx-runtime": "ReactJSXRuntime",
          },
        },
      },
    } : {
      // Development build configuration
      chunkSizeWarningLimit: 1600
    },
    define: {
      global: "globalThis",
      "process.env": "{}",
      // Define process.env for browser compatibility
      "process.env.NODE_ENV": JSON.stringify("production"),
    },
    plugins: [
      react(),
      cssInjectedByJsPlugin(),
      ...(isLibraryBuild ? [dts({
        include: ["src/main.tsx"],
        insertTypesEntry: true,
        outDir: "dist"
      })] : [])
    ],
    resolve: { alias: { src: "/src" } },
    server: {
      cors: true, // Only used by the dev server.
    },
    test: {
      coverage: {
        include: ["src/**/*.ts", "src/**/*.tsx"],
      },
      css: true,
      environment: "happy-dom",
      globals: true,
      mockReset: true,
      passWithNoTests: true,
      restoreMocks: true,
      setupFiles: "./testsSetup.ts",
    },
  };
});
