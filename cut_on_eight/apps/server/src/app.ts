import { healthResponseSchema } from '@cut-on-eight/contracts';
import Fastify, { type FastifyInstance } from 'fastify';
import { getServerConfig, type ServerConfig } from './config.js';
import { installApiErrorHandling } from './http/api-error.js';
import { registerProjectRoutes } from './http/project-routes.js';
import { registerSourceRoutes } from './http/source-routes.js';
import { registerWorkspaceRoutes } from './http/workspace-routes.js';
import {
  MacOsSourcePicker,
  type SourcePicker,
} from './imports/source-picker.js';
import { createServices, type AppServices } from './services.js';

export interface CreateAppOptions {
  readonly config?: ServerConfig;
  readonly picker?: SourcePicker;
  readonly probeRunner?: unknown;
  readonly services?: AppServices;
}

export type CutOnEightApp = FastifyInstance & {
  recover(): Promise<void>;
};

export function createApp(options: CreateAppOptions = {}): CutOnEightApp {
  const services =
    options.services ??
    createServices({
      config: options.config ?? getServerConfig(),
      picker: options.picker ?? new MacOsSourcePicker(),
      probeRunner: options.probeRunner,
    });
  const app = Fastify({ logger: true });

  installApiErrorHandling(app);

  app.get('/api/health', async () =>
    healthResponseSchema.parse({
      status: 'ok',
      service: 'cut-on-eight-server',
    }),
  );

  registerWorkspaceRoutes(app, services);
  registerProjectRoutes(app, services);
  registerSourceRoutes(app, services);

  return Object.assign(app, {
    recover: () => services.recover(),
  });
}
