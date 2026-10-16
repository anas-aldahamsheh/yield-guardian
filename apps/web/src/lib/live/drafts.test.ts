import {
  DRAFT_KEYS,
  isDrawingDraft,
  readDraft,
  readJsonDraft,
  writeDraft,
  writeJsonDraft,
} from "./drafts";

describe("drafts kept for the tab", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("keeps and forgets a draft in this tab's sessionStorage", () => {
    expect(readDraft(DRAFT_KEYS.way)).toBeNull();
    expect(writeDraft(DRAFT_KEYS.way, "draw")).toBe(true);
    expect(readDraft(DRAFT_KEYS.way)).toBe("draw");
    expect(window.localStorage.length).toBe(0);
    writeDraft(DRAFT_KEYS.way, null);
    expect(readDraft(DRAFT_KEYS.way)).toBeNull();
  });

  it("reads back only what the check accepts", () => {
    const draft = { layoutId: "L1", edits: { L1: { wafers: ["AQI="], current: 0 } } };
    writeJsonDraft(DRAFT_KEYS.drawing, draft);
    expect(readJsonDraft(DRAFT_KEYS.drawing, isDrawingDraft)).toEqual(draft);
    writeDraft(DRAFT_KEYS.drawing, "{not json");
    expect(readJsonDraft(DRAFT_KEYS.drawing, isDrawingDraft)).toBeNull();
    writeJsonDraft(DRAFT_KEYS.drawing, { layoutId: 3, edits: {} });
    expect(readJsonDraft(DRAFT_KEYS.drawing, isDrawingDraft)).toBeNull();
    writeJsonDraft(DRAFT_KEYS.drawing, { layoutId: null, edits: { L1: { wafers: [1] } } });
    expect(readJsonDraft(DRAFT_KEYS.drawing, isDrawingDraft)).toBeNull();
  });

  it("works on without storage: nothing is kept, nothing throws", () => {
    const spy = vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(writeDraft(DRAFT_KEYS.way, "draw")).toBe(false);
    expect(readDraft(DRAFT_KEYS.way)).toBeNull();
    expect(writeJsonDraft(DRAFT_KEYS.upload, { a: 1 })).toBe(false);
    spy.mockRestore();
  });

  it("works on when storage refuses a write (a full quota)", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(writeDraft(DRAFT_KEYS.way, "upload")).toBe(false);
    expect(readDraft(DRAFT_KEYS.way)).toBeNull();
  });
});
