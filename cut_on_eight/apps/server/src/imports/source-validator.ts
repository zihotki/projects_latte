import { open, realpath } from 'node:fs/promises';
import { extname } from 'node:path';
import type { ImportFingerprint } from '../storage/library-repository.js';

export interface ValidatedSource {
  readonly fingerprint: ImportFingerprint;
  readonly path: string;
}

export class InvalidMp4SourceError extends Error {
  readonly code = 'invalid_mp4_source';

  constructor(message: string, cause?: unknown) {
    super(message, { cause });
    this.name = 'InvalidMp4SourceError';
  }
}

export async function validateMp4Source(
  selectedPath: string,
): Promise<ValidatedSource> {
  let resolvedPath: string;

  try {
    resolvedPath = await realpath(selectedPath);
  } catch (error) {
    throw new InvalidMp4SourceError(
      'The selected MP4 cannot be resolved',
      error,
    );
  }

  if (extname(resolvedPath).toLowerCase() !== '.mp4') {
    throw new InvalidMp4SourceError('The selected source must be an MP4 file');
  }

  let handle;

  try {
    handle = await open(resolvedPath, 'r');
  } catch (error) {
    throw new InvalidMp4SourceError('The selected MP4 cannot be opened', error);
  }

  try {
    const sourceStatus = await handle.stat();

    if (!sourceStatus.isFile()) {
      throw new InvalidMp4SourceError(
        'The selected source must be a regular file',
      );
    }

    if (!Number.isSafeInteger(sourceStatus.size) || sourceStatus.size <= 0) {
      throw new InvalidMp4SourceError('The selected MP4 must not be empty');
    }

    if (!Number.isFinite(sourceStatus.mtimeMs) || sourceStatus.mtimeMs < 0) {
      throw new InvalidMp4SourceError('The selected MP4 timestamp is invalid');
    }

    const header = Buffer.alloc(12);
    const { bytesRead } = await handle.read(header, 0, header.length, 0);
    const boxSize = bytesRead === header.length ? header.readUInt32BE(0) : 0;
    const hasFtyp = header.subarray(4, 8).equals(Buffer.from('ftyp'));

    if (
      bytesRead !== header.length ||
      !hasFtyp ||
      boxSize < header.length ||
      boxSize > sourceStatus.size
    ) {
      throw new InvalidMp4SourceError(
        'The selected file is not a supported ISO base-media MP4',
      );
    }

    return {
      path: resolvedPath,
      fingerprint: {
        realPath: resolvedPath,
        size: sourceStatus.size,
        modifiedMilliseconds: sourceStatus.mtimeMs,
      },
    };
  } finally {
    await handle.close();
  }
}
