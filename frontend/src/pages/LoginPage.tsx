import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { authApi, type LoginInput } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { UserDto } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/useAuth";

interface LocationState {
  from?: { pathname: string };
}

export function LoginPage() {
  const { status, setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo =
    (location.state as LocationState | null)?.from?.pathname ?? "/stores";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const loginMutation = useMutation<UserDto, Error, LoginInput>({
    mutationFn: authApi.login,
    onSuccess: (user) => {
      setUser(user);
      navigate(redirectTo, { replace: true });
    },
  });

  if (status === "authenticated") {
    return <Navigate to={redirectTo} replace />;
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    loginMutation.mutate({ email: email.trim(), password });
  };

  const errorMessage =
    loginMutation.error instanceof ApiError
      ? loginMutation.error.status === 401
        ? "Неверный email или пароль"
        : loginMutation.error.message
      : loginMutation.error?.message;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-muted/30 to-background px-4 py-12">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-2 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-[#f8bf30] text-black">
            <span className="text-xl font-bold">А</span>
          </div>
          <CardTitle className="text-2xl">Сладости.Экспресс</CardTitle>
          <CardDescription>
            Войдите, чтобы открыть аналитику остатков и продаж
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={loginMutation.isPending}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Пароль</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  disabled={loginMutation.isPending}
                  required
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full px-3 py-2 text-muted-foreground hover:bg-transparent hover:text-foreground"
                  onClick={() => setShowPassword((prev) => !prev)}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                  <span className="sr-only">
                    {showPassword ? "Скрыть пароль" : "Показать пароль"}
                  </span>
                </Button>
              </div>
            </div>
            {errorMessage ? (
              <Alert variant="destructive">
                <AlertTitle>Не удалось войти</AlertTitle>
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            ) : null}
            <Button
              type="submit"
              className="w-full"
              size="lg"
              loading={loginMutation.isPending}
              disabled={!email || !password}
            >
              Войти
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
