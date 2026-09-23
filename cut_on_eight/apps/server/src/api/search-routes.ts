import {
  fragmentSearchQuerySchema,
  fragmentSearchResponseSchema,
} from '@cut-on-eight/api-contracts';
import type { FastifyInstance } from 'fastify';
import { ApiRouteError } from '../http/api-error.js';
import type { ApiRuntime } from '../runtime.js';
import { SearchUnavailableError } from '../search/search-service.js';

export function registerSearchRoutes(
  app: FastifyInstance,
  runtime: ApiRuntime,
): void {
  app.get<{ Querystring: Record<string, string | string[] | undefined> }>(
    '/api/search/fragments',
    async (request) => {
      try {
        return fragmentSearchResponseSchema.parse(
          await runtime.search.search(
            fragmentSearchQuerySchema.parse({
              q: singleValue(request.query.q),
              tagIds: repeatedValues(request.query.tagIds),
              collectionIds: repeatedValues(request.query.collectionIds),
              videoIds: repeatedValues(request.query.videoIds),
              limit: singleValue(request.query.limit),
            }),
          ),
        );
      } catch (error) {
        if (error instanceof SearchUnavailableError) {
          throw new ApiRouteError(
            503,
            error.code,
            'Search is temporarily unavailable.',
            true,
          );
        }
        throw error;
      }
    },
  );
}

function singleValue(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value.length === 1 ? value[0] : undefined;
  return value;
}

function repeatedValues(value: string | string[] | undefined): string[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}
