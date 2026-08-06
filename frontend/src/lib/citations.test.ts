import { describe, expect, it } from "vitest";

import { linkifyCitations, sourceAnchorId } from "./citations";

describe("linkifyCitations", () => {
  it("turns a single bare citation into a link to its source anchor", () => {
    expect(linkifyCitations("This is a fact [1].")).toBe(
      "This is a fact [[1]](#source-1).",
    );
  });

  it("handles multiple citations, including multi-digit IDs", () => {
    expect(linkifyCitations("See [2] and also [10].")).toBe(
      "See [[2]](#source-2) and also [[10]](#source-10).",
    );
  });

  it("leaves text with no citations unchanged", () => {
    const text = "No citations here at all.";
    expect(linkifyCitations(text)).toBe(text);
  });

  it("does not double-process a bracket that is already a Markdown link", () => {
    const text = "Already linked: [1](https://example.com).";
    expect(linkifyCitations(text)).toBe(text);
  });

  it("linkifies a bare citation that appears right before an unrelated parenthesis", () => {
    expect(linkifyCitations("A claim [3] (see also the appendix).")).toBe(
      "A claim [[3]](#source-3) (see also the appendix).",
    );
  });
});

describe("sourceAnchorId", () => {
  it("formats a stable anchor id for a source", () => {
    expect(sourceAnchorId(7)).toBe("source-7");
  });
});
