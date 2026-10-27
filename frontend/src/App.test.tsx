import { render, screen } from "@testing-library/react";
import App from "./App";
import { Providers } from "./test/fixtures";

it("sends signed-out users to the login page", async () => {
  render(
    <Providers route="/ask">
      <App />
    </Providers>,
  );
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Analyst" })).toBeInTheDocument();
});
