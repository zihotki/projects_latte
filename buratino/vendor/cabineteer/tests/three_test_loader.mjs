import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';

const tree = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../vendor/three');

export function resolve(specifier, context, nextResolve) {
  if (specifier === 'three') {
    return {url: pathToFileURL(path.join(tree, 'build/three.module.js')).href, shortCircuit: true};
  }
  return nextResolve(specifier, context);
}
