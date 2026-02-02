import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "@/components/providers/theme-provider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "IC Autopilot - Investment Committee Automation",
  description: "Enterprise-grade Investment Committee workflow automation with real-time progress tracking",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} ${jetbrainsMono.variable} font-sans`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          {children}
          <footer className="fixed bottom-2 right-4 text-xs text-muted-foreground/60 z-50">
            Built by Innovation Hub Istanbul | <a href="mailto:ozgurguler@microsoft.com" className="hover:text-muted-foreground">Ozgur Guler</a>
          </footer>
        </ThemeProvider>
      </body>
    </html>
  );
}
