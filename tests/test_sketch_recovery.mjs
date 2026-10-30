import assert from 'node:assert/strict';
import {setupSketchPad} from '../ui/sketch-pad.js';
let nextImage=0,currentImage=0,restored=0;
const ctx={fillRect(){currentImage=0;},getImageData(){return {image:currentImage};},putImageData(image){currentImage=image.image;},
 beginPath(){},moveTo(){},lineTo(){},stroke(){currentImage=++nextImage;},fillText(){currentImage=++nextImage;},drawImage(){restored++;}};
const elements=new Map();
function $(id){if(!elements.has(id))elements.set(id,{value:'',listeners:{},
 addEventListener(name,handler){this.listeners[name]=handler;},getContext(){return ctx;},
 getBoundingClientRect(){return {left:0,top:0,width:600,height:400};},
 setPointerCapture(){},focus(){},toDataURL(){return 'data:image/png;base64,'+currentImage;},showModal(){},close(){}});return elements.get(id);}
const tools=['pen','text'].map(tool=>({dataset:{sketchTool:tool},setAttribute(){}}));
const saved=new Map([['rylume-drawn-sketch-v1','data:image/png;base64,recovered']]);
const images=[];
globalThis.document={getElementById:$,querySelectorAll(){return tools;}};
globalThis.localStorage={getItem:key=>saved.get(key),setItem:(key,value)=>saved.set(key,value),removeItem:key=>saved.delete(key)};
globalThis.Image=class{constructor(){images.push(this);}};
const used=[],messages=[];
setupSketchPad({onUse:async image=>used.push(image),toast:message=>messages.push(message)});
const paper=$('sketch-pad');paper.width=1200;paper.height=800;
const event={button:0,pointerId:1,clientX:40,clientY:40,preventDefault(){}};
paper.listeners.pointerdown(event);paper.listeners.pointermove({...event,clientX:80});
paper.listeners.pointerup();
assert.equal(saved.get('rylume-drawn-sketch-v1'),'data:image/png;base64,1');
images[0].onload();assert.equal(restored,0,'Late recovery may not paint over a new stroke');
paper.listeners.pointerdown(event);paper.listeners.pointermove({...event,clientX:90});
paper.listeners.pointercancel();assert.equal(currentImage,1,'A cancelled stroke restores the previous pixels');
tools[1].onclick();paper.listeners.pointerdown(event);
assert.ok(messages.includes('先输入名称，再点击纸面放置'));
$('sketch-pad-undo').onclick();assert.equal(currentImage,0,'Empty text input cannot consume the previous undo step');
assert.equal(saved.has('rylume-drawn-sketch-v1'),false);
$('sketch-pad-label').value='Author label';paper.listeners.pointerdown(event);paper.listeners.pointerup();
await $('use-drawn-sketch').onclick();assert.equal(used.length,1);
assert.equal(saved.get('rylume-drawn-sketch-v1'),used[0]);
delete globalThis.document;delete globalThis.localStorage;delete globalThis.Image;
console.log('Sketch strokes persist, cancellation restores pixels, empty text preserves undo and late recovery never overwrites fresh drawing');
