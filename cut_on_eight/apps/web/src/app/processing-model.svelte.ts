import type { ProcessingSnapshotDto } from '@cut-on-eight/api-contracts';

const pollIntervalMs = 5000;

export class ProcessingModel {
  snapshot = $state.raw<ProcessingSnapshotDto | null>(null);
  stale = $state(false);
  expanded = $state(false);

  private timer: ReturnType<typeof setInterval> | null = null;
  private inFlight = false;
  private disposed = false;

  constructor(
    private readonly load: () => Promise<ProcessingSnapshotDto>,
    private readonly isVisible: () => boolean = () =>
      typeof document === 'undefined' || document.visibilityState === 'visible',
  ) {}

  start(): void {
    if (this.disposed || this.timer !== null) return;
    if (this.isVisible()) void this.refresh();
    this.timer = setInterval(() => {
      if (this.isVisible()) void this.refresh();
    }, pollIntervalMs);
  }

  async refresh(): Promise<void> {
    if (this.disposed || this.inFlight) return;
    this.inFlight = true;
    try {
      const snapshot = await this.load();
      if (this.disposed) return;
      this.snapshot = snapshot;
      this.stale = false;
    } catch {
      if (!this.disposed) this.stale = true;
    } finally {
      this.inFlight = false;
    }
  }

  toggle(): void {
    this.expanded = !this.expanded;
    if (this.expanded && this.stale) void this.refresh();
  }

  dispose(): void {
    this.disposed = true;
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }
}
