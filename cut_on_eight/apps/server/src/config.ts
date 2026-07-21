export interface ServerConfig {
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

  return { host: '127.0.0.1', port };
}
