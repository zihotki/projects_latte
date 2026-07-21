import { ApiRouteError } from './api-error.js';

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseProjectId(value: unknown, key: string): string {
  if (
    typeof value !== 'object' ||
    value === null ||
    Array.isArray(value) ||
    !(key in value)
  ) {
    throw new ApiRouteError(
      400,
      'invalid_request',
      'The request does not contain a valid project ID.',
      false,
    );
  }

  const projectId = (value as Record<string, unknown>)[key];

  if (typeof projectId !== 'string' || !uuidPattern.test(projectId)) {
    throw new ApiRouteError(
      400,
      'invalid_request',
      'The request does not contain a valid project ID.',
      false,
    );
  }

  return projectId;
}
