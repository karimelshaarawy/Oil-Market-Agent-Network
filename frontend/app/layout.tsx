import type { Metadata } from "next";
import { Inter, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { ThemeProvider } from "@/components/ThemeProvider";

const inter = Inter({ variable: "--font-sans", subsets: ["latin"], display: "swap" });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Econ Agent Simulation",
  description: "LLM-powered oil market simulation dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${geistMono.variable}`}>
      <body className="h-screen bg-background text-foreground flex relative overflow-hidden">
        <ThemeProvider>
        {/* Ambient background — light theme only (soft tinted glows + faint grid) */}
        <div className="block dark:hidden absolute inset-0 overflow-hidden pointer-events-none z-0">
          {/* Soft cool pastel glow spots that blend cleanly into white */}
          <div className="absolute -top-[20%] -left-[10%] w-[60%] h-[60%] rounded-full bg-sky-200/40 blur-[120px] animate-pulse-slow" />
          <div className="absolute -bottom-[15%] -right-[10%] w-[75%] h-[75%] rounded-full bg-indigo-200/35 blur-[140px] animate-pulse-slower" />
          <div className="absolute top-[20%] right-[15%] w-[45%] h-[45%] rounded-full bg-cyan-200/30 blur-[110px] animate-pulse-slow" />
          <div className="absolute bottom-[10%] left-[20%] w-[50%] h-[50%] rounded-full bg-amber-100/40 blur-[130px] animate-pulse-slower" />

          {/* Faint dark grid overlay */}
          <div
            className="absolute inset-0 bg-[linear-gradient(to_right,#00000007_1px,transparent_1px),linear-gradient(to_bottom,#00000007_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_70%_70%_at_50%_35%,#000_70%,transparent_100%)]"
          />
        </div>

        {/* Premium ambient light and background effects — dark theme only */}
        <div className="hidden dark:block absolute inset-0 overflow-hidden pointer-events-none z-0">
          {/* Dynamic blurred glow spots */}
          <div className="absolute -top-[20%] -left-[10%] w-[60%] h-[60%] rounded-full bg-amber-500/8 blur-[120px] animate-pulse-slow" />
          <div className="absolute -bottom-[15%] -right-[10%] w-[75%] h-[75%] rounded-full bg-indigo-500/7 blur-[140px] animate-pulse-slower" />
          <div className="absolute top-[20%] right-[15%] w-[45%] h-[45%] rounded-full bg-teal-500/4 blur-[110px] animate-pulse-slow" />
          <div className="absolute bottom-[10%] left-[20%] w-[50%] h-[50%] rounded-full bg-purple-500/3 blur-[130px] animate-pulse-slower" />

          {/* High-tech dashboard grid overlay */}
          <div 
            className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff04_1px,transparent_1px),linear-gradient(to_bottom,#ffffff04_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_70%_70%_at_50%_35%,#000_70%,transparent_100%)] opacity-90" 
          />
        </div>

        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6 relative z-10">
          {children}
        </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
