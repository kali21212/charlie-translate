// jsdom in CRA/Jest 27 lacks the browser encoding APIs used by React Router 7.
// Use Node's real implementations; do not mock the upgraded routing library.
import { TextDecoder, TextEncoder } from "util";

globalThis.TextEncoder = globalThis.TextEncoder || TextEncoder;
globalThis.TextDecoder = globalThis.TextDecoder || TextDecoder;
