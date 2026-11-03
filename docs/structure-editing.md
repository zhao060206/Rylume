# Complete structures in imported figures

Rylume 4.11 defaults to moving complete visual structures in high fidelity image imports. A click finds the containing outline; a marquee can specify a different region. Paths describing an organelle's fill, outline and texture move together. Labels remain separate objects. Path editing is an advanced secondary mode.

The scene retains original SVG snapshots. Stable `structures` IDs reference owner/path indices and store a translation, label, optional visibility, background reconstruction and foreground references. Splitting independent rectangular correction subpaths during first grouping preserves curves and holes. Later dragging changes only group metadata. A drag is one undo step. Save conflict handling and scene revisions remain shared with other editing operations.

The display uses detached geometry, Path2D hit testing, a spatial index, cached text outlines and independently transformed structure surfaces. Export never serializes those display canvases. `structure_render.py` applies the same ordering and background reconstruction to vector paths. SVG and PDF retain vectors, and PPTX contains a selectable native group for each displaced structure. Deleting a complete structure retains reversible source data while excluding its paths from export.

## Validation

The CC BY Figure 1 from Li and Battista, DOI **10.3390/ijms27209052**, was used as a real fixture (1770 × 900 pixels). Downloaded research images and user data are not included in the distribution.

- The fixture has 417 scene objects and 48,201 source paths including preserved text outlines. The live main SVG contains zero illustration paths; all original geometry remains in the scene.
- A complete mitochondrion groups 5,109 paths across 257 original colour batches. It presents one selection box and moves as one structure.
- Before caching, a measured drag/render cycle had a median of 112.1 ms; the final isolated run measured 17.3 ms, including the controlled frame delay. Display-update calls had a median of 0.1 ms. These are render-work measurements, not a guarantee of display FPS or performance on all machines.
- First grouping took about 1.3 seconds in the isolated run. Subsequent drags reuse the group. Loading and first grouping can still take longer for larger inputs.
- Grouping at rest retains the original 99.272% foreground RGB score against the paper image. The displaced display and vector export measured 99.59% RGB similarity, with renderer antialiasing differences. This does not verify scientific meaning or hidden content.
- Real HTTP save/reopen, undo/source restoration, native PPTX groups, SVG/PDF/PNG/PPTX output and browser pointer drags were exercised. The full Python run passed 642 tests and 7 subtests (one skipped); the additional workflow-semantics regression passed. All 40 JavaScript test files passed before the final workflow-only correction.

Reproduce with an authorized fixture:

```powershell
python tools/benchmark_performance.py --scene scene.json --svg figure.svg --output qa --serve 8917
# Open http://127.0.0.1:8917/structures and run the visible check.
python tools/verify_structure_fixture.py qa
python -m pytest tests/test_structures.py
node tests/test_structure_geometry.mjs
```

## Limits

Containing outlines and region selection are geometric grouping, not universal biological segmentation. A complex overlap or ambiguous outline may require a marquee. Moving an object reveals content absent from the source image; the background is estimated from nearby colours, and complex backgrounds require author review. Original traced arrows remain contour artwork; newly drawn native connections additionally support endpoint snapping and semantic types. No universal lossless or 99% reconstruction promise is made for arbitrary inputs.
