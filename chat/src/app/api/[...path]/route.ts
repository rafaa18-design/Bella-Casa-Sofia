import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";
const BACKEND_USER = process.env.BACKEND_USER || "admin";
const BACKEND_PASS = process.env.BACKEND_PASS || "bellacasa2026";

// In-memory token cache (per Cloud Run instance). Re-login on 401 or near expiry.
let cachedToken: string | null = null;
let cachedExp = 0;

async function getToken(): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  if (cachedToken && now < cachedExp - 60) return cachedToken;
  const res = await fetch(
    `${BACKEND_URL}/auth/login?username=${encodeURIComponent(BACKEND_USER)}&password=${encodeURIComponent(BACKEND_PASS)}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`auth/login ${res.status}`);
  const data = (await res.json()) as { access_token: string; expires_in: number };
  cachedToken = data.access_token;
  cachedExp = now + (data.expires_in || 86400);
  return cachedToken!;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

async function proxy(request: NextRequest, params: { path: string[] }) {
  const path = params.path.join("/");
  const search = request.nextUrl.search;
  const url = `${BACKEND_URL}/${path}${search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");

  // Always inject a fresh server-side token. The client doesn't authenticate.
  const isLoginPath = path.startsWith("auth/login");
  if (!isLoginPath) {
    try {
      const token = await getToken();
      headers.set("authorization", `Bearer ${token}`);
    } catch (err) {
      return NextResponse.json(
        { error: "Auth failed", detail: String(err) },
        { status: 502 }
      );
    }
  }

  const init: RequestInit = {
    method: request.method,
    headers,
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    const ct = request.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      init.body = await request.text();
    } else {
      init.body = await request.arrayBuffer();
    }
  }

  try {
    let res = await fetch(url, init);
    // On 401, force-refresh the token once and retry
    if (res.status === 401 && !isLoginPath) {
      cachedToken = null;
      cachedExp = 0;
      const token = await getToken();
      headers.set("authorization", `Bearer ${token}`);
      res = await fetch(url, { ...init, headers });
    }
    const body = await res.arrayBuffer();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") || "application/json",
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Backend unavailable", detail: String(err) },
      { status: 502 }
    );
  }
}
