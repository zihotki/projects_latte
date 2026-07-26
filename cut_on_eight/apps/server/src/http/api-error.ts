import { apiErrorSchema, type ApiError } from '@cut-on-eight/legacy-contracts';
import type { FastifyInstance } from 'fastify';
import { CorruptPersistedDataError } from '../storage/atomic-json.js';
import { UnsafeStoragePathError } from '../storage/layout.js';
import { InvalidRepositoryDocumentError } from '../storage/repository-errors.js';
import { InvalidMp4SourceError } from '../imports/source-validator.js';
import { NativePickerError } from '../imports/source-picker.js';
import {
  CatalogNotFound,
  DomainConflict,
  StaleRevision,
} from '../domain/models.js';

export class ApiRouteError extends Error {
  constructor(
    readonly statusCode: number,
    readonly code: string,
    message: string,
    readonly retryable: boolean,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiRouteError';
  }
}

export function apiError(
  code: string,
  message: string,
  retryable: boolean,
  details?: Record<string, unknown>,
): ApiError {
  return apiErrorSchema.parse({
    error: { code, message, retryable, details },
  });
}

function toRouteError(error: unknown): ApiRouteError {
  if (error instanceof ApiRouteError) {
    return error;
  }

  if (error instanceof Error && error.name === 'ZodError') {
    return new ApiRouteError(
      400,
      'invalid_request',
      'The request does not match the expected format.',
      false,
    );
  }

  if (
    error instanceof Error &&
    'statusCode' in error &&
    typeof error.statusCode === 'number' &&
    error.statusCode >= 400 &&
    error.statusCode < 500
  ) {
    return new ApiRouteError(
      400,
      'invalid_request',
      'The request does not match the expected format.',
      false,
    );
  }

  if (error instanceof InvalidMp4SourceError) {
    return new ApiRouteError(400, error.code, error.message, false);
  }

  if (error instanceof NativePickerError) {
    return new ApiRouteError(
      500,
      error.code,
      'The native MP4 picker could not be opened.',
      true,
    );
  }

  if (error instanceof CorruptPersistedDataError) {
    return new ApiRouteError(
      500,
      error.code,
      'Managed project data is corrupt and was left unchanged.',
      false,
    );
  }

  if (error instanceof InvalidRepositoryDocumentError) {
    return new ApiRouteError(
      400,
      error.code,
      'The project data could not be saved because it is invalid.',
      false,
    );
  }

  if (error instanceof UnsafeStoragePathError) {
    return new ApiRouteError(
      500,
      error.code,
      'Managed storage could not be accessed safely.',
      false,
    );
  }

  return new ApiRouteError(
    500,
    'internal_error',
    'The server could not complete the request.',
    true,
  );
}

export function installApiErrorHandling(app: FastifyInstance): void {
  app.setNotFoundHandler((_request, reply) =>
    reply
      .code(404)
      .send(apiError('route_not_found', 'The API route was not found.', false)),
  );

  app.setErrorHandler((error, request, reply) => {
    if (
      error instanceof CatalogNotFound ||
      error instanceof DomainConflict ||
      error instanceof StaleRevision
    ) {
      const status =
        error instanceof CatalogNotFound
          ? 404
          : error.code === 'validation_failed'
            ? 422
            : 409;
      const code = error instanceof CatalogNotFound ? error.code : error.code;
      return reply.code(status).send({
        type: `https://cut-on-eight.local/problems/${code}`,
        title: status === 404 ? 'Catalog item not found' : 'Catalog conflict',
        status,
        detail:
          error.message || 'The catalog operation could not be completed.',
        code,
        instance: request.url,
      });
    }
    const safeError = toRouteError(error);

    if (safeError.statusCode >= 500) {
      request.log.error(error);
    }

    return reply
      .code(safeError.statusCode)
      .send(
        apiError(
          safeError.code,
          safeError.message,
          safeError.retryable,
          safeError.details,
        ),
      );
  });
}
