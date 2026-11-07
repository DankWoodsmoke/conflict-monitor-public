declare const __APP_BUILD_ID__:string;
/** A source fingerprint identifies the running UI; it is not a release-readiness assertion. */
export const BUILD_ID=typeof __APP_BUILD_ID__==="string"?__APP_BUILD_ID__:"development";
