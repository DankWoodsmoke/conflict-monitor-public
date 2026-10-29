import { SHOWCASE } from "./runtime";
import { showcase } from "./showcase";
/** Replayable fixture clock; operational mode always uses wall clock. */
export const nowMs = () => SHOWCASE ? Date.parse(showcase.asOf) : Date.now();
