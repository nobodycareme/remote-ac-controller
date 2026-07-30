// Native shim for `node:sqlite` used ONLY by the vitest transform pipeline.
// vite 5.4.x mishandles the `node:sqlite` builtin (strips the `node:` prefix and
// fails to resolve it). By aliasing `node:sqlite` -> this .cjs file, vite leaves the
// import as a native `require('node:sqlite')`, which Node resolves correctly. This
// keeps a SINGLE shared db module instance across the test files (no dup instances).
module.exports = require('node:sqlite');
