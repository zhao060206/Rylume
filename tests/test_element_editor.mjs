import assert from 'node:assert/strict';
import {localVectorDelta,enclosedBounds} from '../ui/element-editor.js';
assert.deepEqual(localVectorDelta({a:2,b:0,c:0,d:4},6,8),{x:3,y:2});
assert.deepEqual(localVectorDelta({a:0,b:2,c:-2,d:0},6,8),{x:4,y:-3});
assert.throws(()=>localVectorDelta({a:0,b:0,c:0,d:0},1,1),/不可逆/);
assert.equal(enclosedBounds({x:2,y:3,w:4,h:5},{x:0,y:0,w:10,h:10}),true);
assert.equal(enclosedBounds({x:0,y:0,w:20,h:20},{x:2,y:2,w:10,h:10}),false,'A background path must not join a small icon selection');
console.log('Internal vector editing respects scaled/rotated parents and excludes large background paths.');
