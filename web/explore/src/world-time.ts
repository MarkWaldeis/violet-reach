import { renderGroup, uniform } from "three/tsl";

/** Fixed shader time (s) used by ?freeze=1 so captures are reproducible. */
export const FROZEN_TIME = 0;
let frozen: number | undefined;

/** Drop-in for TSL `time` that every animated effect (clouds, water) must use. */
export const worldTime = uniform(0).setGroup(renderGroup).onRenderUpdate((frame) => frozen ?? frame.time ?? 0);

export function freezeWorldTime(at: number | undefined = FROZEN_TIME) {
  frozen = at;
}

export const worldTimeFrozen = () => frozen !== undefined;
