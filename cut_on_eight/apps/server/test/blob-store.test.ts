import { readFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { afterEach, describe, expect, test } from 'vitest';
import { blobKey } from '../src/blobs/blob-key.js';
import { LocalBlobStore } from '../src/blobs/local-blob-store.js';

const root = resolve('.local/test-data/blob-store');

afterEach(async () => rm(root, { recursive: true, force: true }));

describe('LocalBlobStore', () => {
  test('stages, publishes and range reads without overwriting', async () => {
    const store = new LocalBlobStore(root);
    const staged = await store.writeStaged(
      (async function* () {
        yield Buffer.from('hello ');
        yield Buffer.from('world');
      })(),
    );
    const destination = blobKey('videos/video/source/demo.mp4');
    await store.publish(staged, destination);
    expect(await store.stat(destination)).toEqual({ size: 11 });
    expect(await readFile(resolve(root, destination), 'utf8')).toBe(
      'hello world',
    );
    const range = await store.openRange(destination, {
      start: 6,
      endInclusive: 10,
    });
    const chunks: Buffer[] = [];
    for await (const chunk of range.stream) chunks.push(Buffer.from(chunk));
    expect(Buffer.concat(chunks).toString()).toBe('world');

    const duplicate = await store.writeStaged(
      (async function* () {
        yield Buffer.from('duplicate');
      })(),
    );
    await expect(store.publish(duplicate, destination)).rejects.toThrow();
    await store.delete(destination);
    await store.delete(destination);
  });

  test.each(['/absolute', 'videos/../escape', 'videos\\escape', 'outside/key'])(
    'rejects unsafe key %s',
    (value) => expect(() => blobKey(value)).toThrow(),
  );
});
