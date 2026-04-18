import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./Toast";

function Fixture({ message, type }: { message: string; type?: "info" | "success" | "error" }) {
  const { toast } = useToast();
  return <button onClick={() => toast(message, type)}>fire</button>;
}

describe("Toast", () => {
  it("renders a toast when toast() is called", () => {
    render(
      <ToastProvider>
        <Fixture message="Hello world" type="success" />
      </ToastProvider>,
    );
    act(() => {
      screen.getByRole("button", { name: "fire" }).click();
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Hello world");
  });

  it("dismisses when the toast is clicked", () => {
    render(
      <ToastProvider>
        <Fixture message="click me" type="error" />
      </ToastProvider>,
    );
    act(() => {
      screen.getByRole("button", { name: "fire" }).click();
    });
    const toast = screen.getByRole("alert");
    act(() => {
      toast.click();
    });
    expect(screen.queryByText("click me")).not.toBeInTheDocument();
  });

  describe("with fake timers", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("auto-dismisses after ~3.5s", () => {
      render(
        <ToastProvider>
          <Fixture message="ephemeral" />
        </ToastProvider>,
      );
      act(() => {
        screen.getByRole("button", { name: "fire" }).click();
      });
      expect(screen.getByText("ephemeral")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(3600);
      });
      expect(screen.queryByText("ephemeral")).not.toBeInTheDocument();
    });
  });
});
