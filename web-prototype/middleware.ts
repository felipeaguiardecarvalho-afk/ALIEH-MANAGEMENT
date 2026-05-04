import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { verifySessionTokenEdge } from "@/lib/auth/jwt-core";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";
import { isPrototypeOpenEffective } from "@/lib/env/alieh-runtime";

function isPublicPath(pathname: string): boolean {
  if (pathname.startsWith("/_next/")) return true;
  if (pathname === "/favicon.ico") return true;
  return false;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (isPrototypeOpenEffective()) {
    return NextResponse.next();
  }

  if (pathname === "/login") {
    const secret = process.env.AUTH_SESSION_SECRET?.trim();
    const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;
    if (secret && token && (await verifySessionTokenEdge(token, secret))) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
    return NextResponse.next();
  }

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const secret = process.env.AUTH_SESSION_SECRET?.trim();
  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;

  if (!secret || !token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  const ok = await verifySessionTokenEdge(token, secret);
  if (!ok) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
