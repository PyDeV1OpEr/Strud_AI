import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { ChatStoreProvider } from "@/hooks/use-chats";
import "@/styles/globals.css";
import "@/components/ui/animations.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Strud AI — Biology Assistant",
  description:
    "A premium AI-powered Biology learning assistant. Ask Strud anything about Biology.",
};

export const viewport: Viewport = {
  themeColor: "#070708",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans`}>
        {/* atmospheric gradient layer */}
        <div className="atmosphere" aria-hidden="true" />
        <ChatStoreProvider>{children}</ChatStoreProvider>
      </body>
    </html>
  );
}
