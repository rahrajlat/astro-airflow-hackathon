import { ThemeProvider, type ThemeProviderProps } from "next-themes";

export const ColorModeProvider = (props: ThemeProviderProps) => (
  <ThemeProvider attribute="class" disableTransitionOnChange {...props} />
);
