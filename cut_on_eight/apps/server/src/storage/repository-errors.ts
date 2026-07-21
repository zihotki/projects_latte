export class InvalidRepositoryDocumentError extends Error {
  readonly code = 'invalid_repository_document';

  constructor(documentName: string, cause: unknown) {
    super(`Invalid ${documentName} document`, { cause });
    this.name = 'InvalidRepositoryDocumentError';
  }
}
