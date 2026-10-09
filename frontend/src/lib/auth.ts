const client = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;
const domain = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
const redirect =
  import.meta.env.VITE_REDIRECT_URI ||
  (typeof window !== "undefined" ? window.location.origin : "");
export const cloudMode = Boolean(import.meta.env.VITE_API_URL);

export function accessToken() {
  if (typeof sessionStorage === "undefined") return null;
  const expires = Number(sessionStorage.getItem("aqua_expires") || 0);
  return Date.now() < expires ? sessionStorage.getItem("aqua_token") : null;
}
let refreshInFlight: Promise<string | null> | null = null;
export async function ensureAccessToken() {
  const token = accessToken();
  if (token || !cloudMode) return token;
  const refresh = sessionStorage.getItem("aqua_refresh");
  if (!refresh || !domain || !client) return null;
  if (!refreshInFlight)
    refreshInFlight = (async () => {
      const response = await fetch(`${domain}/oauth2/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "refresh_token",
          client_id: client,
          refresh_token: refresh,
        }),
      });
      if (!response.ok) {
        sessionStorage.removeItem("aqua_refresh");
        return null;
      }
      const body = await response.json();
      sessionStorage.setItem("aqua_token", body.access_token);
      sessionStorage.setItem(
        "aqua_expires",
        String(Date.now() + body.expires_in * 1000 - 30000),
      );
      return body.access_token as string;
    })().finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

function base64Url(bytes: Uint8Array) {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

export async function login() {
  if (!client || !domain)
    throw new Error("Cognito environment configuration is missing");
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(32)));
  const state = crypto.randomUUID();
  sessionStorage.setItem("aqua_verifier", verifier);
  sessionStorage.setItem("aqua_state", state);
  const challenge = base64Url(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)),
    ),
  );
  const url = new URL(`${domain}/oauth2/authorize`);
  url.search = new URLSearchParams({
    client_id: client,
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: redirect,
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  }).toString();
  window.location.assign(url);
}

export async function finishLogin() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  if (!code) return;
  if (params.get("state") !== sessionStorage.getItem("aqua_state"))
    throw new Error("Login state mismatch");
  const verifier = sessionStorage.getItem("aqua_verifier");
  if (!client || !domain || !verifier) throw new Error("Login session missing");
  const response = await fetch(`${domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: client,
      code,
      redirect_uri: redirect,
      code_verifier: verifier,
    }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error("Cognito token exchange failed");
  if (body.refresh_token)
    sessionStorage.setItem("aqua_refresh", body.refresh_token);
  sessionStorage.setItem("aqua_token", body.access_token);
  sessionStorage.setItem(
    "aqua_expires",
    String(Date.now() + body.expires_in * 1000 - 30000),
  );
  sessionStorage.removeItem("aqua_verifier");
  sessionStorage.removeItem("aqua_state");
  history.replaceState(null, "", window.location.pathname);
}

export function logout() {
  sessionStorage.removeItem("aqua_refresh");
  sessionStorage.removeItem("aqua_token");
  sessionStorage.removeItem("aqua_expires");
  if (domain && client)
    window.location.assign(
      `${domain}/logout?client_id=${encodeURIComponent(client)}&logout_uri=${encodeURIComponent(redirect)}`,
    );
  else window.location.reload();
}
