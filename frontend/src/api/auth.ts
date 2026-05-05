import { apiRequest, ApiError, clearAccessToken, setAccessToken } from "@/api/client";
import type { LoginRequestDto, LoginResponseDto, UserDto } from "@/api/types";

export interface LoginInput {
  email: string;
  password: string;
}

async function login({ email, password }: LoginInput): Promise<UserDto> {
  const credentials: LoginRequestDto = {
    username: email,
    password,
  };

  try {
    const result = await apiRequest<LoginResponseDto>("/api/v1/auth/login", {
      method: "POST",
      body: credentials,
    });
    setAccessToken(result.access_token);
    return result.user;
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status === 400 &&
      typeof error.message === "string" &&
      /authentication is disabled/i.test(error.message)
    ) {
      const me = await fetchCurrentUser();
      if (me) {
        return me;
      }
    }
    throw error;
  }
}

async function logout(): Promise<void> {
  try {
    await apiRequest<void>("/api/v1/auth/logout", { method: "POST" });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status >= 500) {
      throw error;
    }
  } finally {
    clearAccessToken();
  }
}

async function fetchCurrentUser(): Promise<UserDto | null> {
  try {
    return await apiRequest<UserDto>("/api/v1/auth/me");
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      return null;
    }
    throw error;
  }
}

export const authApi = {
  login,
  logout,
  fetchCurrentUser,
};
