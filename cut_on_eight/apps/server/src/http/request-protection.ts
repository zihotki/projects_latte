import type { FastifyInstance, FastifyRequest } from 'fastify';
import { ApiRouteError } from './api-error.js';

interface LocalAuthority {
  readonly hostname: '127.0.0.1' | 'localhost' | '::1';
  readonly port: number | null;
}

const localHostPattern = /^(localhost|127\.0\.0\.1)(?::([0-9]+))?$/i;
const ipv6LoopbackPattern = /^\[::1\](?::([0-9]+))?$/;
const originPattern = /^http:\/\/([^/?#]+)$/i;
const fetchSites = new Set(['cross-site', 'none', 'same-origin', 'same-site']);

function parsePort(value: string | undefined): number | null {
  if (value === undefined) return null;
  const port = Number(value);
  return Number.isInteger(port) && port >= 0 && port <= 65_535
    ? port
    : Number.NaN;
}

function parseLocalAuthority(value: string): LocalAuthority | null {
  if (value !== value.trim()) return null;

  const ipv6 = ipv6LoopbackPattern.exec(value);
  if (ipv6 !== null) {
    const port = parsePort(ipv6[1]);
    return Number.isNaN(port) ? null : { hostname: '::1', port };
  }

  const local = localHostPattern.exec(value);
  if (local === null) return null;
  const hostname = local[1];
  if (hostname === undefined) return null;
  const port = parsePort(local[2]);
  if (Number.isNaN(port)) return null;

  return {
    hostname: hostname.toLowerCase() as LocalAuthority['hostname'],
    port,
  };
}

function requireLocalHost(request: FastifyRequest): LocalAuthority {
  const value = request.headers.host;
  const authority =
    typeof value === 'string' ? parseLocalAuthority(value) : null;
  if (authority !== null) return authority;

  throw new ApiRouteError(
    value === undefined ? 400 : 403,
    value === undefined ? 'invalid_request_host' : 'forbidden_request_host',
    value === undefined
      ? 'The request Host header is invalid.'
      : 'The request Host is not allowed.',
    false,
  );
}

interface ParsedOrigin {
  readonly localAuthority: LocalAuthority | null;
}

function parseOrigin(value: string): ParsedOrigin | null {
  if (value !== value.trim()) return null;
  const match = originPattern.exec(value);
  if (match === null) return null;
  const authority = match[1];
  if (authority === undefined) return null;

  try {
    const parsed = new URL(value);
    if (
      parsed.protocol !== 'http:' ||
      parsed.username !== '' ||
      parsed.password !== ''
    ) {
      return null;
    }
  } catch {
    return null;
  }

  return { localAuthority: parseLocalAuthority(authority) };
}

function effectivePort(authority: LocalAuthority): number {
  return authority.port ?? 80;
}

function isAllowedOrigin(
  origin: LocalAuthority,
  requestHost: LocalAuthority,
): boolean {
  const isViteOrigin =
    origin.port === 5173 &&
    (origin.hostname === '127.0.0.1' || origin.hostname === 'localhost');
  const isBackendOrigin =
    origin.hostname === requestHost.hostname &&
    effectivePort(origin) === effectivePort(requestHost);
  return isViteOrigin || isBackendOrigin;
}

function protectBrowserRequest(
  request: FastifyRequest,
  requestHost: LocalAuthority,
): void {
  const originValue = request.headers.origin;
  const fetchSiteValue = request.headers['sec-fetch-site'];

  if (originValue !== undefined) {
    const origin = parseOrigin(originValue);
    if (origin === null) {
      throw new ApiRouteError(
        400,
        'invalid_request_origin',
        'The request Origin header is invalid.',
        false,
      );
    }
    if (
      origin.localAuthority !== null &&
      isAllowedOrigin(origin.localAuthority, requestHost)
    ) {
      return;
    }

    throw new ApiRouteError(
      403,
      'forbidden_request_origin',
      'The request Origin is not allowed.',
      false,
    );
  }

  if (fetchSiteValue === undefined) return;
  const fetchSite = fetchSiteValue.toLowerCase();
  if (!fetchSites.has(fetchSite)) {
    throw new ApiRouteError(
      400,
      'invalid_fetch_site',
      'The request browser provenance header is invalid.',
      false,
    );
  }
  if (fetchSite === 'cross-site') {
    throw new ApiRouteError(
      403,
      'forbidden_request_origin',
      'Cross-site browser requests are not allowed.',
      false,
    );
  }
}

function isApiRequest(url: string): boolean {
  return url === '/api' || url.startsWith('/api/') || url.startsWith('/api?');
}

export function installApiRequestProtection(app: FastifyInstance): void {
  app.addHook('onRequest', async (request) => {
    if (!isApiRequest(request.url)) return;
    const requestHost = requireLocalHost(request);
    protectBrowserRequest(request, requestHost);
  });
}
