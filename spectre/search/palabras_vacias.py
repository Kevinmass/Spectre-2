"""Palabras vacías del castellano — artículos, preposiciones, conjunciones,
pronombres, determinantes y las cópulas más frecuentes.

Se usa para dos cosas que no tienen que ver con el ranking:

- resaltar los términos de la consulta sin marcar "del" / "por" / "sin"
  (PR-A3, del lado del navegador);
- ubicar dónde recortar el extracto sin centrarlo en una palabra vacía
  (PR-A4, en `spectre/api/app.py`).

**Hay un gemelo en `spectre/web/app.js` (`PALABRAS_VACIAS`).** Si se toca una
lista, tocar la otra: no comparten código (una es Python, la otra JS servida
al navegador sin build, D-15).
"""

from __future__ import annotations

_LISTA = """
    el la lo los las un una unos unas al del
    de a ante bajo cabe con contra desde durante en entre hacia hasta
    mediante para por según sin so sobre tras
    y e o u ni que pero mas sino aunque porque pues como si cuando mientras
    donde
    yo tú él ella ello nosotros vosotros ellos ellas me te se nos os le les
    mi mis tu tus su sus nuestro nuestra nuestros nuestras vuestro vuestra
    este esta esto estos estas ese esa eso esos esas
    aquel aquella aquello aquellos aquellas
    cual cuales quien quienes cuyo cuya cuyos cuyas
    otro otra otros otras mismo misma mismos mismas
    tan tanto tanta tantos tantas todo toda todos todas cada
    algún alguna alguno algunos algunas ningún ninguna ninguno
    mucho mucha muchos muchas poco poca pocos pocas más menos muy
    no sí ya así también tampoco siempre nunca solo sólo aún aun
    es son ser fue fueron era eran sea sean
    ha han haber hay había habían hubo está están estaba estar
"""

PALABRAS_VACIAS: frozenset[str] = frozenset(_LISTA.split())
