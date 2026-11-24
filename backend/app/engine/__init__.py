"""PDFVana document engine.

Low-level building blocks shared by every tool:

* ``geometry`` – page boxes, rotation and the mapping between what a reader
  *sees* (view space) and the PDF's own coordinate system (user space).
* ``raster``   – rendering, text and image extraction.
* ``stamp``    – vector stamps (text, images, shapes) placed on pages at any
  position, size, rotation and opacity.
* ``layout``   – reading-order analysis that turns a PDF page into paragraphs,
  headings, lists, tables and images.
* ``export``   – Word, PowerPoint, Excel, CSV and Markdown writers.
"""
