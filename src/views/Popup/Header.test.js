/* eslint-disable testing-library/no-unnecessary-act */
import { act } from "react";
import { createRoot } from "react-dom/client";
import Header from "./Header";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../../hooks/I18n", () => ({
  useI18n: () => (key) => key,
}));

jest.mock("../../components/Logo", () => () => null);

describe("Popup Header support menu", () => {
  let container;
  let root;
  let originalWindowOpen;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    originalWindowOpen = window.open;
    window.open = jest.fn();
  });

  afterEach(() => {
    act(() => root.unmount());
    document.body.innerHTML = "";
    window.open = originalWindowOpen;
  });

  test("keeps window/settings actions and removes support promotions", () => {
    const settings = jest.fn();
    const separate = jest.fn();
    act(() =>
      root.render(
        <Header openSettings={settings} openSeparateWindow={separate} />
      )
    );
    expect(container.querySelector('[aria-label="popup_support"]')).toBeNull();
    act(() => container.querySelector('[aria-label="setting"]').click());
    act(() =>
      container.querySelector('[aria-label="open_separate_window"]').click()
    );
    expect(settings).toHaveBeenCalledTimes(1);
    expect(separate).toHaveBeenCalledTimes(1);
  });

  test("collapses to a close button when hosted in the page", () => {
    const onClose = jest.fn();
    act(() => root.render(<Header onClose={onClose} />));

    const close = container.querySelector('[aria-label="close"]');
    expect(close).not.toBeNull();
    expect(
      container.querySelector('[aria-label="open_separate_window"]')
    ).toBeNull();

    act(() => close.click());
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
