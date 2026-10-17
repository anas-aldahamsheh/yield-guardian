/**
 * A model-backed action failed. The provider-failure dialog listens: when the site runs on AMD it
 * offers to switch to Claude and run the action again; on Claude it does nothing.
 */
export const MODEL_FAILED = "yg:model-failed";

export interface ModelFailure {
  reason: string;
  retry: () => void;
}

export function reportModelFailure(failure: ModelFailure) {
  window.dispatchEvent(new CustomEvent<ModelFailure>(MODEL_FAILED, { detail: failure }));
}
