import { ChakraProvider } from "@chakra-ui/react";
import { FC } from "react";

import { ColorModeProvider } from "src/context/colorMode";
import { HomePage } from "src/pages/HomePage";

import { localSystem } from "./theme";

/**
 * Main plugin component
 */
const PluginComponent: FC = () => {

  // Use the globalChakraUISystem provided by the Airflow Core UI,
  // so the plugin has a consistent theming with the host Airflow UI,
  // fallback to localSystem for local development.
  const system = (globalThis.ChakraUISystem) ?? localSystem;

  return (
    <ChakraProvider value={system}>
      <ColorModeProvider>
          <HomePage />
      </ColorModeProvider>
    </ChakraProvider>
  );
};

export default PluginComponent;
