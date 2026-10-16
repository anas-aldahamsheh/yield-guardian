"use client";

import type { SessionInfo as Session } from "@yield-guardian/contracts";
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
import { ApiError, describeError } from "@/lib/api/errors";
import { useLogin, useLogout } from "@/lib/api/session";

import { ROLE_LABEL, SessionButton } from "./session-control";

/** The signed-in menu, loaded when it is first pressed; SessionControl holds its open state. */
export function SessionMenu({
  session,
  className,
  open,
  onOpenChange,
}: {
  session: Session;
  className?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const logout = useLogout();
  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <SessionButton session={session} className={className} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="font-[420] text-ink-2">
          Signed in as {ROLE_LABEL[session.role].toLowerCase()}
          {session.expires_at ? (
            <span className="mt-0.5 block text-xs text-ink-3">
              Session ends{" "}
              {new Date(session.expires_at).toLocaleTimeString("en-US", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          ) : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => logout.mutate()}>Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AdminLoginDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
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
              Admins assign models to roles. Engineers do not need an account: use “Try as
              engineer”.
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
