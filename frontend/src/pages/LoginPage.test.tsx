import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const apiPost = vi.fn();
vi.mock("../api/client", () => ({
  default: { post: (...args: unknown[]) => apiPost(...args) },
}));

import LoginPage from "./LoginPage";
import { getAccessToken, getRefreshToken } from "../lib/auth";

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    navigate.mockClear();
    apiPost.mockReset();
  });

  it("defaults to sign-in mode (no display name field)", () => {
    renderLogin();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/display name/i)).not.toBeInTheDocument();
  });

  it("toggles to register mode and shows the display name field", async () => {
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole("button", { name: /register/i }));
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/display name/i)).toBeInTheDocument();
  });

  it("on successful login, stores both tokens and navigates to /documents", async () => {
    const user = userEvent.setup();
    apiPost.mockResolvedValueOnce({
      data: { access_token: "access-123", refresh_token: "refresh-456", token_type: "bearer" },
    });
    renderLogin();

    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "pw");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/documents"));
    expect(apiPost).toHaveBeenCalledWith("/api/auth/login", {
      email: "alice@example.com",
      password: "pw",
    });
    expect(getAccessToken()).toBe("access-123");
    expect(getRefreshToken()).toBe("refresh-456");
  });

  it("shows an error message when the server rejects the credentials", async () => {
    const user = userEvent.setup();
    apiPost.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { detail: "Invalid email or password" } },
    });
    // LoginPage uses axios.isAxiosError for the guard — stub it to see the rejected value as an axios error.
    const axiosModule = await import("axios");
    vi.spyOn(axiosModule.default, "isAxiosError").mockReturnValue(true);

    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
  });
});
