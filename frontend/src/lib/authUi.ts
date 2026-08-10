/** When true, SPA skips the login gate (use with AUTH_ENABLED=false on the API). */
export function isAuthUiDisabled(): boolean {
  return import.meta.env.VITE_DISABLE_AUTH === "true";
}
