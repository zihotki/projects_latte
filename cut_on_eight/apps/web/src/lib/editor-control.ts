export interface VideoEditorControl {
  readonly projectId: string;
  prepareForSave(): void;
  releaseAfterSave(): void;
}

export type RegisterVideoEditorControl = (
  control: VideoEditorControl,
) => () => void;
