import "@testing-library/jest-dom/vitest";
import { api } from "../api/client";

// jsdom lacks ResizeObserver (used by Recharts' ResponsiveContainer) and matchMedia.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener() {},
  removeListener() {},
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

// No real network in unit tests: anything a test does not mock fails fast and quietly
// (otherwise jsdom logs connection errors for components that fetch metadata).
api.defaults.adapter = () => Promise.reject(new Error("network disabled in unit tests"));
