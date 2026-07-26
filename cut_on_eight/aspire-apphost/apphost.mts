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
await api.waitForCompletion(migrations);

const worker = await builder.addJavaScriptApp('worker', '../apps/server', {
  runScriptName: 'dev:worker',
});
await worker.withPnpm({ install: false });
await worker.withReference(catalog);
await worker.withReference(qdrant);
await worker.waitForCompletion(migrations);

const web = await builder.addViteApp('web', '../apps/web');
await web.withPnpm({ install: false });
await web.withReference(api);
await web.waitFor(api);

await builder.build().run();
