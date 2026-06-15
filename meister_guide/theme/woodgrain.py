"""Subtle wood-grain noise tile as a base64 data URI for QSS backgrounds."""
import base64

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
    '<filter id="n">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.9 0.02" '
    'numOctaves="2" seed="7"/>'
    '<feColorMatrix type="saturate" values="0"/>'
    '</filter>'
    '<rect width="120" height="120" filter="url(#n)" opacity="0.05"/>'
    '</svg>'
)

WOODGRAIN_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(
    _SVG.encode("utf-8")
).decode("ascii")
