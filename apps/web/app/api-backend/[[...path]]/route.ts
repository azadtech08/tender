/**
 * Proxy route for backend API requests.
 *
 * This route handles requests to /api-backend/* and forwards them to the FastAPI backend
 * while preserving important headers like Authorization.
 *
 * Browser calls /api-backend/api/jobs
 *   ↓
 * This route receives it as /api-backend/api/jobs
 *   ↓
 * Forwards to http://api:8000/api/jobs with Authorization header
 */

import { NextRequest, NextResponse } from "next/server";

export async function handleRequest(
  req: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  try {
    const resolvedParams = await params;
    const pathArray = resolvedParams.path || [];
    const pathString = pathArray.join("/");

    // Build the backend URL
    const backendUrl =
      (process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") +
      "/" +
      pathString +
      (req.nextUrl.search ? req.nextUrl.search : "");

    // Copy headers from the incoming request
    const headers = new Headers();
    req.headers.forEach((value, key) => {
      // Skip headers that shouldn't be forwarded
      if (key.toLowerCase() === "host" || key.toLowerCase() === "connection") {
        return;
      }
      headers.set(key, value);
    });

    // Forward the request to the backend
    const response = await fetch(backendUrl, {
      method: req.method,
      headers,
      body: req.method !== "GET" && req.method !== "HEAD" ? await req.text() : undefined,
    });

    // Create a response with the same status and content
    const responseBody = await response.text();
    const nextResponse = new NextResponse(responseBody, {
      status: response.status,
      statusText: response.statusText,
    });

    // Forward response headers
    response.headers.forEach((value, key) => {
      // Skip headers that can cause issues
      if (key.toLowerCase() !== "content-encoding") {
        nextResponse.headers.set(key, value);
      }
    });

    return nextResponse;
  } catch (error) {
    console.error("[API Proxy] Error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}

// Export handlers for all HTTP methods
export const GET = handleRequest;
export const POST = handleRequest;
export const PUT = handleRequest;
export const PATCH = handleRequest;
export const DELETE = handleRequest;
export const HEAD = handleRequest;
export const OPTIONS = handleRequest;
