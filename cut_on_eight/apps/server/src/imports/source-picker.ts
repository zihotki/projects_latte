import { execFile } from 'node:child_process';

const pickerScript = [
  'set selectedFile to choose file of type {"public.mpeg-4"} with prompt "Choose an MP4 file"',
  'return POSIX path of selectedFile',
].join('\n');

export interface SourcePicker {
  selectMp4(): Promise<string | null>;
}

export interface ProcessResult {
  readonly stderr: string;
  readonly stdout: string;
}

export type ProcessRunner = (
  executable: string,
  arguments_: readonly string[],
) => Promise<ProcessResult>;

export class NativePickerError extends Error {
  readonly code = 'native_picker_failed';

  constructor(cause?: unknown) {
    super('The native MP4 picker failed', { cause });
    this.name = 'NativePickerError';
  }
}

const runProcess: ProcessRunner = (executable, arguments_) =>
  new Promise((resolve, reject) => {
    execFile(
      executable,
      [...arguments_],
      { encoding: 'utf8', shell: false },
      (error, stdout, stderr) => {
        if (error !== null) {
          reject(Object.assign(error, { stderr }));
          return;
        }

        resolve({ stdout, stderr });
      },
    );
  });

function isCancellation(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  const code =
    'code' in error ? (error as { readonly code?: unknown }).code : null;
  const stderr =
    'stderr' in error && typeof error.stderr === 'string' ? error.stderr : '';
  return code === '-128' || code === -128 || /\(-128\)/u.test(stderr);
}

export class MacOsSourcePicker implements SourcePicker {
  constructor(private readonly execute: ProcessRunner = runProcess) {}

  async selectMp4(): Promise<string | null> {
    let result: ProcessResult;

    try {
      result = await this.execute('osascript', ['-e', pickerScript]);
    } catch (error) {
      if (isCancellation(error)) {
        return null;
      }

      throw new NativePickerError(error);
    }

    const selectedPath = result.stdout.trim();

    if (selectedPath.length === 0) {
      throw new NativePickerError();
    }

    return selectedPath;
  }
}
