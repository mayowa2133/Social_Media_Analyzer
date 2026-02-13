import type { Metadata } from "next";
import { Manrope } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

const manrope = Manrope({ subsets: ["latin"] });

export const metadata: Metadata = {
    title: "Social Performance Coach",
    description: "Audit your social performance and get actionable recommendations",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" className="dark">
            <body className={manrope.className}>
                <Providers>
                    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900">
                        {children}
                    </div>
                </Providers>
            </body>
        </html>
    );
}
