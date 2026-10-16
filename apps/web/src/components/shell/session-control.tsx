"use client";

import type { SessionInfo as Session } from "@yield-guardian/contracts";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import dynamic from "next/dynamic";
import { type ComponentProps, useState } from "react";

import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import { cn } from "@/lib/utils";

export const ROLE_LABEL = { visitor: "Visitor", engineer: "Engineer", admin: "Admin" } as const;

// The signed-in menu and the admin dialog (Radix, focus trap, form) load when first used.
const loadMenus = () => import("./session-menus");
const AdminLoginDialog = dynamic(() => loadMenus().then((m) => m.AdminLoginDialog), { ssr: false });
const SessionMenu = dynamic(() => loadMenus().then((m) => m.SessionMenu), { ssr: false });

/** The signed-in button: who you are, opening the session menu. */
export function SessionButton({
  session,
  className,
  ...props
}: { session: Session } & ComponentProps<typeof Button>) {
  return (
    <Button
      size="sm"
      variant="outline"
      className={cn("group/session gap-2 pr-2.5 pl-3 data-[state=open]:bg-surface-2", className)}
      {...props}
    >
      <span className="relative flex size-2" aria-hidden="true">
        <span className="absolute inset-0 rounded-full bg-pass" />
        <span className="absolute -inset-1 rounded-full bg-pass-wash" />
      </span>
      <span>{session.display_name ?? ROLE_LABEL[session.role]}</span>
      <span className="text-ink-3">{session.display_name ? ROLE_LABEL[session.role] : null}</span>
      <ChevronDown
        className="size-3.5 text-ink-3 transition-transform duration-(--dur-3) ease-spring group-data-[state=open]/session:rotate-180"
        aria-hidden="true"
      />
    </Button>
  );
}

export function SessionControl({
  className,
  stacked = false,
}: {
  className?: string;
  stacked?: boolean;
}) {
  const api = useApi();
  const { session, loading } = useSession();
  const meta = useQuery(q.meta(api));
  const guest = useStartGuestSession();
  const [loginOpen, setLoginOpen] = useState(false);
  const [loginUsed, setLoginUsed] = useState(false);
  // The menu is controlled from here: its state outlives the menu itself, which unmounts when
  // the session changes, so it never reopens by itself when it mounts again.
  const [menuLoaded, setMenuLoaded] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const adminLogin = meta.data?.features.admin_login ?? false;

  if (loading) {
    return (
      <div className={cn("h-8 w-36 rounded-full bg-surface-2", className)} aria-hidden="true" />
    );
  }

  if (session.role === "visitor") {
    return (
      <div
        className={cn(
          "flex items-center gap-1",
          stacked && "flex-col items-stretch gap-2",
          className,
        )}
      >
        <Button size="sm" onClick={() => guest.mutate()} disabled={guest.isPending}>
          {guest.isPending ? "Starting session…" : "Try as engineer"}
        </Button>
        {adminLogin ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setLoginUsed(true);
              setLoginOpen(true);
            }}
            onPointerEnter={() => void loadMenus()}
            onFocus={() => void loadMenus()}
          >
            Admin sign-in
          </Button>
        ) : null}
        {/* Stays mounted once used, so it can animate out when it closes. */}
        {loginUsed ? <AdminLoginDialog open={loginOpen} onOpenChange={setLoginOpen} /> : null}
      </div>
    );
  }

  if (menuLoaded) {
    return (
      <SessionMenu
        session={session}
        className={className}
        open={menuOpen}
        onOpenChange={setMenuOpen}
      />
    );
  }
  return (
    <SessionButton
      session={session}
      className={className}
      aria-haspopup="menu"
      aria-expanded={false}
      onClick={() => {
        setMenuLoaded(true);
        setMenuOpen(true);
      }}
      onPointerEnter={() => void loadMenus()}
      onFocus={() => void loadMenus()}
    />
  );
}
