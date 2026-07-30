/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>;
  export default component;
}

declare const __APP_BUILD_ID__: string;
declare const __APP_GIT_COMMIT__: string;
declare const __APP_BUILD_TS__: string;
