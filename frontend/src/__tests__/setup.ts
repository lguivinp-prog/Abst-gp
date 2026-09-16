import { Module } from 'module';

const originalRequire = Module.prototype.require;
Module.prototype.require = function(request: string) {
  if (request.endsWith('.css')) {
    return {};
  }
  return originalRequire.apply(this, arguments as any);
};
