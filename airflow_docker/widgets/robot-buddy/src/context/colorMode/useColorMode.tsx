import { useTheme } from "next-themes";

export const useColorMode = () => {
  const { resolvedTheme, setTheme, theme } = useTheme();

  return {
    colorMode: resolvedTheme as "dark" | "light" | undefined,
    selectedTheme: theme as "dark" | "light" | "system" | undefined,
    setColorMode: setTheme,
  };
};
