export type SaveState = 'saved' | 'saving' | 'unsaved' | 'failed';

export interface SaveStatus {
  readonly state: SaveState;
  readonly error: string | null;
}

export interface SaveClock {
  setTimeout(
    callback: () => void,
    milliseconds: number,
  ): ReturnType<typeof setTimeout>;
  clearTimeout(timer: ReturnType<typeof setTimeout>): void;
}

export interface SaveControllerOptions {
  readonly save: () => Promise<void>;
  readonly onStatusChange?: (status: SaveStatus) => void;
  readonly clock?: SaveClock;
  readonly debounceMilliseconds?: number;
}

const systemClock: SaveClock = {
  setTimeout: (callback, milliseconds) => setTimeout(callback, milliseconds),
  clearTimeout: (timer) => clearTimeout(timer),
};

export class SaveController {
  private readonly save: () => Promise<void>;
  private readonly onStatusChange: (status: SaveStatus) => void;
  private readonly clock: SaveClock;
  private readonly debounceMilliseconds: number;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private inFlight: Promise<void> | undefined;
  private revision = 0;
  private savedRevision = 0;
  private cancelled = false;
  private currentStatus: SaveStatus = { state: 'saved', error: null };

  constructor(options: SaveControllerOptions) {
    this.save = options.save;
    this.onStatusChange = options.onStatusChange ?? (() => undefined);
    this.clock = options.clock ?? systemClock;
    this.debounceMilliseconds = options.debounceMilliseconds ?? 1_000;
  }

  get state(): SaveState {
    return this.currentStatus.state;
  }

  get status(): SaveStatus {
    return this.currentStatus;
  }

  markDirty(): void {
    if (this.cancelled) return;

    this.revision += 1;
    this.setStatus('unsaved');
    this.clearTimer();

    if (this.inFlight === undefined) {
      this.scheduleSave();
    }
  }

  async flush(): Promise<void> {
    if (this.cancelled) return;

    this.clearTimer();
    const targetRevision = this.revision;

    while (!this.cancelled && this.savedRevision < targetRevision) {
      if (this.inFlight !== undefined) {
        await this.inFlight;
      } else {
        this.clearTimer();
        await this.startSave();
      }
    }

    if (!this.cancelled && this.revision === this.savedRevision) {
      this.setStatus('saved');
    }
  }

  retry(): Promise<void> {
    return this.flush();
  }

  cancel(): void {
    this.cancelled = true;
    this.clearTimer();
  }

  private scheduleSave(): void {
    this.timer = this.clock.setTimeout(() => {
      this.timer = undefined;
      void this.startSave().catch(() => undefined);
    }, this.debounceMilliseconds);
  }

  private startSave(): Promise<void> {
    if (this.inFlight !== undefined) return this.inFlight;

    const savingRevision = this.revision;
    this.setStatus('saving');

    const operation = Promise.resolve().then(this.save);
    this.inFlight = operation;

    void operation.then(
      () => {
        this.savedRevision = Math.max(this.savedRevision, savingRevision);
        this.finishSave(savingRevision, 'saved');
      },
      (error: unknown) =>
        this.finishSave(savingRevision, 'failed', errorMessage(error)),
    );

    return operation;
  }

  private finishSave(
    savingRevision: number,
    settledState: SaveState,
    error: string | null = null,
  ): void {
    this.inFlight = undefined;

    if (this.cancelled) return;

    if (this.revision > savingRevision) {
      this.setStatus(settledState === 'failed' ? 'failed' : 'unsaved', error);
      this.scheduleSave();
      return;
    }

    this.setStatus(settledState, error);
  }

  private clearTimer(): void {
    if (this.timer === undefined) return;
    this.clock.clearTimeout(this.timer);
    this.timer = undefined;
  }

  private setStatus(state: SaveState, error: string | null = null): void {
    if (
      state === this.currentStatus.state &&
      error === this.currentStatus.error
    )
      return;
    this.currentStatus = { state, error };
    this.onStatusChange(this.currentStatus);
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'The project could not be saved.';
}
