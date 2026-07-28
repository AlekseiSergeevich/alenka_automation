import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, LogOut, Store } from "lucide-react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/cn";
import { isAuthUiDisabled } from "@/lib/authUi";

export function AppShell() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const logoutMutation = useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      queryClient.clear();
      navigate(isAuthUiDisabled() ? "/stores" : "/login", { replace: true });
    },
  });

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-screen-2xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-8">
            <Link to="/stores" className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-[#f8bf30] text-black">
                <span className="text-sm font-bold">А</span>
              </span>
              <span className="text-sm font-semibold tracking-tight">
                Сладости.Экспресс
              </span>
            </Link>
            <nav className="flex flex-wrap items-center gap-1">
              <NavItem to="/stores" icon={<Store className="h-4 w-4" />}>
                Магазины
              </NavItem>
              <NavItem to="/order-blank" icon={<FileSpreadsheet className="h-4 w-4" />}>
                Бланк заказа
              </NavItem>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {user ? (
              <div className="hidden text-right sm:block">
                <p className="text-sm font-medium leading-tight">
                  {user.username}
                </p>
                <p className="text-xs leading-tight text-muted-foreground">
                  {user.role}
                </p>
              </div>
            ) : null}
            {isAuthUiDisabled() ? null : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => logoutMutation.mutate()}
                loading={logoutMutation.isPending}
              >
                <LogOut className="h-4 w-4" />
                Выйти
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
        <Outlet />
      </main>
    </div>
  );
}

interface NavItemProps {
  to: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

function NavItem({ to, icon, children }: NavItemProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
          isActive
            ? "bg-muted text-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )
      }
    >
      {icon}
      {children}
    </NavLink>
  );
}
