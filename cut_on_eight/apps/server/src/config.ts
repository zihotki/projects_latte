import { homedir } from 'node:os';
import { isAbsolute, join } from 'node:path';

export interface ServerConfig {
  dataRoot: string;
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

  return { dataRoot, host: '127.0.0.1', port };
}
