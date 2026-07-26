import {
  catalogueMetadataSchema,
  type CatalogueMetadata,
} from '@cut-on-eight/legacy-contracts';
import { readJsonValidated, writeJsonAtomic } from './atomic-json.js';
import type { StorageLayout } from './layout.js';
import { InvalidRepositoryDocumentError } from './repository-errors.js';

const emptyMetadata = (): CatalogueMetadata => ({ schemaVersion: 1, tags: [] });

export class CatalogueMetadataRepository {
  constructor(private readonly layout: StorageLayout) {}

  async read(): Promise<CatalogueMetadata> {
    await this.layout.assertNoSymlinkComponents(
      this.layout.catalogueMetadataFile,
    );
    return (
      (await readJsonValidated(this.layout.catalogueMetadataFile, (value) =>
        catalogueMetadataSchema.parse(value),
      )) ?? emptyMetadata()
    );
  }

  async save(document: CatalogueMetadata): Promise<void> {
    let validated: CatalogueMetadata;
    try {
      validated = catalogueMetadataSchema.parse(document);
    } catch (error) {
      throw new InvalidRepositoryDocumentError('catalogue metadata', error);
    }
    await this.read();
    await this.layout.assertNoSymlinkComponents(
      this.layout.catalogueMetadataFile,
    );
    await writeJsonAtomic(this.layout.catalogueMetadataFile, validated);
  }
}
