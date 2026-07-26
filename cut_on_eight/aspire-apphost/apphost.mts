import { ContainerLifetime, createBuilder } from './.aspire/modules/aspire.mjs';

const builder = await createBuilder();

const postgres = await builder.addPostgres('postgres');
await postgres.withImageTag('18.4');
await postgres.withDataVolume({ name: 'cut-on-eight-postgres-data' });
await postgres.withLifetime(ContainerLifetime.Persistent);
await postgres.withContainerName('cut-on-eight-postgres');
const catalog = await postgres.addDatabase('catalog', {
  databaseName: 'cut_on_eight',
});

const qdrant = await builder.addQdrant('qdrant');
await qdrant.withImageTag('v1.18.3');
await qdrant.withDataVolume({ name: 'cut-on-eight-qdrant-data' });
await qdrant.withLifetime(ContainerLifetime.Persistent);

const nats = await builder.addContainer('nats', 'nats');
await nats.withImageTag('2.14.3-alpine');
await nats.withArgs(['-js', '-sd', '/data']);
await nats.withVolume('/data', { name: 'cut-on-eight-nats-data' });
await nats.withLifetime(ContainerLifetime.Persistent);
await nats.withEndpoint({ name: 'nats', port: 4222, targetPort: 4222 });

const migrations = await builder.addJavaScriptApp(
  'migrations',
  '../apps/server',
  { runScriptName: 'db:migrate' },
);
await migrations.withPnpm({ install: false });
await migrations.withReference(catalog);
await migrations.waitFor(catalog);

const api = await builder.addJavaScriptApp('api', '../apps/server');
await api.withPnpm({ install: false });
await api.withHttpEndpoint({ env: 'CUT_ON_EIGHT_PORT' });
await api.withExternalHttpEndpoints();
await api.withReference(catalog);
await api.withReference(qdrant);
await api.withReference(nats);
await api.withEnvironment('NATS_URL', 'nats://127.0.0.1:4222');
await api.waitForCompletion(migrations);

const worker = await builder.addJavaScriptApp('worker', '../apps/server', {
  runScriptName: 'dev:worker',
});
await worker.withPnpm({ install: false });
await worker.withReference(catalog);
await worker.withReference(qdrant);
await worker.waitForCompletion(migrations);

const relay = await builder.addJavaScriptApp('outbox-relay', '../apps/server', {
  runScriptName: 'dev:relay',
});
await relay.withPnpm({ install: false });
await relay.withReference(catalog);
await relay.withReference(nats);
await relay.withEnvironment('NATS_URL', 'nats://127.0.0.1:4222');
await relay.waitForCompletion(migrations);

const projector = await builder.addJavaScriptApp(
  'qdrant-projector',
  '../apps/server',
  {
    runScriptName: 'dev:qdrant-projector',
  },
);
await projector.withPnpm({ install: false });
await projector.withReference(catalog);
await projector.withReference(qdrant);
await projector.withReference(nats);
await projector.withEnvironment('NATS_URL', 'nats://127.0.0.1:4222');
await projector.waitForCompletion(migrations);

const thumbnails = await builder.addJavaScriptApp(
  'thumbnails-service',
  '../apps/server',
  {
    runScriptName: 'dev:thumbnails-service',
  },
);
await thumbnails.withPnpm({ install: false });
await thumbnails.withHttpEndpoint({
  port: 4320,
  env: 'CUT_ON_EIGHT_THUMBNAIL_ORIGIN_PORT',
});
await thumbnails.withExternalHttpEndpoints();
await thumbnails.withReference(catalog);
await thumbnails.withReference(nats);
await thumbnails.withEnvironment('NATS_URL', 'nats://127.0.0.1:4222');
await thumbnails.waitForCompletion(migrations);

const web = await builder.addViteApp('web', '../apps/web');
await web.withPnpm({ install: false });
await web.withReference(api);
await web.withReference(thumbnails);
await web.waitFor(api);

await builder.build().run();
