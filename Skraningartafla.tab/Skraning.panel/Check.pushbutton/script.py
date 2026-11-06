# -*- coding: utf-8 -*-
"""Villuleit og yfirlit án þess að skrifa Excel skjal."""
__title__ = "Yfirfara\nskráningu"
__doc__ = ("Villuleitar skráningargögn í líkaninu (rýmisnúmer, eignarhald, höfuðflokkun, "
           "salarhæðir, nettóflötur...) og sýnir yfirlit eftir hæðum. Skrifar ekkert.")

from skraning import export

export.run(check_only=True)
