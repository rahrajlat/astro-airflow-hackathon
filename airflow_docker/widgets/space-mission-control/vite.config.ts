import react from "@vitejs/plugin-react-swc";
import { resolve } from "node:path";
import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";
import { defineConfig } from "vite";

export default defineConfig({base:"./",build:{chunkSizeWarningLimit:800,lib:{entry:resolve("src","main.tsx"),fileName:"mission-control-v1",formats:["umd"],name:"AirflowPlugin"},rollupOptions:{external:["react","react-dom","react/jsx-runtime"],output:{globals:{react:"React","react-dom":"ReactDOM","react/jsx-runtime":"ReactJSXRuntime"}}}},define:{global:"globalThis","process.env":"{}","process.env.NODE_ENV":JSON.stringify("production")},plugins:[react(),cssInjectedByJsPlugin()]});
