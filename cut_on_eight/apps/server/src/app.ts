import { healthResponseSchema } from '@cut-on-eight/contracts';
import Fastify, { type FastifyInstance } from 'fastify';
import { getServerConfig, type ServerConfig } from './config.js';
import { installApiErrorHandling } from './http/api-error.js';
import { installApiRequestProtection } from './http/request-protection.js';
import { registerProjectRoutes } from './http/project-routes.js';
import { registerJobRoutes } from './http/job-routes.js';
import { registerSourceRoutes } from './http/source-routes.js';
import { registerThumbnailRoutes } from './http/thumbnail-routes.js';
import { registerWorkspaceRoutes } from './http/workspace-routes.js';
import { registerFragmentRoutes } from './http/fragment-routes.js';
import {
  MacOsSourcePicker,
  type SourcePicker,
} from './imports/source-picker.js';
import { createServices, type AppServices } from './services.js';

export interface CreateAppOptions {
  readonly config?: ServerConfig;
  readonly picker?: SourcePicker;
  readonly probeRunner?: import('./jobs/ffprobe-runner.js').ProbeRunner;
  readonly thumbnailGenerator?: import('./thumbnails/thumbnail-worker.js').ThumbnailGenerator;
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
      thumbnailGenerator: options.thumbnailGenerator,
    });
  const app = Fastify({ logger: true });

  installApiErrorHandling(app);
  installApiRequestProtection(app);

  app.get('/api/health', async () =>
    healthResponseSchema.parse({
      status: 'ok',
      service: 'cut-on-eight-server',
    }),
  );

  registerWorkspaceRoutes(app, services);
  registerProjectRoutes(app, services);
  registerFragmentRoutes(app, services);
  registerSourceRoutes(app, services);
  registerThumbnailRoutes(app, services);
  registerJobRoutes(app, services);

  app.addHook('onClose', async () => services.shutdown?.());

  return Object.assign(app, {
    recover: () => services.recover(),
  });
}
