import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import PluginComponent from "./main";

// Development entry point for testing the component
createRoot(document.querySelector("#root") as HTMLDivElement).render(
  <StrictMode>
    <PluginComponent />
  </StrictMode>,
);
