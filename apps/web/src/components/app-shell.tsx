"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

interface NavItem {
    href: string;
    label: string;
    matchPrefix: string;
}

const NAV_ITEMS: NavItem[] = [
    { href: "/dashboard", label: "Dashboard", matchPrefix: "/dashboard" },
    { href: "/connect", label: "Connect", matchPrefix: "/connect" },
    { href: "/competitors", label: "Competitors", matchPrefix: "/competitors" },
    { href: "/research", label: "Research", matchPrefix: "/research" },
    { href: "/audit/new", label: "Audit Workspace", matchPrefix: "/audit" },
    { href: "/report/latest", label: "Latest Report", matchPrefix: "/report" },
];

function isActive(pathname: string, item: NavItem): boolean {
    return pathname === item.href || pathname.startsWith(item.matchPrefix);
}

export function StudioTopNav({ rightSlot }: { rightSlot?: ReactNode }) {
    const pathname = usePathname();
    const [mobileOpen, setMobileOpen] = useState(false);

    useEffect(() => {
        setMobileOpen(false);
    }, [pathname]);

    return (
        <header className="border-b border-[#dfdfdf] bg-[#fafafa]">
            <div className="flex h-16 items-center justify-between px-4 md:px-6">
                <div className="flex items-center gap-4">
                    <Link href="/" className="text-lg font-bold text-[#1f1f1f]">
                        SPC Studio
                    </Link>
                    <nav className="hidden items-center gap-4 text-sm text-[#6b6b6b] md:flex">
                        {NAV_ITEMS.map((item) => (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={isActive(pathname, item) ? "font-medium text-[#1b1b1b]" : "hover:text-[#151515]"}
                            >
                                {item.label}
                            </Link>
                        ))}
                    </nav>
                </div>

                <div className="flex items-center gap-2">
                    {rightSlot}
                    <button
                        type="button"
                        onClick={() => setMobileOpen((prev) => !prev)}
                        className="inline-flex rounded-lg border border-[#d5d5d5] bg-white px-3 py-1.5 text-xs text-[#444] md:hidden"
                        aria-expanded={mobileOpen}
                        aria-label="Toggle navigation"
                    >
                        Menu
                    </button>
                </div>
            </div>

            {mobileOpen && (
                <div className="border-t border-[#e3e3e3] bg-[#fafafa] px-4 py-3 md:hidden">
                    <nav className="flex flex-col gap-1">
                        {NAV_ITEMS.map((item) => (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`rounded-lg px-3 py-2 text-sm ${
                                    isActive(pathname, item)
                                        ? "bg-white font-medium text-[#1b1b1b] border border-[#dddddd]"
                                        : "text-[#555] hover:bg-white/80"
                                }`}
                            >
                                {item.label}
                            </Link>
                        ))}
                    </nav>
                </div>
            )}
        </header>
    );
}

export function StudioAppShell({
    children,
    rightSlot,
}: {
    children: ReactNode;
    rightSlot?: ReactNode;
}) {
    return (
        <div className="min-h-screen bg-[#e8e8e8] px-3 py-4 md:px-8 md:py-6">
            <div className="mx-auto w-full max-w-[1500px] overflow-hidden rounded-[30px] border border-[#d8d8d8] bg-[#f5f5f5] shadow-[0_35px_90px_rgba(0,0,0,0.12)]">
                <StudioTopNav rightSlot={rightSlot} />
                {children}
            </div>
        </div>
    );
}
