import { homedir } from 'node:os';
import { isAbsolute, join } from 'node:path';

export interface ServerConfig {
  dataRoot: string;
  databaseUrl: string;
  qdrantHttpUrl: string | null;
  qdrantApiKey: string | null;
  maxUploadBytes: number;
  host: '127.0.0.1';
  port: number;
}

export function getServerConfig(
  environment: NodeJS.ProcessEnv = process.env,
): ServerConfig {
  const portText = environment.CUT_ON_EIGHT_PORT ?? '4318';
  const port = Number(portText);

  if (
    !/^[1-9]\d*$/.test(portText) ||
    !Number.isInteger(port) ||
    port > 65_535
  ) {
    throw new Error('CUT_ON_EIGHT_PORT must be an integer from 1 to 65535');
  }

  const dataRoot =
    environment.CUT_ON_EIGHT_DATA_ROOT ?? join(homedir(), 'cut-on-eight_data');

  if (!isAbsolute(dataRoot)) {
    throw new Error('CUT_ON_EIGHT_DATA_ROOT must be an absolute path');
  }

  const databaseUrl =
    environment.ConnectionStrings__catalog ?? environment.DATABASE_URL;
  if (databaseUrl === undefined || databaseUrl.trim() === '') {
    throw new Error(
      'ConnectionStrings__catalog or DATABASE_URL must be configured',
    );
  }
  assertUrl(databaseUrl, ['postgres:', 'postgresql:'], 'database URL');

  const qdrantHttpUrl =
    environment.QDRANT_HTTPURI ?? environment.QDRANT_HTTP_URL ?? null;
  if (qdrantHttpUrl !== null) {
    assertUrl(qdrantHttpUrl, ['http:', 'https:'], 'Qdrant URL');
  }
  const maxUploadBytes = Number(
    environment.CUT_ON_EIGHT_MAX_UPLOAD_BYTES ?? 20 * 1024 ** 3,
  );
  if (!Number.isSafeInteger(maxUploadBytes) || maxUploadBytes <= 0) {
    throw new Error('CUT_ON_EIGHT_MAX_UPLOAD_BYTES must be a positive integer');
  }

  return {
    dataRoot,
    databaseUrl,
    qdrantHttpUrl,
    qdrantApiKey: environment.QDRANT_APIKEY ?? null,
    maxUploadBytes,
    host: '127.0.0.1',
    port,
  };
}

function assertUrl(value: string, protocols: string[], label: string): void {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`Configured ${label} is not a valid URL`);
  }
  if (!protocols.includes(url.protocol)) {
    throw new Error(`Configured ${label} uses an unsupported protocol`);
  }
}
