import { ContainerLifetime, createBuilder } from './.aspire/modules/aspire.mjs';

const builder = await createBuilder();

const postgres = await builder.addPostgres('postgres');
await postgres.withImageTag('18.4');
await postgres.withDataVolume('cut-on-eight-postgres-data');
await postgres.withLifetime(ContainerLifetime.Persistent);
await postgres.withContainerName('cut-on-eight-postgres');
const catalog = await postgres.addDatabase('catalog', 'cut_on_eight');

const qdrant = await builder.addQdrant('qdrant');
await qdrant.withImageTag('v1.18.3');
await qdrant.withDataVolume('cut-on-eight-qdrant-data');
await qdrant.withLifetime(ContainerLifetime.Persistent);

const migrations = await builder.addJavaScriptApp(
  'migrations',
  '../apps/server',
  'db:migrate',
);
await migrations.withPnpm(false);
await migrations.withReference(catalog);
await migrations.waitFor(catalog);

const api = await builder.addJavaScriptApp('api', '../apps/server', 'dev');
await api.withPnpm(false);
await api.withHttpEndpoint({ env: 'CUT_ON_EIGHT_PORT' });
await api.withExternalHttpEndpoints();
await api.withReference(catalog);
await api.withReference(qdrant);
await api.waitForCompletion(migrations);

const worker = await builder.addJavaScriptApp(
  'worker',
  '../apps/server',
  'dev:worker',
);
await worker.withPnpm(false);
await worker.withReference(catalog);
await worker.withReference(qdrant);
await worker.waitForCompletion(migrations);

const web = await builder.addViteApp('web', '../apps/web');
await web.withPnpm(false);
await web.withReference(api);
await web.waitFor(api);

await builder.build().run();
