"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApi } from "@/lib/api/context";
import { ApiError, describeError } from "@/lib/api/errors";
import { q } from "@/lib/api/queries";
import { useLogin, useLogout, useSession, useStartGuestSession } from "@/lib/api/session";
import { cn } from "@/lib/utils";

const ROLE_LABEL = { visitor: "Visitor", engineer: "Engineer", admin: "Admin" } as const;

export function SessionControl({ className, stacked = false }: { className?: string; stacked?: boolean }) {
  const api = useApi();
  const { session, loading } = useSession();
  const meta = useQuery(q.meta(api));
  const guest = useStartGuestSession();
  const logout = useLogout();
  const [loginOpen, setLoginOpen] = useState(false);
  const adminLogin = meta.data?.features.admin_login ?? false;

  if (loading) {
    return <div className={cn("h-8 w-36 rounded-md bg-die-2", className)} aria-hidden="true" />;
  }

  if (session.role === "visitor") {
    return (
      <div className={cn("flex items-center gap-1", stacked && "flex-col items-stretch gap-2", className)}>
        <Button
          size="sm"
          variant="outline"
          onClick={() => guest.mutate()}
          disabled={guest.isPending}
          className="border-hairline-strong"
        >
          {guest.isPending ? "Starting session…" : "Try as engineer"}
        </Button>
        {adminLogin ? (
          <Button size="sm" variant="ghost" onClick={() => setLoginOpen(true)} className="text-ink-2">
            Admin sign-in
          </Button>
        ) : null}
        <AdminLoginDialog open={loginOpen} onOpenChange={setLoginOpen} />
      </div>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="ghost" className={cn("gap-1.5", className)}>
          <span className="size-1.5 rounded-full bg-pass" aria-hidden="true" />
          <span>{session.display_name ?? ROLE_LABEL[session.role]}</span>
          <span className="text-ink-3">{session.display_name ? ROLE_LABEL[session.role] : null}</span>
          <ChevronDown className="size-3.5 text-ink-3" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="font-normal text-ink-2">
          Signed in as {ROLE_LABEL[session.role].toLowerCase()}
          {session.expires_at ? (
            <span className="mt-0.5 block text-xs text-ink-3">
              Session ends {new Date(session.expires_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
            </span>
          ) : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => logout.mutate()}>Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function AdminLoginDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate(
      { username, password },
      {
        onSuccess: () => {
          setPassword("");
          onOpenChange(false);
        },
      },
    );
  };

  const error = login.error ? describeError(login.error) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <form onSubmit={submit} className="grid grid-cols-[minmax(0,1fr)] gap-4">
          <DialogHeader>
            <DialogTitle>Admin sign-in</DialogTitle>
            <DialogDescription>
              Admins assign models to roles. Engineers do not need an account: use “Try as engineer”.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-2">
            <Label htmlFor="admin-username">Username</Label>
            <Input
              id="admin-username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-2">
            <Label htmlFor="admin-password">Password</Label>
            <Input
              id="admin-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error ? (
            <p role="alert" className="text-sm text-fail">
              {login.error instanceof ApiError && login.error.status === 401
                ? "The username or password is not right."
                : error.detail}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={login.isPending}>
              {login.isPending ? "Signing in…" : "Sign in"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
