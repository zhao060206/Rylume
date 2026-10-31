import assert from 'node:assert/strict';
import {clampPosition} from '../ui/floating-windows.js';
assert.equal(clampPosition(-20,100,600),0);
assert.equal(clampPosition(580,100,600),500);
assert.equal(clampPosition(100,800,600),0);
assert.equal(clampPosition(125,100,600),125);
console.log('floating window bounds passed');
