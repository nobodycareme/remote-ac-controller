import { createApp } from 'vue';
import App from './App.vue';
import './style.css';

createApp(App).mount('#app');

// Register PWA service worker (best-effort).
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  });
}
