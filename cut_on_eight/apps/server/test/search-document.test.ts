import { describe, expect, test } from 'vitest';
import { buildSearchDocument } from '../src/search/search-document.js';

describe('buildSearchDocument', () => {
  test('builds stable lexical text and a SHA-256 hash', () => {
    const source = {
      fragmentTitle: 'Fragment title',
      fragmentDescription: 'slow turn',
      fragmentTags: ['Foxtrot'],
      sourceTitle: 'source title',
      sourceDescription: 'lesson notes',
      sourceTags: ['Bronze'],
    };

    expect(buildSearchDocument(source)).toEqual({
      text: 'Fragment title\nslow turn\nfoxtrot\nsource title\nlesson notes\nbronze',
      hash: 'b78fadc2409c9af73dcbc23b7aa3cc03963ff21c60110bc2151ffd00d6b14dad',
    });
    expect(
      buildSearchDocument({ ...source, collectionTitles: ['ignored'] }).text,
    ).not.toContain('ignored');
  });

  test('omits blank fields and canonicalizes unordered tags', () => {
    expect(
      buildSearchDocument({
        fragmentTitle: '  Figure  ',
        fragmentDescription: ' ',
        fragmentTags: ['Waltz', 'turn', 'waltz'],
        sourceTitle: null,
        sourceDescription: '\n',
        sourceTags: [],
      }).text,
    ).toBe('Figure\nturn\nwaltz');
  });

  test('orders non-ASCII tags independently of the host locale', () => {
    expect(
      buildSearchDocument({
        fragmentTitle: null,
        fragmentDescription: null,
        fragmentTags: ['éclair', 'zebra', 'apple'],
        sourceTitle: null,
        sourceDescription: null,
        sourceTags: [],
      }).text,
    ).toBe('apple\nzebra\néclair');
  });
});
