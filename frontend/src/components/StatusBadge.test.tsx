import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the status text", () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText("completed")).toBeInTheDocument();
  });

  it("shows a pulsing indicator only for running jobs", () => {
    const { container, rerender } = render(<StatusBadge status="running" />);
    expect(container.querySelector(".animate-pulse")).not.toBeNull();

    rerender(<StatusBadge status="completed" />);
    expect(container.querySelector(".animate-pulse")).toBeNull();
  });
});
