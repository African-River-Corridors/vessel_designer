# Draw General Arrangements with sankofa-draw

GAs are produced through the shared `sankofa-draw` tool (Engineering Drawings as Code: DXF + SVG,
version-controlled), not with the bespoke SVG renderer ported from Ankobra. This takes a dependency on
the private Workflows repo, accepted because it is the house drawing standard and gives DXF for
drafters. Only the output layer imports it; the calculation core has no drawing dependency. Title blocks
carry the African River Corridors logo for now.
